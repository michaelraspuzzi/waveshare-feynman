/*
 * Lecture engine: reads lecture.fqv from the "lecture" flash partition (see tools/pack_lecture.py)
 * and feeds the play queue in timeline order: one MP3 frame of audio (36 ms) at a time, with the
 * subtitles and animation frames that fall inside it pushed just before it.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_partition.h"
#include "miniz.h"
#include "mp3dec.h"
#include "app.h"

static const char *TAG = "lecture";

typedef struct __attribute__((packed)) {
    char magic[4];
    uint32_t size, rate;
    uint16_t fps, n_scenes, n_lines, n_subs;
    uint32_t total, audio_off, audio_len;
    uint16_t mp3_bytes, mp3_samples;
    uint32_t scenes_off, lines_off, subs_off, strings_off, title;
    uint8_t pad[8];
} hdr_t;

typedef struct __attribute__((packed)) {
    char id[24];
    uint32_t start, end, frames, palette, index, final_off, final_len, desc;
    uint8_t pad[8];
} scene_rec_t;

typedef struct __attribute__((packed)) {
    uint32_t start, end;
    uint16_t scene, pad;
    uint32_t text;
} line_rec_t;

typedef struct __attribute__((packed)) {
    uint32_t at, text;
} sub_rec_t;

#define TILE  16
#define GRID  30
#define BITMAP 113

static const esp_partition_t *part;
static uint8_t *meta;                 /* everything before the payload: header, tables, strings */
static hdr_t *H;
static scene_rec_t *scenes;
static line_rec_t *lines;
static sub_rec_t *subs;
static const char *strings;
static uint16_t **palettes;
static uint32_t **indexes;

static TaskHandle_t producer;
static volatile uint32_t play_gen, req_pos;
static volatile bool running;

/* ---------------------------------------------------------------- reading */

static void rd(uint32_t off, void *buf, size_t len)
{
    esp_partition_read(part, off, buf, len);
}

static void *rd_alloc(uint32_t off, size_t len)
{
    void *p = heap_caps_malloc(len, MALLOC_CAP_SPIRAM);
    if (p) rd(off, p, len);
    return p;
}

bool lecture_init(void)
{
    part = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x40, "lecture");
    if (!part) {
        ESP_LOGE(TAG, "no 'lecture' partition");
        return false;
    }
    hdr_t h;
    rd(0, &h, sizeof(h));
    if (memcmp(h.magic, "FQV1", 4) || h.size > part->size) {
        ESP_LOGE(TAG, "lecture partition is empty or not FQV1 (flash build/lectures/*/lecture.fqv)");
        return false;
    }
    meta = rd_alloc(0, h.audio_off);
    H = (hdr_t *)meta;
    scenes = (scene_rec_t *)(meta + H->scenes_off);
    lines = (line_rec_t *)(meta + H->lines_off);
    subs = (sub_rec_t *)(meta + H->subs_off);
    strings = (const char *)(meta + H->strings_off);
    palettes = calloc(H->n_scenes, sizeof(uint16_t *));
    indexes = calloc(H->n_scenes, sizeof(uint32_t *));
    for (int i = 0; i < H->n_scenes; i++) {
        palettes[i] = rd_alloc(scenes[i].palette, 512);
        indexes[i] = rd_alloc(scenes[i].index, (scenes[i].frames + 1) * 4);
    }
    ESP_LOGI(TAG, "'%s': %d scenes, %d lines, %.1f min", strings + H->title, H->n_scenes, H->n_lines,
             H->total / (float)H->rate / 60);
    return true;
}

uint32_t lecture_total(void) { return H ? H->total : 0; }
const char *lecture_title(void) { return H ? strings + H->title : ""; }
int lecture_scene_count(void) { return H ? H->n_scenes : 0; }
const char *lecture_scene_id(int i) { return scenes[i].id; }
const char *lecture_scene_desc(int i) { return strings + scenes[i].desc; }

int lecture_scene_find(const char *id)
{
    for (int i = 0; H && id && i < H->n_scenes; i++)
        if (!strncmp(scenes[i].id, id, sizeof(scenes[i].id))) return i;
    return -1;
}

static uint32_t line_start(uint32_t pos)
{
    for (int i = 0; i < H->n_lines; i++)
        if (lines[i].end + RATE * 3 / 10 > pos) return lines[i].start;
    return H->total;
}

int lecture_heard(uint32_t pos, char *out, size_t cap)
{
    /* the last ~30 lines the listener has heard, for the tutor's context */
    int last = -1;
    for (int i = 0; i < H->n_lines; i++)
        if (lines[i].start <= pos) last = i;
    size_t n = 0;
    out[0] = 0;
    for (int i = last - 29 < 0 ? 0 : last - 29; i <= last && n + 2 < cap; i++)
        n += snprintf(out + n, cap - n, "%s\n", strings + lines[i].text);
    return n;
}

/* ---------------------------------------------------------------- video (FQV) */

static uint8_t *blob, *tiles;
static size_t blob_cap;
static tinfl_decompressor *inflator;

/* Decode one FQV frame into the framebuffer. Caller holds the UI lock. */
static void decode(int s, uint32_t off, uint32_t len, bool invalidate)
{
    if (len < 2 + BITMAP) return;
    if (len > blob_cap) {
        free(blob);
        blob_cap = len + 4096;
        blob = heap_caps_malloc(blob_cap, MALLOC_CAP_SPIRAM);
    }
    if (!tiles) tiles = heap_caps_malloc(GRID * GRID * TILE * TILE, MALLOC_CAP_SPIRAM);
    if (!inflator) inflator = heap_caps_malloc(sizeof(tinfl_decompressor), MALLOC_CAP_SPIRAM);
    if (!blob || !tiles || !inflator) return;
    rd(off, blob, len);
    uint16_t n;
    memcpy(&n, blob, 2);
    if (!n) return;
    size_t in_sz = len - 2 - BITMAP, out_sz = (size_t)n * TILE * TILE;
    tinfl_init(inflator);
    tinfl_status st = tinfl_decompress(inflator, blob + 2 + BITMAP, &in_sz, tiles, tiles, &out_sz,
                                       TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
    if (st != TINFL_STATUS_DONE || out_sz != (size_t)n * TILE * TILE) {
        ESP_LOGW(TAG, "bad frame in scene %d (%d)", s, st);
        return;
    }
    const uint16_t *pal = palettes[s];
    uint16_t *fb = ui_framebuffer();
    const uint8_t *src = tiles;
    const uint8_t *bm = blob + 2;
    for (int t = 0; t < GRID * GRID; t++) {
        if (!(bm[t >> 3] & (1 << (t & 7)))) continue;
        int tx = (t % GRID) * TILE, ty = (t / GRID) * TILE;
        for (int row = 0; row < TILE; row++) {
            uint16_t *dst = fb + (ty + row) * IMG_W + tx;
            for (int col = 0; col < TILE; col++) dst[col] = pal[*src++];
        }
        if (invalidate) {
            lv_area_t a = {.x1 = tx, .y1 = ty, .x2 = tx + TILE - 1, .y2 = ty + TILE - 1};
            lv_obj_invalidate_area(ui_image(), &a);
        }
    }
}

void video_apply(int s, int k)
{
    if (s < 0 || s >= H->n_scenes || k < 0 || k >= (int)scenes[s].frames) return;
    ui_lock();
    decode(s, indexes[s][k], indexes[s][k + 1] - indexes[s][k], true);
    ui_unlock();
}

void video_seek(int s, int k)
{
    if (s < 0 || s >= H->n_scenes) return;
    if (k >= (int)scenes[s].frames) k = scenes[s].frames - 1;
    ui_lock();
    for (int j = 0; j <= k; j++)                       /* frame 0 is a keyframe; replay the deltas up to k */
        decode(s, indexes[s][j], indexes[s][j + 1] - indexes[s][j], false);
    lv_obj_invalidate(ui_image());
    ui_unlock();
}

void video_final(int s)
{
    if (s < 0 || s >= H->n_scenes) return;
    ui_lock();
    decode(s, scenes[s].final_off, scenes[s].final_len, false);
    lv_obj_invalidate(ui_image());
    ui_unlock();
}

/* ---------------------------------------------------------------- producer */

static int scene_at(uint32_t pos)
{
    int s = 0;
    for (int i = 0; i < H->n_scenes; i++)
        if (scenes[i].start <= pos) s = i;
    return s;
}

static uint32_t frame_pos(int s, uint32_t k)
{
    return scenes[s].start + (uint32_t)((uint64_t)k * H->rate / H->fps);
}

static void run(uint32_t from, uint32_t g)
{
    static HMP3Decoder mp3;
    static int16_t pcm[1152];
    static uint8_t abuf[144 * 32];
    if (!mp3) mp3 = MP3InitDecoder();

    const uint32_t fs = H->mp3_samples, fb = H->mp3_bytes, nframes = H->audio_len / fb;
    uint32_t start = line_start(from);
    uint32_t fi = start / fs;
    start = fi * fs;
    int s = scene_at(start);
    uint32_t k = 0;
    if (start > scenes[s].start)
        k = (uint32_t)(((uint64_t)(start - scenes[s].start) * H->fps + H->rate - 1) / H->rate);
    if (k >= scenes[s].frames) k = scenes[s].frames - 1;
    int si = 0;
    while (si < H->n_subs && subs[si].at < start) si++;

    ESP_LOGI(TAG, "play from %.1fs (scene %d frame %lu)", start / (float)H->rate, s, (unsigned long)k);
    play_mode(MODE_LECTURE);
    play_key(s, k);
    k++;
    uint32_t chunk0 = UINT32_MAX;

    for (; fi < nframes && g == play_gen; fi++) {
        uint32_t a_pos = fi * fs, a_end = a_pos + fs;
        while (si < H->n_subs && subs[si].at < a_end) play_sub(strings + subs[si++].text);
        for (;;) {                                        /* animation frames due before this audio ends */
            if (k < scenes[s].frames && frame_pos(s, k) < scenes[s].end) {
                if (frame_pos(s, k) >= a_end) break;
                play_frame(s, k++);
            } else if (s + 1 < H->n_scenes && scenes[s + 1].start < a_end) {
                s++;
                k = 0;
                play_key(s, k++);
            } else {
                break;
            }
        }
        if (chunk0 == UINT32_MAX || fi >= chunk0 + 32) {  /* read 32 MP3 frames at a time */
            chunk0 = fi;
            uint32_t n = nframes - fi < 32 ? nframes - fi : 32;
            rd(H->audio_off + fi * fb, abuf, n * fb);
        }
        unsigned char *in = abuf + (fi - chunk0) * fb;
        int left = fb;
        if (MP3Decode(mp3, &in, &left, pcm, 0) == ERR_MP3_NONE) play_audio(a_pos, pcm, fs);
        while (queued_samples > RATE * 6 / 10 && g == play_gen) vTaskDelay(pdMS_TO_TICKS(10));
    }
    if (g == play_gen) play_mode(MODE_DONE);
}

static void producer_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        uint32_t g = play_gen;
        running = true;
        run(req_pos, g);
        running = false;
    }
}

void lecture_play(uint32_t from_pos)
{
    if (!H) return;
    if (!producer) xTaskCreatePinnedToCore(producer_task, "lecture", 8192, NULL, 6, &producer, 0);
    play_gen++;
    req_pos = from_pos;
    xTaskNotifyGive(producer);
}

/* Stop feeding the queue and wait until the producer has really let go, so a flush right after
 * this can't be followed by a stale item. */
void lecture_stop(void)
{
    play_gen++;
    for (int i = 0; i < 40 && running; i++) vTaskDelay(pdMS_TO_TICKS(5));
}

/* ---------------------------------------------------------------- timeline helpers (scrubbing) */

int lecture_scene_at(uint32_t pos) { return H ? scene_at(pos) : 0; }
uint32_t lecture_scene_start(int i) { return scenes[i].start; }
uint32_t lecture_line_start(uint32_t pos) { return H ? line_start(pos) : 0; }

const char *lecture_scene_name(int i)
{
    static char name[24];
    const char *id = scenes[i].id, *dash = strchr(id, '-');
    strlcpy(name, dash ? dash + 1 : id, sizeof(name));
    for (char *c = name; *c; c++)
        if (*c == '-') *c = ' ';
    if (name[0] >= 'a' && name[0] <= 'z') name[0] -= 32;
    return name;
}

void lecture_preview(uint32_t pos)
{
    if (!H) return;
    uint32_t start = line_start(pos);
    int s = scene_at(start);
    uint32_t k = start > scenes[s].start
                     ? (uint32_t)(((uint64_t)(start - scenes[s].start) * H->fps + H->rate - 1) / H->rate) : 0;
    play_key(s, k);
    const char *text = "";
    for (int i = 0; i < H->n_subs && subs[i].at <= start; i++) text = strings + subs[i].text;
    play_sub(text);
}
