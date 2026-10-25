/*
 * Questions, answered on the board itself:
 *   listen (adaptive voice detection) -> OpenRouter speech-to-text (Deepgram Nova-3)
 *   -> Claude via OpenRouter (tutor in Feynman's style, knows what you've heard so far)
 *   -> OpenRouter voice (Deepgram Aura-2 "Draco", British), streamed sentence by sentence
 * then the lecture resumes at the start of the line it was interrupted on.
 */
#include <math.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "cJSON.h"
#include "app.h"
#include "secrets.h"

static const char *TAG = "ask";

#define OR_BASE    "https://openrouter.ai/api/v1"
#define STT_MODEL  "deepgram/nova-3"
#define LLM_MODEL  "anthropic/claude-opus-5.5"
#define TTS_MODEL  "deepgram/aura-2"
#define TTS_VOICE  "aura-2-draco-en"
#define MAX_REC_S  20
#define FRAME      1600            /* 100 ms at 16 kHz */

static const char *SYSTEM_PROMPT =
    "You are a tutor speaking in the voice and teaching style of Richard Feynman, partway through a "
    "lecture to one student, who pressed a button to interrupt and ask a question out loud.\n"
    "- Talk, don't write: your words are spoken by a voice and shown as subtitles.\n"
    "- 2 to 4 short sentences, under 70 words. Plain words, concrete images, a little humor is fine.\n"
    "- No markdown, lists, symbols or equations; say 'phi one', 'squared', 'h-bar'.\n"
    "- Answer what they asked. If it's unclear or just noise, say briefly you didn't catch it.\n"
    "- If it helps, pick one of the lecture's diagrams to show while you answer.\n"
    "- Don't claim to be the real Richard Feynman; you're a tutor in his style.\n"
    "Reply with JSON only: {\"answer\": \"...\", \"visual\": \"<diagram id or null>\"}";

static TaskHandle_t task;
static volatile uint32_t gen;
static volatile bool done_talking;
static uint32_t resume_pos;
static int16_t *rec;
static char *history[3][2];

void ask_begin(uint32_t pos)
{
    gen++;
    resume_pos = pos;
    done_talking = false;
    xTaskNotifyGive(task);
}

void ask_done_talking(void) { done_talking = true; }
void ask_cancel(void) { gen++; }

/* ---------------------------------------------------------------- helpers */

static void say(const char *text)            /* a subtitle right now, outside the play queue */
{
    ui_lock();
    ui_set_sub(text);
    ui_unlock();
}

static void set_mode(app_mode_t m)
{
    ui_lock();
    ui_set_mode(m);
    ui_unlock();
}

/* The board's fonts are ASCII: fold curly quotes and dashes, drop anything else non-ASCII. */
static void ascii_fold(char *s)
{
    static const struct { const char *u, *a; } map[] = {
        {"\xe2\x80\x99", "'"}, {"\xe2\x80\x98", "'"}, {"\xe2\x80\x9c", "\""}, {"\xe2\x80\x9d", "\""},
        {"\xe2\x80\x94", " - "}, {"\xe2\x80\x93", "-"}, {"\xe2\x80\xa6", "..."},
    };
    char *r = s, *w = s;
    while (*r) {
        bool hit = false;
        for (size_t i = 0; i < sizeof(map) / sizeof(map[0]); i++) {
            size_t n = strlen(map[i].u);
            if (!strncmp(r, map[i].u, n)) {
                size_t m = strlen(map[i].a);
                if (w + m <= r + n) {
                    memcpy(w, map[i].a, m);
                    w += m;
                }
                r += n;
                hit = true;
                break;
            }
        }
        if (hit) continue;
        if ((unsigned char)*r < 0x80) *w++ = *r;
        r++;
    }
    *w = 0;
}

typedef struct {
    char *buf;
    size_t len, cap;
} body_t;

static void body_add(body_t *b, const void *data, size_t n)
{
    if (b->len + n + 1 > b->cap) {
        size_t cap = (b->len + n + 1) * 2;
        char *nb = heap_caps_realloc(b->buf, cap, MALLOC_CAP_SPIRAM);
        if (!nb) return;
        b->buf = nb;
        b->cap = cap;
    }
    memcpy(b->buf + b->len, data, n);
    b->len += n;
    b->buf[b->len] = 0;
}

typedef void (*chunk_fn)(const uint8_t *data, int n, void *ctx);

/* POST to OpenRouter. The response either accumulates in `out` or streams through `on_chunk`. */
static int post(const char *path, const char *ctype, const void *body, size_t blen, body_t *out,
                chunk_fn on_chunk, void *ctx, uint32_t g)
{
    char url[96];
    snprintf(url, sizeof(url), OR_BASE "%s", path);
    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 30000,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .buffer_size = 4096,
        .buffer_size_tx = 2048,
    };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    esp_http_client_set_header(c, "Authorization", "Bearer " OPENROUTER_API_KEY);
    esp_http_client_set_header(c, "Content-Type", ctype);
    esp_http_client_set_header(c, "X-Title", "Feynman tutor (ESP32)");
    int status = -1;
    if (esp_http_client_open(c, blen) == ESP_OK) {
        size_t sent = 0;
        while (sent < blen) {
            int w = esp_http_client_write(c, (const char *)body + sent, blen - sent);
            if (w <= 0) break;
            sent += w;
        }
        esp_http_client_fetch_headers(c);
        status = esp_http_client_get_status_code(c);
        static uint8_t chunk[4096];
        int n;
        while (g == gen && (n = esp_http_client_read(c, (char *)chunk, sizeof(chunk))) > 0) {
            if (on_chunk && status == 200) on_chunk(chunk, n, ctx);
            else if (out) body_add(out, chunk, n);
        }
    }
    esp_http_client_cleanup(c);
    if (status != 200) ESP_LOGW(TAG, "%s -> HTTP %d %s", path, status, out && out->buf ? out->buf : "");
    return status;
}

/* ---------------------------------------------------------------- 1. listen */

static int cmp_float(const void *a, const void *b)
{
    float x = *(const float *)a, y = *(const float *)b;
    return x < y ? -1 : x > y;
}

/* Records into `rec` until the speaker pauses, presses again, or time runs out. Returns samples,
 * and whether it heard anything that stood out from the room. */
static size_t record_question(uint32_t g, bool *heard)
{
    static int16_t stereo[FRAME * 2];
    float levels[MAX_REC_S * 10];
    int nl = 0, speech_frames = 0;
    size_t n = 0;
    TickType_t t0 = xTaskGetTickCount(), last_voice = 0;
    bool started = false;
    float peak = 0;
    esp_codec_dev_read(mic, stereo, sizeof(stereo));          /* drop what sat in the DMA buffer */
    while (g == gen && !done_talking && n + FRAME <= (size_t)RATE * MAX_REC_S) {
        if (esp_codec_dev_read(mic, stereo, sizeof(stereo)) != ESP_CODEC_DEV_OK) continue;
        double e = 0;
        for (int i = 0; i < FRAME; i++) {
            int32_t m = stereo[2 * i] + stereo[2 * i + 1];       /* two mics summed */
            m = m > 32767 ? 32767 : m < -32768 ? -32768 : m;
            rec[n + i] = m;
            e += (double)m * m;
        }
        n += FRAME;
        float rms = sqrtf(e / FRAME);
        TickType_t now = xTaskGetTickCount();
        if (now - t0 < pdMS_TO_TICKS(250)) continue;
        levels[nl++] = rms;
        if (rms > peak) peak = rms;
        if (nl < 5) continue;
        float sorted[MAX_REC_S * 10];
        memcpy(sorted, levels, nl * sizeof(float));
        qsort(sorted, nl, sizeof(float), cmp_float);
        float floor_ = sorted[nl / 5];                          /* the quiet 20% is the room */
        float thresh = fmaxf(1.8f * floor_, floor_ + 80.0f);
        if (rms > thresh) {
            started = true;
            speech_frames++;
            last_voice = now;
        }
        if (started && now - last_voice > pdMS_TO_TICKS(1500)) break;
        if (!started && now - t0 > pdMS_TO_TICKS(8000)) break;
    }
    *heard = started && speech_frames >= 2;
    ESP_LOGI(TAG, "recorded %.1fs, peak %.0f, speech %d", n / (float)RATE, peak, speech_frames);
    return n;
}

/* Scale up to a healthy level (the mics are quiet) and wrap as a WAV file. */
static uint8_t *make_wav(size_t n, size_t *len)
{
    int32_t peak = 1;
    int64_t mean = 0;
    for (size_t i = 0; i < n; i++) mean += rec[i];
    mean /= (int64_t)(n ? n : 1);
    for (size_t i = 0; i < n; i++) {
        int32_t v = abs(rec[i] - (int32_t)mean);
        if (v > peak) peak = v;
    }
    float gain = fminf(30.0f, 23000.0f / peak);
    *len = 44 + n * 2;
    uint8_t *w = heap_caps_malloc(*len, MALLOC_CAP_SPIRAM);
    if (!w) return NULL;
    uint32_t sr = RATE, br = RATE * 2, data = n * 2, riff = 36 + data;
    uint16_t pcm = 1, ch = 1, align = 2, bits = 16;
    memcpy(w, "RIFF", 4); memcpy(w + 4, &riff, 4); memcpy(w + 8, "WAVEfmt ", 8);
    uint32_t fmt = 16;
    memcpy(w + 16, &fmt, 4); memcpy(w + 20, &pcm, 2); memcpy(w + 22, &ch, 2); memcpy(w + 24, &sr, 4);
    memcpy(w + 28, &br, 4); memcpy(w + 32, &align, 2); memcpy(w + 34, &bits, 2);
    memcpy(w + 36, "data", 4); memcpy(w + 40, &data, 4);
    int16_t *out = (int16_t *)(w + 44);
    for (size_t i = 0; i < n; i++) {
        float v = (rec[i] - mean) * gain;
        out[i] = v > 32767 ? 32767 : v < -32768 ? -32768 : (int16_t)v;
    }
    return w;
}

/* ---------------------------------------------------------------- 2. transcribe, think */

static char *transcribe(const uint8_t *wav, size_t wlen, uint32_t g)
{
    static const char *B = "feynmanboundary7MA4YWxkTrZu0gW";
    body_t req = {0}, resp = {0};
    char head[256];
    int hn = snprintf(head, sizeof(head),
                      "--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n" STT_MODEL "\r\n"
                      "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"q.wav\"\r\n"
                      "Content-Type: audio/wav\r\n\r\n", B, B);
    body_add(&req, head, hn);
    body_add(&req, wav, wlen);
    hn = snprintf(head, sizeof(head), "\r\n--%s--\r\n", B);
    body_add(&req, head, hn);
    char ctype[80];
    snprintf(ctype, sizeof(ctype), "multipart/form-data; boundary=%s", B);
    int st = post("/audio/transcriptions", ctype, req.buf, req.len, &resp, NULL, NULL, g);
    free(req.buf);
    char *text = NULL;
    if (st == 200 && resp.buf) {
        cJSON *j = cJSON_Parse(resp.buf);
        const char *t = cJSON_GetStringValue(cJSON_GetObjectItem(j, "text"));
        if (t) text = strdup(t);
        cJSON_Delete(j);
    }
    free(resp.buf);
    return text;
}

static bool think(const char *question, uint32_t pos, char **answer, int *scene, uint32_t g)
{
    char *heard = heap_caps_malloc(6000, MALLOC_CAP_SPIRAM);
    lecture_heard(pos, heard, 6000);
    body_t prompt = {0};
    char line[320];
    int n = snprintf(line, sizeof(line), "Lecture: %s\n\nDiagrams you can show:\n", lecture_title());
    body_add(&prompt, line, n);
    for (int i = 0; i < lecture_scene_count(); i++) {
        n = snprintf(line, sizeof(line), "- %s: %s\n", lecture_scene_id(i), lecture_scene_desc(i));
        body_add(&prompt, line, n);
    }
    body_add(&prompt, "\nWhat the student has heard so far:\n", 36);
    body_add(&prompt, heard, strlen(heard));
    body_add(&prompt, "\nEarlier questions in this session:\n", 36);
    for (int i = 0; i < 3; i++)
        if (history[i][0]) {
            n = snprintf(line, sizeof(line), "Student: %.120s\nTutor: %.180s\n", history[i][0], history[i][1]);
            body_add(&prompt, line, n);
        }
    n = snprintf(line, sizeof(line), "\nThe student asks: \"%.250s\"", question);
    body_add(&prompt, line, n);
    free(heard);

    cJSON *req = cJSON_CreateObject();
    cJSON_AddStringToObject(req, "model", LLM_MODEL);
    cJSON_AddNumberToObject(req, "max_tokens", 400);
    cJSON *reasoning = cJSON_AddObjectToObject(req, "reasoning");
    cJSON_AddStringToObject(reasoning, "effort", "low");
    cJSON_AddBoolToObject(reasoning, "exclude", true);
    cJSON *msgs = cJSON_AddArrayToObject(req, "messages");
    cJSON *sys = cJSON_CreateObject();
    cJSON_AddStringToObject(sys, "role", "system");
    cJSON_AddStringToObject(sys, "content", SYSTEM_PROMPT);
    cJSON_AddItemToArray(msgs, sys);
    cJSON *usr = cJSON_CreateObject();
    cJSON_AddStringToObject(usr, "role", "user");
    cJSON_AddStringToObject(usr, "content", prompt.buf);
    cJSON_AddItemToArray(msgs, usr);
    char *json = cJSON_PrintUnformatted(req);
    cJSON_Delete(req);
    free(prompt.buf);

    body_t resp = {0};
    int st = post("/chat/completions", "application/json", json, strlen(json), &resp, NULL, NULL, g);
    free(json);
    bool ok = false;
    *answer = NULL;
    *scene = -1;
    if (st == 200 && resp.buf) {
        cJSON *j = cJSON_Parse(resp.buf);
        cJSON *msg = cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(j, "choices"), 0), "message");
        const char *content = cJSON_GetStringValue(cJSON_GetObjectItem(msg, "content"));
        if (content) {
            const char *a = strchr(content, '{'), *b = strrchr(content, '}');
            cJSON *inner = (a && b && b > a) ? cJSON_ParseWithLength(a, b - a + 1) : NULL;
            const char *ans = cJSON_GetStringValue(cJSON_GetObjectItem(inner, "answer"));
            *answer = strdup(ans ? ans : content);
            *scene = lecture_scene_find(cJSON_GetStringValue(cJSON_GetObjectItem(inner, "visual")));
            cJSON_Delete(inner);
            ok = true;
        }
        cJSON_Delete(j);
    }
    free(resp.buf);
    return ok;
}

/* ---------------------------------------------------------------- 3. speak */

typedef struct {
    int16_t carry[3];
    int nc;
    uint8_t odd;
    bool has_odd;
} resampler_t;

/* Aura returns 24 kHz PCM; the speaker runs at 16 kHz: every 3 samples in become 2 out. */
static void on_tts(const uint8_t *data, int n, void *ctx)
{
    resampler_t *r = ctx;
    static int16_t in[2200], out[1500];
    int ni = 0, no = 0;
    if (r->has_odd && n > 0) {                      /* a sample split across two network chunks */
        uint8_t b[2] = {r->odd, data[0]};
        memcpy(&in[ni++], b, 2);
        data++;
        n--;
        r->has_odd = false;
    }
    for (int i = 0; i < r->nc; i++) in[ni++] = r->carry[i];
    r->nc = 0;
    int whole = n / 2;
    memcpy(in + ni, data, whole * 2);
    ni += whole;
    if (n & 1) {
        r->odd = data[n - 1];
        r->has_odd = true;
    }
    int i = 0;
    for (; i + 3 <= ni; i += 3) {
        out[no++] = in[i];
        out[no++] = (int16_t)((in[i + 1] + in[i + 2]) / 2);
    }
    for (; i < ni; i++) r->carry[r->nc++] = in[i];
    if (no) play_audio(ANSWER_POS, out, no);
}

static void speak(const char *sentence, uint32_t g)
{
    cJSON *req = cJSON_CreateObject();
    cJSON_AddStringToObject(req, "model", TTS_MODEL);
    cJSON_AddStringToObject(req, "input", sentence);
    cJSON_AddStringToObject(req, "voice", TTS_VOICE);
    cJSON_AddStringToObject(req, "response_format", "pcm");
    char *json = cJSON_PrintUnformatted(req);
    cJSON_Delete(req);
    resampler_t r = {0};
    post("/audio/speech", "application/json", json, strlen(json), NULL, on_tts, &r, g);
    free(json);
    static const int16_t gap[RATE / 5] = {0};       /* a breath between sentences */
    play_audio(ANSWER_POS, gap, RATE / 5);
}

/* ---------------------------------------------------------------- flow */

static void back_to_lecture(uint32_t g, const char *why)
{
    if (why) {
        say(why);
        vTaskDelay(pdMS_TO_TICKS(1800));
    }
    if (g == gen) {
        say("");
        lecture_play(resume_pos);
    }
}

static void flow(uint32_t g)
{
    bool heard = false;
    size_t n = record_question(g, &heard);
    if (g != gen) return;
    set_mode(MODE_THINKING);
    if (!heard) {
        back_to_lecture(g, "(didn't catch that)");
        return;
    }
    if (!net_online()) {
        back_to_lecture(g, "Questions need Wi-Fi. Back to the lecture.");
        return;
    }

    size_t wlen;
    uint8_t *wav = make_wav(n, &wlen);
    TickType_t t0 = xTaskGetTickCount();
    char *q = wav ? transcribe(wav, wlen, g) : NULL;
    free(wav);
    if (g != gen) {
        free(q);
        return;
    }
    if (!q || strlen(q) < 2) {
        free(q);
        back_to_lecture(g, "(didn't catch that)");
        return;
    }
    char shown[300];
    snprintf(shown, sizeof(shown), "\"%.290s\"", q);
    ascii_fold(shown);
    say(shown);
    ESP_LOGI(TAG, "heard (%lums): %s", (unsigned long)pdTICKS_TO_MS(xTaskGetTickCount() - t0), q);

    char *answer = NULL;
    int scene = -1;
    bool ok = think(q, resume_pos, &answer, &scene, g);
    ESP_LOGI(TAG, "answer (%lums, scene %d): %s", (unsigned long)pdTICKS_TO_MS(xTaskGetTickCount() - t0),
             scene, answer ? answer : "-");
    if (g != gen || !ok || !answer) {
        free(q);
        free(answer);
        if (g == gen) back_to_lecture(g, "Couldn't reach the tutor. Back to the lecture.");
        return;
    }

    play_mode(MODE_ANSWERING);
    if (scene >= 0) play_final(scene);
    char *s = answer;
    while (*s && g == gen) {                        /* one sentence at a time: subtitle, then its voice */
        while (*s == ' ') s++;
        char *e = s;
        while (*e && !((*e == '.' || *e == '?' || *e == '!') && (e[1] == ' ' || e[1] == 0))) e++;
        if (*e) e++;
        char save = *e;
        *e = 0;
        if (*s) {
            char sub[400];
            strlcpy(sub, s, sizeof(sub));
            ascii_fold(sub);
            play_sub(sub);
            speak(s, g);
        }
        *e = save;
        s = e;
    }
    play_sub("");
    while (g == gen && queued_samples > 0) vTaskDelay(pdMS_TO_TICKS(50));   /* let the answer finish */

    free(history[2][0]);
    free(history[2][1]);
    memmove(history[1], history[0], sizeof(history[0]) * 2);
    history[0][0] = q;
    history[0][1] = answer;
    if (g == gen) lecture_play(resume_pos);
}

static void ask_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        flow(gen);
    }
}

void ask_init(void)
{
    rec = heap_caps_malloc(RATE * MAX_REC_S * 2, MALLOC_CAP_SPIRAM);
    /* TLS needs a deep stack; keep it in PSRAM so internal RAM stays free for Wi-Fi */
    xTaskCreatePinnedToCoreWithCaps(ask_task, "ask", 16384, NULL, 5, &task, 0, MALLOC_CAP_SPIRAM);
}
