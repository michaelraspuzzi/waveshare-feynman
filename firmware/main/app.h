/*
 * Feynman tutor, standalone: the lecture plays from a flash partition (lecture.fqv), and questions go
 * straight from the board to OpenRouter (speech-to-text, Claude, voice) over whichever Wi-Fi is around.
 *
 *   main.c     UI, buttons, swipes, home screen
 *   player.c   the one ordered play queue: audio, subtitles, mode changes, animation frames
 *   lecture.c  reads lecture.fqv: MP3 audio + FQV animation frames, feeds the play queue
 *   ask.c      record a question, transcribe, ask Claude, speak the answer
 *   net.c      Wi-Fi: home + hotspot, whichever is in range
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "lvgl.h"
#include "esp_codec_dev.h"

#define RATE       16000
#define IMG_W      480
#define ANSWER_POS 0xFFFFFFFFu

typedef enum { MODE_IDLE, MODE_LECTURE, MODE_LISTENING, MODE_THINKING, MODE_ANSWERING, MODE_DONE, MODE_HOME } app_mode_t;
extern volatile app_mode_t mode;
extern esp_codec_dev_handle_t spk, mic;

/* ---- player.c: everything that should happen in step with the audio goes through here */
void player_init(void);
void play_audio(uint32_t pos, const int16_t *pcm, size_t samples);   /* pos = lecture sample, or ANSWER_POS */
void play_sub(const char *text);
void play_mode(app_mode_t m);
void play_frame(int scene, int frame);      /* apply one animation delta */
void play_key(int scene, int frame);        /* jump the animation to an exact frame (scene start, resume) */
void play_final(int scene);                 /* a scene's last frame, used as the picture for an answer */
void play_flush(void);
extern volatile uint32_t played_pos;        /* last lecture sample actually played */
extern volatile int32_t queued_samples;     /* audio waiting in the queue, for pacing */

/* ---- main.c: UI helpers (call ui_lock around anything that touches LVGL from outside its task) */
void ui_lock(void);
void ui_unlock(void);
void ui_set_sub(const char *text);          /* lock held */
void ui_set_mode(app_mode_t m);             /* lock held */
void ui_note(const char *text);             /* small transient status line; takes the lock */
uint16_t *ui_framebuffer(void);
lv_obj_t *ui_image(void);
void app_lecture_done(void);

/* ---- lecture.c */
bool lecture_init(void);
void lecture_play(uint32_t from_pos);       /* resumes at the start of the line containing from_pos */
void lecture_stop(void);
uint32_t lecture_total(void);
const char *lecture_title(void);
int lecture_heard(uint32_t pos, char *out, size_t cap);
int lecture_scene_count(void);
const char *lecture_scene_id(int i);
const char *lecture_scene_desc(int i);
int lecture_scene_find(const char *id);
void video_apply(int scene, int frame);     /* lock taken inside */
void video_seek(int scene, int frame);
void video_final(int scene);

/* ---- ask.c */
void ask_init(void);
void ask_begin(uint32_t lecture_pos);       /* button pressed during lecture/answer */
void ask_done_talking(void);                /* pressed again while listening */
void ask_cancel(void);

/* ---- net.c */
void net_init(void);
bool net_online(void);
const char *net_name(void);                 /* SSID in use, or "" */
