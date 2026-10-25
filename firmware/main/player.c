/*
 * The play queue. Producers (lecture.c, ask.c) push items in timeline order; one task plays them,
 * so subtitles, mode changes and animation frames happen exactly when the audio reaches them.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_heap_caps.h"
#include "app.h"

typedef enum { IT_AUDIO, IT_SUB, IT_MODE, IT_FRAME, IT_KEY, IT_FINAL } item_type_t;

typedef struct {
    uint8_t type;
    uint32_t pos;     /* audio: lecture sample of the first sample (or ANSWER_POS) */
    int32_t a, b;     /* mode / scene, frame */
    uint32_t len;     /* bytes in data */
    uint8_t data[];   /* pcm16 for audio, NUL-terminated text for subtitles */
} item_t;

static QueueHandle_t q;
static volatile uint32_t gen;
volatile uint32_t played_pos;
volatile int32_t queued_samples;

static void push(item_t *it)
{
    if (it && xQueueSend(q, &it, pdMS_TO_TICKS(5000)) != pdTRUE) {
        if (it->type == IT_AUDIO) __atomic_sub_fetch(&queued_samples, it->len / 2, __ATOMIC_RELAXED);
        free(it);
    }
}

static item_t *make(uint8_t type, size_t len)
{
    item_t *it = heap_caps_malloc(sizeof(item_t) + len, MALLOC_CAP_SPIRAM);
    if (it) {
        memset(it, 0, sizeof(item_t));
        it->type = type;
        it->len = len;
    }
    return it;
}

void play_audio(uint32_t pos, const int16_t *pcm, size_t samples)
{
    item_t *it = make(IT_AUDIO, samples * 2);
    if (!it) return;
    it->pos = pos;
    memcpy(it->data, pcm, samples * 2);
    __atomic_add_fetch(&queued_samples, samples, __ATOMIC_RELAXED);
    push(it);
}

void play_sub(const char *text)
{
    size_t n = strlen(text);
    item_t *it = make(IT_SUB, n + 1);
    if (!it) return;
    memcpy(it->data, text, n + 1);
    push(it);
}

static void push_ab(uint8_t type, int a, int b)
{
    item_t *it = make(type, 0);
    if (!it) return;
    it->a = a;
    it->b = b;
    push(it);
}

void play_mode(app_mode_t m) { push_ab(IT_MODE, m, 0); }
void play_frame(int scene, int frame) { push_ab(IT_FRAME, scene, frame); }
void play_key(int scene, int frame) { push_ab(IT_KEY, scene, frame); }
void play_final(int scene) { push_ab(IT_FINAL, scene, 0); }

void play_flush(void)
{
    gen++;
    item_t *it;
    while (xQueueReceive(q, &it, 0) == pdTRUE) {
        if (it->type == IT_AUDIO) __atomic_sub_fetch(&queued_samples, it->len / 2, __ATOMIC_RELAXED);
        free(it);
    }
}

static void player_task(void *arg)
{
    item_t *it;
    for (;;) {
        if (xQueueReceive(q, &it, portMAX_DELAY) != pdTRUE) continue;
        uint32_t g = gen;
        switch (it->type) {
        case IT_AUDIO: {
            const int16_t *pcm = (const int16_t *)it->data;
            uint32_t n = it->len / 2;
            for (uint32_t off = 0; off < n && g == gen; off += 320) {           /* 20 ms writes */
                uint32_t k = n - off < 320 ? n - off : 320;
                esp_codec_dev_write(spk, (void *)(pcm + off), k * 2);
                if (it->pos != ANSWER_POS) played_pos = it->pos + off + k;
            }
            __atomic_sub_fetch(&queued_samples, n, __ATOMIC_RELAXED);
            break;
        }
        case IT_SUB:
            if (g == gen) {
                ui_lock();
                ui_set_sub((const char *)it->data);
                ui_unlock();
            }
            break;
        case IT_MODE:
            if (g == gen) {
                ui_lock();
                ui_set_mode((app_mode_t)it->a);
                ui_unlock();
                if (it->a == MODE_DONE) app_lecture_done();
            }
            break;
        case IT_FRAME:
            if (g == gen) video_apply(it->a, it->b);
            break;
        case IT_KEY:
            if (g == gen) video_seek(it->a, it->b);
            break;
        case IT_FINAL:
            if (g == gen) video_final(it->a);
            break;
        }
        free(it);
    }
}

void player_init(void)
{
    q = xQueueCreate(512, sizeof(item_t *));
    xTaskCreatePinnedToCore(player_task, "player", 6144, NULL, 7, NULL, 1);
}
