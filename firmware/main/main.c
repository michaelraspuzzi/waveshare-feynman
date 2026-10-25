/*
 * Feynman tutor for the Waveshare ESP32-S3-Touch-AMOLED-2.16: UI, controls, home screen.
 *
 *   side button (GPIO18)   press: ask (stops when you pause; press again to finish early)
 *                          or hold while you talk and let go
 *   tap the screen         pause / play
 *   drag left / right      rewind / fast-forward, with a timeline and chapter preview
 *   two swipes up          home (pauses; the card resumes where you were)
 *   BOOT button            tap: volume 40 / 60 / 75 / 90 / 100 %    hold 1.5 s: home
 *
 * See app.h for how the pieces fit together.
 */
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"
#include "bsp/esp-bsp.h"
#include "app.h"

static const char *TAG = "feynman";

#define ASK_GPIO    GPIO_NUM_18   /* user key */
#define VOLUME_GPIO GPIO_NUM_0    /* BOOT key (only read after boot) */

volatile app_mode_t mode = MODE_IDLE;
esp_codec_dev_handle_t spk, mic;

static TaskHandle_t button_task_handle;
static void timeline_hide(void);
static void scrub_init(lv_obj_t *scr);
static uint16_t *fb;
static lv_image_dsc_t fb_dsc;
static lv_obj_t *img, *sub_label, *mode_label, *note_label, *vol_label;
static lv_obj_t *home_panel, *home_resume, *home_net;
static lv_timer_t *note_timer, *vol_timer;
static uint32_t saved_pos;
static bool have_lecture;

/* ------------------------------------------------------------------ UI helpers */

void ui_lock(void) { bsp_display_lock(UINT32_MAX); }
void ui_unlock(void) { bsp_display_unlock(); }
uint16_t *ui_framebuffer(void) { return fb; }
lv_obj_t *ui_image(void) { return img; }

void ui_set_sub(const char *text) { lv_label_set_text(sub_label, text); }

void ui_set_mode(app_mode_t m)
{
    static const char *names[] = {"", "", "LISTENING", "THINKING", "ANSWERING", "THE END", "", "PAUSED"};
    static const uint32_t colors[] = {0, 0, 0xff8a8a, 0xb993ff, 0x7be38f, 0x8a8983, 0, 0xe8e6e1};
    if (mode == MODE_HOME && m != MODE_HOME) return;     /* paused: stale queue items can't take over */
    mode = m;
    if (names[m][0]) {
        lv_label_set_text(mode_label, names[m]);
        lv_obj_set_style_text_color(mode_label, lv_color_hex(colors[m]), 0);
        lv_obj_remove_flag(mode_label, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(mode_label, LV_OBJ_FLAG_HIDDEN);
    }
}

static void hide_cb(lv_timer_t *t) { lv_obj_add_flag((lv_obj_t *)lv_timer_get_user_data(t), LV_OBJ_FLAG_HIDDEN); }

/* Show a label for a moment (lock held). */
static void flash_label(lv_obj_t *label, lv_timer_t **timer, int ms)
{
    lv_obj_remove_flag(label, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(label);
    if (!*timer) {
        *timer = lv_timer_create(hide_cb, ms, label);
        lv_timer_set_auto_delete(*timer, false);
    }
    lv_timer_set_period(*timer, ms);
    lv_timer_set_repeat_count(*timer, 1);
    lv_timer_reset(*timer);
    lv_timer_resume(*timer);
}

void ui_note(const char *text)
{
    ui_lock();
    lv_label_set_text(note_label, text);
    flash_label(note_label, &note_timer, 2200);
    ui_unlock();
}

/* ------------------------------------------------------------------ position memory */

static void save_pos(uint32_t pos)
{
    nvs_handle_t h;
    if (nvs_open("feynman", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_u32(h, "pos", pos);
        nvs_commit(h);
        nvs_close(h);
    }
    saved_pos = pos;
}

/* ------------------------------------------------------------------ home screen */

static void refresh_home(void)   /* lock held */
{
    unsigned at = saved_pos / RATE, total = lecture_total() / RATE;
    if (!have_lecture)
        lv_label_set_text(home_resume, "lecture data missing - flash lecture.fqv");
    else if (saved_pos > RATE * 2)
        lv_label_set_text_fmt(home_resume, "resume  %u:%02u / %u:%02u", at / 60, at % 60, total / 60, total % 60);
    else
        lv_label_set_text_fmt(home_resume, "tap to start  -  %u:%02u", total / 60, total % 60);
    if (net_online())
        lv_label_set_text_fmt(home_net, "Wi-Fi: %s  -  questions on", net_name());
    else
        lv_label_set_text(home_net, "offline  -  lecture only");
}

static void go_home(void)       /* lock held (LVGL callbacks) */
{
    if (mode == MODE_HOME) return;
    lecture_stop();
    ask_cancel();
    play_flush();
    if (played_pos) save_pos(played_pos);
    ui_set_mode(MODE_HOME);
    ui_set_sub("");
    timeline_hide();
    refresh_home();
    lv_obj_remove_flag(home_panel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(home_panel);
    ESP_LOGI(TAG, "home (at %.1fs)", saved_pos / (float)RATE);
}

static void leave_home(uint32_t from)
{
    if (!have_lecture) return;
    lv_obj_add_flag(home_panel, LV_OBJ_FLAG_HIDDEN);
    ui_set_sub("");
    mode = MODE_IDLE;
    lecture_play(from);
}

static void resume_clicked(lv_event_t *e) { leave_home(saved_pos); }
static void restart_clicked(lv_event_t *e) { save_pos(0); leave_home(0); }

static void home_timer_cb(lv_timer_t *t) { go_home(); }

void app_lecture_done(void)
{
    save_pos(0);
    ui_lock();
    lv_timer_t *t = lv_timer_create(home_timer_cb, 4000, NULL);
    lv_timer_set_repeat_count(t, 1);
    ui_unlock();
}

static lv_obj_t *home_button(lv_obj_t *parent, int w, int h, uint32_t border)
{
    lv_obj_t *b = lv_button_create(parent);
    lv_obj_set_size(b, w, h);
    lv_obj_set_style_bg_color(b, lv_color_hex(0x121216), 0);
    lv_obj_set_style_bg_color(b, lv_color_hex(0x24203a), LV_STATE_PRESSED);
    lv_obj_set_style_border_color(b, lv_color_hex(border), 0);
    lv_obj_set_style_border_width(b, 2, 0);
    lv_obj_set_style_radius(b, 22, 0);
    lv_obj_set_style_shadow_width(b, 0, 0);
    return b;
}

static lv_obj_t *text_label(lv_obj_t *parent, const lv_font_t *font, uint32_t color, const char *text)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
    lv_label_set_text(l, text);
    return l;
}

static void home_init(lv_obj_t *scr)
{
    home_panel = lv_obj_create(scr);
    lv_obj_set_size(home_panel, IMG_W, IMG_W);
    lv_obj_set_pos(home_panel, 0, 0);
    lv_obj_set_style_bg_color(home_panel, lv_color_black(), 0);
    lv_obj_set_style_border_width(home_panel, 0, 0);
    lv_obj_set_style_radius(home_panel, 0, 0);
    lv_obj_remove_flag(home_panel, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_align(text_label(home_panel, &lv_font_montserrat_28, 0xb993ff, "Feynman Tutor"), LV_ALIGN_TOP_MID, 0, 52);

    lv_obj_t *card = home_button(home_panel, 392, 132, 0xb993ff);
    lv_obj_align(card, LV_ALIGN_CENTER, 0, -30);
    lv_obj_add_event_cb(card, resume_clicked, LV_EVENT_CLICKED, NULL);
    lv_obj_align(text_label(card, &lv_font_montserrat_28, 0xe8e6e1, "Quantum Behavior"), LV_ALIGN_TOP_LEFT, 6, 12);
    home_resume = text_label(card, &lv_font_montserrat_16, 0x8a8983, "");
    lv_obj_align(home_resume, LV_ALIGN_BOTTOM_LEFT, 6, -14);

    lv_obj_t *again = home_button(home_panel, 200, 52, 0x55545a);
    lv_obj_align(again, LV_ALIGN_CENTER, 0, 86);
    lv_obj_add_event_cb(again, restart_clicked, LV_EVENT_CLICKED, NULL);
    lv_obj_center(text_label(again, &lv_font_montserrat_16, 0xe8e6e1, "Start over"));

    home_net = text_label(home_panel, &lv_font_montserrat_16, 0x7be38f, "");
    lv_obj_align(home_net, LV_ALIGN_BOTTOM_MID, 0, -78);
    lv_obj_align(text_label(home_panel, &lv_font_montserrat_16, 0x55545a, "ask: side button  -  pause: tap  -  seek: drag"),
                 LV_ALIGN_BOTTOM_MID, 0, -46);
}

/* ------------------------------------------------------------------ pause, scrub, timeline
 * Tap: pause / play. Drag sideways: scrub (1 px = 0.5 s) with a timeline, a big "-0:15" cue and the
 * chapter name; crossing into another chapter previews its diagram. Let go to jump there.
 * Swipe up twice: home. Touches are logged to check the panel orientation. */

#define SCRUB_SAMPLES_PER_PX (RATE / 2)
#define BAR_X  20
#define BAR_W  400

static lv_obj_t *scrub_panel, *bar_fill, *knob, *time_label, *chap_label, *cue_label, *play_icon;
static lv_point_t press_pt;
static bool swiped, scrubbing, scrub_was_playing;
static uint32_t scrub_from, scrub_to;
static int scrub_scene;
static TickType_t last_swipe_up;

static void mmss(char *out, size_t n, uint32_t samples)
{
    unsigned s = samples / RATE;
    snprintf(out, n, "%u:%02u", s / 60, s % 60);
}

static void timeline_show(uint32_t pos)   /* lock held */
{
    uint32_t total = lecture_total() ? lecture_total() : 1;
    int x = (int)((uint64_t)pos * BAR_W / total);
    lv_obj_set_width(bar_fill, x > 0 ? x : 1);
    lv_obj_set_x(knob, BAR_X + x - 10);
    char a[16], b[16];
    mmss(a, sizeof(a), pos);
    mmss(b, sizeof(b), total);
    lv_label_set_text_fmt(time_label, "%s / %s", a, b);
    lv_label_set_text(chap_label, lecture_scene_name(lecture_scene_at(pos)));
    int cx = BAR_X + x - lv_obj_get_width(chap_label) / 2;
    lv_obj_set_x(chap_label, cx < 8 ? 8 : cx > 440 - lv_obj_get_width(chap_label) ? 440 - lv_obj_get_width(chap_label) : cx);
    lv_obj_add_flag(sub_label, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(scrub_panel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(scrub_panel);
}

static void timeline_hide(void)   /* lock held */
{
    lv_obj_add_flag(scrub_panel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(cue_label, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(play_icon, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(sub_label, LV_OBJ_FLAG_HIDDEN);
}

static void pause_now(void)   /* lock held */
{
    lecture_stop();
    play_flush();
    ui_set_mode(MODE_PAUSED);
    lv_obj_remove_flag(play_icon, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(play_icon);
    timeline_show(played_pos);
    save_pos(played_pos);
}

static void play_now(uint32_t from)   /* lock held */
{
    timeline_hide();
    mode = MODE_IDLE;
    lecture_play(from);
}

static void scrub_begin(void)   /* lock held */
{
    scrub_was_playing = mode == MODE_LECTURE;
    scrub_from = scrub_to = played_pos;
    scrub_scene = lecture_scene_at(played_pos);
    if (scrub_was_playing) {
        lecture_stop();
        play_flush();
        ui_set_mode(MODE_PAUSED);
    }
    lv_obj_add_flag(play_icon, LV_OBJ_FLAG_HIDDEN);
    scrubbing = swiped = true;
}

static void scrub_move(int dx)   /* lock held */
{
    int64_t to = (int64_t)scrub_from + (int64_t)dx * SCRUB_SAMPLES_PER_PX;
    int64_t total = lecture_total();
    scrub_to = to < 0 ? 0 : to > total - RATE ? total - RATE : to;
    timeline_show(scrub_to);
    char t[16];
    int32_t delta = (int32_t)scrub_to - (int32_t)scrub_from;
    mmss(t, sizeof(t), delta < 0 ? -delta : delta);
    if (delta < 0) lv_label_set_text_fmt(cue_label, LV_SYMBOL_PREV " %s", t);
    else lv_label_set_text_fmt(cue_label, "%s " LV_SYMBOL_NEXT, t);
    lv_obj_remove_flag(cue_label, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(cue_label);
    int sc = lecture_scene_at(scrub_to);
    if (sc != scrub_scene) {                          /* show where you're landing */
        scrub_scene = sc;
        play_final(sc);
    }
}

static void scrub_end(void)   /* lock held */
{
    scrubbing = false;
    lv_obj_add_flag(cue_label, LV_OBJ_FLAG_HIDDEN);
    played_pos = lecture_line_start(scrub_to);
    ESP_LOGI(TAG, "scrub %.1fs -> %.1fs", scrub_from / (float)RATE, played_pos / (float)RATE);
    if (scrub_was_playing) {
        play_now(played_pos);
    } else {
        lecture_preview(played_pos);
        lv_obj_remove_flag(play_icon, LV_OBJ_FLAG_HIDDEN);
        timeline_show(played_pos);
        save_pos(played_pos);
    }
}

static void on_swipe_up(void)   /* lock held */
{
    TickType_t now = xTaskGetTickCount();
    if (last_swipe_up && now - last_swipe_up < pdMS_TO_TICKS(1500)) {
        last_swipe_up = 0;
        go_home();
    } else {
        last_swipe_up = now;
        lv_label_set_text(note_label, "swipe up again for home");
        flash_label(note_label, &note_timer, 1500);
    }
}

static void screen_event(lv_event_t *e)
{
    lv_event_code_t code = lv_event_get_code(e);
    lv_point_t p;
    lv_indev_get_point(lv_indev_active(), &p);
    int dx = p.x - press_pt.x, dy = p.y - press_pt.y;
    if (code == LV_EVENT_PRESSED) {
        press_pt = p;
        swiped = scrubbing = false;
    } else if (code == LV_EVENT_PRESSING) {
        if (!scrubbing && (mode == MODE_LECTURE || mode == MODE_PAUSED) && abs(dx) > 24 && abs(dx) > 2 * abs(dy))
            scrub_begin();
        if (scrubbing) scrub_move(dx);
    } else if (code == LV_EVENT_RELEASED) {
        ESP_LOGI(TAG, "touch %d,%d -> %d,%d (dx %d, dy %d)", press_pt.x, press_pt.y, p.x, p.y, dx, dy);
        if (scrubbing) {
            scrub_end();
            return;
        }
        if (abs(dx) > 50 || abs(dy) > 50) swiped = true;
        if (mode != MODE_HOME && dy < -60 && abs(dy) > abs(dx)) on_swipe_up();
    } else if (code == LV_EVENT_CLICKED) {
        if (swiped) return;
        if (mode == MODE_LECTURE) pause_now();
        else if (mode == MODE_PAUSED) play_now(played_pos);
        else if (mode == MODE_LISTENING) ask_done_talking();
    }
}

static void scrub_init(lv_obj_t *scr)
{
    scrub_panel = lv_obj_create(scr);
    lv_obj_set_size(scrub_panel, 440, 86);
    lv_obj_align(scrub_panel, LV_ALIGN_BOTTOM_MID, 0, -14);
    lv_obj_set_style_bg_color(scrub_panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(scrub_panel, LV_OPA_80, 0);
    lv_obj_set_style_border_width(scrub_panel, 0, 0);
    lv_obj_set_style_radius(scrub_panel, 18, 0);
    lv_obj_set_style_pad_all(scrub_panel, 0, 0);
    lv_obj_remove_flag(scrub_panel, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t *bar = lv_obj_create(scrub_panel);                   /* track */
    lv_obj_set_size(bar, BAR_W, 6);
    lv_obj_set_pos(bar, BAR_X, 56);
    lv_obj_set_style_bg_color(bar, lv_color_hex(0x3a3940), 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_radius(bar, 3, 0);
    lv_obj_remove_flag(bar, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    bar_fill = lv_obj_create(scrub_panel);                        /* played part */
    lv_obj_set_size(bar_fill, 1, 6);
    lv_obj_set_pos(bar_fill, BAR_X, 56);
    lv_obj_set_style_bg_color(bar_fill, lv_color_hex(0xb993ff), 0);
    lv_obj_set_style_border_width(bar_fill, 0, 0);
    lv_obj_set_style_radius(bar_fill, 3, 0);
    lv_obj_remove_flag(bar_fill, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    for (int i = 1; i < lecture_scene_count(); i++) {             /* chapter ticks */
        lv_obj_t *tick = lv_obj_create(scrub_panel);
        lv_obj_set_size(tick, 2, 14);
        lv_obj_set_pos(tick, BAR_X + (int)((uint64_t)lecture_scene_start(i) * BAR_W / lecture_total()), 52);
        lv_obj_set_style_bg_color(tick, lv_color_hex(0x8a8983), 0);
        lv_obj_set_style_border_width(tick, 0, 0);
        lv_obj_set_style_radius(tick, 1, 0);
        lv_obj_remove_flag(tick, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    }
    knob = lv_obj_create(scrub_panel);
    lv_obj_set_size(knob, 20, 20);
    lv_obj_set_pos(knob, BAR_X - 10, 49);
    lv_obj_set_style_bg_color(knob, lv_color_white(), 0);
    lv_obj_set_style_border_width(knob, 0, 0);
    lv_obj_set_style_radius(knob, LV_RADIUS_CIRCLE, 0);
    lv_obj_remove_flag(knob, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    chap_label = text_label(scrub_panel, &lv_font_montserrat_16, 0xe8e6e1, "");
    lv_obj_set_pos(chap_label, BAR_X, 14);
    time_label = text_label(scrub_panel, &lv_font_montserrat_16, 0x8a8983, "");
    lv_obj_align(time_label, LV_ALIGN_TOP_RIGHT, -BAR_X, 14);
    lv_obj_add_flag(scrub_panel, LV_OBJ_FLAG_HIDDEN);

    cue_label = text_label(scr, &lv_font_montserrat_28, 0xffffff, "");
    lv_obj_set_style_bg_color(cue_label, lv_color_hex(0x111111), 0);
    lv_obj_set_style_bg_opa(cue_label, LV_OPA_80, 0);
    lv_obj_set_style_pad_hor(cue_label, 22, 0);
    lv_obj_set_style_pad_ver(cue_label, 12, 0);
    lv_obj_set_style_radius(cue_label, 24, 0);
    lv_obj_align(cue_label, LV_ALIGN_CENTER, 0, -30);
    lv_obj_add_flag(cue_label, LV_OBJ_FLAG_HIDDEN);

    play_icon = lv_obj_create(scr);
    lv_obj_set_size(play_icon, 96, 96);
    lv_obj_align(play_icon, LV_ALIGN_CENTER, 0, -30);
    lv_obj_set_style_bg_color(play_icon, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(play_icon, LV_OPA_70, 0);
    lv_obj_set_style_border_color(play_icon, lv_color_white(), 0);
    lv_obj_set_style_border_width(play_icon, 3, 0);
    lv_obj_set_style_radius(play_icon, LV_RADIUS_CIRCLE, 0);
    lv_obj_remove_flag(play_icon, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    lv_obj_t *sym = text_label(play_icon, &lv_font_montserrat_28, 0xffffff, LV_SYMBOL_PLAY);
    lv_obj_align(sym, LV_ALIGN_CENTER, 4, 0);
    lv_obj_add_flag(play_icon, LV_OBJ_FLAG_HIDDEN);
}

static void ui_init(void)
{
    fb = heap_caps_calloc(IMG_W * IMG_W, 2, MALLOC_CAP_SPIRAM);
    fb_dsc = (lv_image_dsc_t){
        .header = {.magic = LV_IMAGE_HEADER_MAGIC, .cf = LV_COLOR_FORMAT_RGB565, .w = IMG_W, .h = IMG_W, .stride = IMG_W * 2},
        .data_size = IMG_W * IMG_W * 2,
        .data = (const uint8_t *)fb,
    };
    ui_lock();
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(scr, LV_OBJ_FLAG_CLICKABLE);

    img = lv_image_create(scr);
    lv_obj_set_pos(img, 0, 0);
    lv_image_set_src(img, &fb_dsc);

    mode_label = text_label(scr, &lv_font_montserrat_16, 0x8a8983, "");
    lv_obj_set_style_text_letter_space(mode_label, 2, 0);
    lv_obj_align(mode_label, LV_ALIGN_TOP_RIGHT, -34, 30);
    lv_obj_add_flag(mode_label, LV_OBJ_FLAG_HIDDEN);

    sub_label = text_label(scr, &lv_font_montserrat_24, 0xe8e6e1, "");
    lv_obj_set_width(sub_label, 420);
    lv_label_set_long_mode(sub_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(sub_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(sub_label, LV_ALIGN_BOTTOM_MID, 0, -22);

    note_label = text_label(scr, &lv_font_montserrat_16, 0xe8e6e1, "");
    lv_obj_set_style_bg_color(note_label, lv_color_hex(0x222222), 0);
    lv_obj_set_style_bg_opa(note_label, LV_OPA_90, 0);
    lv_obj_set_style_pad_all(note_label, 10, 0);
    lv_obj_set_style_radius(note_label, 12, 0);
    lv_obj_align(note_label, LV_ALIGN_TOP_MID, 0, 70);
    lv_obj_add_flag(note_label, LV_OBJ_FLAG_HIDDEN);

    vol_label = text_label(scr, &lv_font_montserrat_28, 0xffffff, "");
    lv_obj_set_style_bg_color(vol_label, lv_color_hex(0x222222), 0);
    lv_obj_set_style_bg_opa(vol_label, LV_OPA_90, 0);
    lv_obj_set_style_pad_all(vol_label, 14, 0);
    lv_obj_set_style_radius(vol_label, 14, 0);
    lv_obj_align(vol_label, LV_ALIGN_TOP_MID, 0, 40);
    lv_obj_add_flag(vol_label, LV_OBJ_FLAG_HIDDEN);

    lv_obj_add_event_cb(scr, screen_event, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(scr, screen_event, LV_EVENT_PRESSING, NULL);
    lv_obj_add_event_cb(scr, screen_event, LV_EVENT_RELEASED, NULL);
    lv_obj_add_event_cb(scr, screen_event, LV_EVENT_CLICKED, NULL);
    home_init(scr);
    ui_unlock();
}

/* ------------------------------------------------------------------ buttons */

static void ask_pressed(void)
{
    if (mode == MODE_HOME || mode == MODE_THINKING || !have_lecture) return;
    if (mode == MODE_LISTENING) {
        ask_done_talking();
        return;
    }
    lecture_stop();
    ask_cancel();
    play_flush();
    ui_lock();
    timeline_hide();
    ui_set_sub("");
    ui_set_mode(MODE_LISTENING);
    ui_unlock();
    ESP_LOGI(TAG, "question at %.1fs", played_pos / (float)RATE);
    ask_begin(played_pos);
}

static const int volumes[] = {40, 60, 75, 90, 100};
static int volume_idx = 2;

static void volume_step(void)
{
    volume_idx = (volume_idx + 1) % (int)(sizeof(volumes) / sizeof(volumes[0]));
    esp_codec_dev_set_out_vol(spk, volumes[volume_idx]);
    nvs_handle_t h;
    if (nvs_open("feynman", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_i32(h, "vol", volume_idx);
        nvs_commit(h);
        nvs_close(h);
    }
    ui_lock();
    lv_label_set_text_fmt(vol_label, "Volume %d%%", volumes[volume_idx]);
    flash_label(vol_label, &vol_timer, 1500);
    ui_unlock();
}

static void button_task(void *arg)
{
    gpio_config_t io = {.pin_bit_mask = (1ULL << ASK_GPIO) | (1ULL << VOLUME_GPIO), .mode = GPIO_MODE_INPUT,
                        .pull_up_en = 1};
    gpio_config(&io);
    vTaskDelay(pdMS_TO_TICKS(20));                               /* let the pull-ups settle */
    const int rest = gpio_get_level(ASK_GPIO);                   /* learn the idle level rather than assume it */
    bool ask_down = false, vol_down = false, vol_held = false;
    TickType_t ask_at = 0, vol_at = 0, last_save = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10));
        TickType_t now = xTaskGetTickCount();

        /* side button: press to ask (it stops when you pause), or hold while talking and release */
        bool down = gpio_get_level(ASK_GPIO) != rest;
        if (down && !ask_down) {
            ask_at = now;
            ask_pressed();
        } else if (!down && ask_down && now - ask_at > pdMS_TO_TICKS(700) && mode == MODE_LISTENING) {
            ask_done_talking();
        }
        ask_down = down;

        /* BOOT: tap for volume, hold 1.5 s for home */
        bool vdown = gpio_get_level(VOLUME_GPIO) == 0;
        if (vdown && !vol_down) {
            vol_at = now;
            vol_held = false;
        } else if (vdown && !vol_held && now - vol_at > pdMS_TO_TICKS(1500)) {
            vol_held = true;
            ui_lock();
            go_home();
            ui_unlock();
        } else if (!vdown && vol_down && !vol_held && now - vol_at > pdMS_TO_TICKS(30)) {
            volume_step();
        }
        vol_down = vdown;

        if (mode == MODE_LECTURE && now - last_save > pdMS_TO_TICKS(30000)) {   /* survive a flat battery */
            last_save = now;
            save_pos(played_pos);
        }
    }
}

/* ------------------------------------------------------------------ audio */

static void audio_init(void)
{
    i2s_std_config_t cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {.mclk = BSP_I2S_MCLK, .bclk = BSP_I2S_SCLK, .ws = BSP_I2S_LCLK,
                     .dout = BSP_I2S_DOUT, .din = BSP_I2S_DSIN},
    };
    ESP_ERROR_CHECK(bsp_audio_init(&cfg));
    spk = bsp_audio_codec_speaker_init();
    mic = bsp_audio_codec_microphone_init();
    esp_codec_dev_sample_info_t out_fs = {.sample_rate = RATE, .channel = 1, .bits_per_sample = 16};
    esp_codec_dev_sample_info_t in_fs = {.sample_rate = RATE, .channel = 2, .bits_per_sample = 16};
    ESP_ERROR_CHECK(esp_codec_dev_open(spk, &out_fs));
    ESP_ERROR_CHECK(esp_codec_dev_open(mic, &in_fs));
    nvs_handle_t h;
    int32_t v;
    uint32_t p;
    if (nvs_open("feynman", NVS_READONLY, &h) == ESP_OK) {
        if (nvs_get_i32(h, "vol", &v) == ESP_OK && v >= 0 && v < (int32_t)(sizeof(volumes) / sizeof(volumes[0])))
            volume_idx = v;
        if (nvs_get_u32(h, "pos", &p) == ESP_OK) saved_pos = p;
        nvs_close(h);
    }
    esp_codec_dev_set_out_vol(spk, volumes[volume_idx]);
    esp_codec_dev_set_in_gain(mic, 37.5);   /* ES7210 maximum; the mics are quiet */
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    bsp_i2c_init();
    bsp_display_start();
    bsp_display_brightness_set(85);
    ui_init();
    audio_init();
    player_init();
    have_lecture = lecture_init();
    ui_lock();
    scrub_init(lv_screen_active());                 /* needs the lecture's chapters for its ticks */
    ui_unlock();
    ask_init();
    xTaskCreatePinnedToCore(button_task, "button", 4096, NULL, 5, &button_task_handle, 1);
    net_init();

    ui_lock();                                       /* start on the home screen */
    mode = MODE_IDLE;
    go_home();
    ui_unlock();
    for (;;) {                                       /* keep the home screen's Wi-Fi line current */
        vTaskDelay(pdMS_TO_TICKS(2000));
        if (mode == MODE_HOME) {
            ui_lock();
            refresh_home();
            ui_unlock();
        }
    }
}
