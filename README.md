# Feynman Tutor on a Waveshare ESP32-S3 AMOLED

A pocket physics tutor. It plays an animated lecture on *Quantum Behavior*, in the spirit of Feynman's Caltech lectures, with narration, subtitles and explainer animations. Press the side button to interrupt and ask a question out loud, and a tutor in Feynman's style answers by voice before the lecture picks up again.

It runs on its own. The lecture lives in the board's flash and plays with no network. Questions go straight from the board to [OpenRouter](https://openrouter.ai) over Wi-Fi, home or phone hotspot. There's no server or computer involved.

Hardware: [Waveshare ESP32-S3-Touch-AMOLED-2.16](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.16): ESP32-S3R8, 16 MB flash, 8 MB PSRAM, a 480×480 AMOLED touchscreen, an ES8311 speaker codec, an ES7210 dual microphone and an AXP2101 battery chip. The speaker plugs into the 2-pin header.

## Controls

| Control | Action |
|---|---|
| Side button | Press to ask a question; it stops listening when you pause. Or hold it while you talk and let go. |
| Tap the screen | Same as the side button. |
| Two swipes up | Home: pauses, and the card resumes where you were. |
| BOOT | Tap to cycle volume. Hold 1.5 s to go home. |

## How it works

```
content/quantum-behavior/lecture.json   the script: narration lines grouped into scenes
tools/beats/*.py                        one animated scene per section, choreographed to the narration lines
tools/render_lecture.py                 voice (Deepgram Aura-2 via OpenRouter) + 15 fps frames + subtitle timing
tools/pack_lecture.py                   -> lecture.fqv: MP3 audio + FQV animation frames, in one flash image
firmware/                               ESP-IDF 5.5 app: plays lecture.fqv, records questions, calls OpenRouter
```

- **FQV** (`tools/fqv.py`) is a small animation codec built for this board. Each scene gets a 256-colour palette. Each frame stores only the 16×16 tiles that changed, deflated. 53 MB of raw frames come to about 10 MB, and the board decodes them straight from flash using the inflater in the ESP32-S3's ROM.
- **Questions:** the board records with adaptive voice detection, then makes three OpenRouter calls:
  - `deepgram/nova-3` for speech-to-text.
  - `anthropic/claude-opus-5.5` as the tutor, which knows what you've heard so far and can pick a diagram to show.
  - `deepgram/aura-2` for the voice, streamed sentence by sentence with subtitles.

  Then the lecture resumes at the start of the sentence you interrupted.
- **Firmware layout:**
  - `main.c`: UI, controls, home screen.
  - `player.c`: one ordered queue for audio, subtitles and frames.
  - `lecture.c`: reads the flash image.
  - `ask.c`: questions.
  - `net.c`: joins the strongest known Wi-Fi.

## Build it

Requirements: Python 3, ffmpeg, librsvg (`brew install ffmpeg librsvg`) and [ESP-IDF 5.5](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/get-started/).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "OPENROUTER_API_KEY=sk-or-..." > .env

# 1. render and pack the lecture (voice clips are cached in cache/tts/)
.venv/bin/python tools/render_lecture.py quantum-behavior
.venv/bin/python tools/pack_lecture.py quantum-behavior

# 2. Wi-Fi networks + OpenRouter key -> firmware/main/secrets.h (gitignored)
tools/set_wifi.sh

# 3. build and flash the app, then the lecture image into its partition
source ~/esp/esp-idf/export.sh
cd firmware && idf.py build
../.venv/bin/esptool --port /dev/cu.usbmodem101 -b 921600 write-flash @build/flash_args \
    0x290000 ../build/lectures/quantum-behavior/lecture.fqv
```

`tools/render_lecture.py` also writes `build/preview/quantum-behavior.mp4`, the whole lecture as a video, for checking animation changes without flashing. To preview a single scene, `.venv/bin/python tools/animate.py 02-waves` renders one frame per narration line.

## Board notes

- `firmware/components/esp32_s3_touch_amoled_2_16` is Waveshare's BSP with one change: the display draw buffers are in internal DMA RAM. The stock PSRAM buffers make every flush bounce through a 48 KB internal block, which Wi-Fi starves.
- The microphones are quiet, so the gain is set to the maximum (37.5 dB), the two mics are summed, and each question is normalized before speech-to-text.
- The flash partitions are a 2.5 MB app and a 13.4 MB `lecture` data partition at `0x290000`.

## Dev tools

`server/` + `sim/` hold the earlier Mac-hosted version: a WebSocket server and a browser simulator of the device, at `http://localhost:8780`. They're handy for iterating on content: `.venv/bin/python -m server.app`.

## Content note

The lecture is an original script written in the style of Feynman's 1961–64 Caltech lectures. It isn't a transcript. The original recordings are © Caltech and published for streaming at [feynmanlectures.caltech.edu](https://www.feynmanlectures.caltech.edu/flptapes.html). To use a recording you own, transcribe it with timestamps into the same `lecture.json` / timeline format.
