# Feynman Tutor on Waveshare ESP32-S3-Touch-AMOLED-2.16

The device streams a Feynman lecture with subtitles and explainer visuals. Press a button to interrupt and ask a question by voice, and the tutor answers.

## Hardware (read from the board on 2026-10-24)

- **Port:** `/dev/cu.usbmodem101` (native USB-Serial/JTAG, VID 0x303A / PID 0x1001)
- **Chip:** ESP32-S3 (QFN56) rev v0.2, dual-core 240 MHz, Wi-Fi + BLE 5
- **Memory:** 8 MB embedded PSRAM, 16 MB quad flash
- **MAC:** 90:70:69:fe:6d:04
- **Factory firmware backup:** `backup/factory-firmware-16MB.bin`
  - Restore it with: `.venv/bin/esptool --port /dev/cu.usbmodem101 write-flash 0 backup/factory-firmware-16MB.bin`

Docs: https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.16

### Pin map for this project

| Function | Part | Pins |
|---|---|---|
| Display 480×480 AMOLED | CO5300, QSPI | SIO0-3 = 4,5,6,7 · CLK 38 · CS 12 · RST 39 |
| Touch | CST9220 | I2C · INT 11 · RST 40 |
| Shared I2C | touch, AXP2101, QMI8658, PCF85063, ES8311, ES7210 | SCL 14 · SDA 15 |
| Speaker DAC | ES8311 | MCLK 42 · BCLK 9 · LRCK 45 · DOUT 8 · PA enable 46 |
| Mic array (2 mics, AEC) | ES7210 | MCLK 42 · BCLK 9 · LRCK 45 · DIN 10 |
| User button (interrupt) | Key3 | GPIO18 (active low) |
| BOOT / PWR | Key2 / Key1 | GPIO0 / PMIC |
| SD card (SPI) | — | MOSI 1 · SCK 2 · MISO 3 · CS 41 |
| PMIC / battery | AXP2101 | I2C |

## Proposed architecture

The ESP32-S3 can't run speech recognition or an LLM, so it acts as a thin client. A server does the rest.

```
 ┌──────── device (ESP32-S3) ────────┐        ┌──────────── server (laptop / cloud) ────────────┐
 │ LVGL UI: visual + subtitle strip  │◀─WS────│ lecture timeline: audio chunks, subtitle cues,  │
 │ I2S out → ES8311 → speaker        │        │ visual cues (SVG → 480×480 PNG/RGB565)           │
 │ GPIO18 / touch → "interrupt"      │──WS───▶│ pause lecture, receive mic audio                 │
 │ I2S in ← ES7210 mics (16 kHz)     │──WS───▶│ STT → Claude (Feynman tutor persona) → TTS       │
 └───────────────────────────────────┘        │ answer audio + subtitles + optional diagram      │
                                              │ → resume the lecture where it stopped            │
                                              └──────────────────────────────────────────────────┘
```

- **Visuals:** SVGs are authored here and rasterized on the server or at build time to 480×480 images. The device only shows bitmaps; rendering SVG on the chip is possible (LVGL 9 + ThorVG) but slow and memory-hungry.
- **Subtitles:** timed cues (WebVTT-style) pushed with the audio and drawn as an LVGL label at the bottom of the round-corner square screen.
- **Firmware:** ESP-IDF 5.x + LVGL 9 + `esp_codec_dev` for audio, built from Waveshare's demos for the display and codec bring-up.

## Lecture content: findings (2026-10-24)

- **Real recordings exist:** Caltech publishes all 122 original 1961–64 lecture tapes at https://www.feynmanlectures.caltech.edu/flptapes.html, along with each lecture's book chapter.
- **They're streaming-only:** the audio is © Caltech and served from a `/protectedaudio/` path behind Cloudflare bot protection. We won't scrape or download it.
- **Legitimate copies:** Basic Books released the tapes as audio CD sets (Hachette lists them, e.g. ISBN 9780738209289). Audio you own can be used on this personal device. We'd transcribe it locally with Whisper to get timed subtitles. Don't redistribute it.
- **Fallback:** Claude writes an original lecture in Feynman's teaching style, voiced with a stock TTS voice. It doesn't clone his voice or reproduce the book text.
- **Candidate first lecture:** #37 *Quantum behavior* (4/3/62), the double-slit experiment (FLP Vol. III ch. 1). It's iconic and suits diagrams.

## How to run it

```
content/quantum-behavior/   lecture.json (script, split into subtitle lines) + visuals/*.svg
tools/make_visuals.py       generates the SVG diagrams
tools/render_lecture.py     script -> audio.pcm + timeline.json + 480x480 RGB565 images (build/lectures/)
server/                     aiohttp WebSocket server: paced streaming, interrupt, Whisper -> Claude -> TTS
sim/index.html              browser simulator of the device (same protocol), served at http://localhost:8780
firmware/                   ESP-IDF 5.5 app for the board (Waveshare BSP + LVGL 9 + esp_websocket_client)
```

1. Render the lecture after editing the script or diagrams:
   ```
   .venv/bin/python tools/make_visuals.py && .venv/bin/python tools/render_lecture.py quantum-behavior
   ```
2. Start the server: `.venv/bin/python -m server.app`. Then open http://localhost:8780, click Start, and press space to interrupt.
3. Run the headless end-to-end test (interrupt, spoken question, answer, resume): `.venv/bin/python tools/test_client.py "your question"`.
4. Firmware: put your Wi-Fi details in `firmware/main/secrets.h`, then:
   ```
   source ~/esp/esp-idf/export.sh && cd firmware && idf.py -p /dev/cu.usbmodem101 flash monitor
   ```

### Services and settings

- **Voice:** Deepgram Aura-2 `aura-2-draco-en` (British male) via OpenRouter. It uses `OPENROUTER_API_KEY` in `.env`, copied from jev-test. Set `FEYNMAN_VOICE` to try another Aura-2 voice. Clips are cached in `cache/tts/`. Without a key it falls back to macOS `say`.
- **Speech-to-text:** Whisper small.en running locally via mlx-whisper.
- **Answers:** Claude (`claude-opus-5-5`) through the Anthropic API if `ANTHROPIC_API_KEY` is set. Otherwise it uses the local `claude -p` CLI (`FEYNMAN_CLI_MODEL`, default sonnet).
- **Swapping in the real recording later:** produce the same `audio.pcm` + `timeline.json` from the real audio. Whisper with word timestamps gives the subtitle cues; visual cues are added by hand. The server and firmware don't change.
