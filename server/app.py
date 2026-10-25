"""Feynman tutor server.

One WebSocket per device (or browser simulator). The server streams the lecture as paced audio
with in-band subtitle/visual cues; the device presses its button to interrupt, streams mic audio
back, and gets a spoken answer before the lecture resumes at the start of the interrupted line.

Wire protocol (all integers little-endian):
  server -> device
    binary 0x01 | u32 pos | pcm16 mono 16 kHz     audio; pos = lecture sample (0xFFFFFFFF = answer)
    binary 0x02 | u8 n | id[n] | rgb565 480x480    image; device caches it by id
    binary 0x03 | dirty rects (see server/frames.py) in-band: patches the image on screen (animation)
    text {"t":"show","id"} {"t":"sub","text"} {"t":"mode","mode"}   in-band: fire when playback reaches them
    text {"t":"flush"}                              out-of-band: drop everything queued
  device -> server
    text {"t":"hello","device"} {"t":"start"} {"t":"interrupt","pos"} {"t":"ask_done"}
         {"t":"home","pos"} (pause, device shows its home screen) {"t":"resume"} (continue where it paused)
    binary 0x10 | pcm16 mono 16 kHz                 mic audio while listening

Run: .venv/bin/python -m server.app   (then open http://localhost:8780 for the simulator)
"""
import asyncio
import math
import zlib
import json
import logging
import os
import re
import struct
import time
from pathlib import Path

import numpy as np
from aiohttp import WSMsgType, web

from server import brain, stt, tts
from server.frames import encode_delta

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000
CHUNK = 1600            # 100 ms of audio per frame
LEAD_S = 1.0            # how far ahead of real time we keep the device's buffer
ANSWER_POS = 0xFFFFFFFF
log = logging.getLogger("feynman")

# The device's LVGL fonts are ASCII-only, so subtitles are folded to ASCII before sending.
_ASCII = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": " - ", "–": "-", "…": "...",
                        "φ": "phi", "ħ": "h-bar", "≠": "!=", "≥": ">=", "≤": "<=", "→": "->",
                        "²": "^2", "₁": "1", "₂": "2", "·": "*", "Δ": "delta "})


def ascii_text(s):
    return s.translate(_ASCII).encode("ascii", "ignore").decode()


class Lecture:
    def __init__(self, lecture_id):
        d = ROOT / "build" / "lectures" / lecture_id
        self.timeline = json.loads((d / "timeline.json").read_text())
        self.pcm = (d / "audio.pcm").read_bytes()
        self.visual_dir = d / "visuals"
        self.title = self.timeline["title"]
        self.lines = self.timeline["lines"]
        self.events = self.timeline["events"]
        self.total = self.timeline["total"]
        self.visuals = sorted(p.stem for p in self.visual_dir.glob("*.rgb565"))
        self.fps = self.timeline.get("fps", 15)
        self.anim = self.timeline.get("anim", {})
        self.anim_blobs = {v: (d / "anim" / f"{v}.bin").read_bytes() for v in self.anim}

    def frame(self, vid, k):
        a = self.anim[vid]
        k = max(0, min(k, a["frames"] - 1))
        raw = zlib.decompress(self.anim_blobs[vid][a["offsets"][k]:a["offsets"][k + 1]])
        return np.frombuffer(raw, dtype="<u2").reshape(480, 480)

    def anim_events(self, start):
        """Keyframe at the start of each scene (or at the resume point), then one delta per frame."""
        step = RATE / self.fps
        out = []
        for vid, a in self.anim.items():
            if a["end"] <= start:
                continue
            k0 = math.ceil((start - a["start"]) / step) if start > a["start"] else 0
            out.append({"at": max(a["start"], start), "t": "key", "id": vid, "k": k0})
            for k in range(k0 + 1, a["frames"]):
                at = int(a["start"] + k * step)
                if at >= a["end"]:
                    break
                out.append({"at": at, "t": "frame", "id": vid, "k": k})
        return out

    def image(self, vid):
        return (self.visual_dir / f"{vid}.rgb565").read_bytes()

    def line_start(self, pos):
        """Start of the line being spoken at pos (so a resume never begins mid-sentence)."""
        for ln in self.lines:
            if ln["end"] + int(0.3 * RATE) > pos:
                return ln["start"]
        return self.total

    def visual_at(self, pos):
        vid = None
        for e in self.events:
            if e["at"] > pos:
                break
            if e["t"] == "show":
                vid = e["id"]
        return vid

    def heard(self, pos):
        return [ln["text"] for ln in self.lines if ln["start"] <= pos]


class Session:
    def __init__(self, ws, lecture):
        self.ws, self.lec = ws, lecture
        self.pos = 0
        self.mode = "idle"
        self.task = None
        self.mic = bytearray()
        self.listen_started = 0.0
        self.speech_started = False
        self.last_voice = 0.0
        self.noise = []
        self.history = []
        self.device = "?"

    # ------------------------------------------------------------------ sending
    async def send(self, **msg):
        await self.ws.send_str(json.dumps(msg))

    async def send_image(self, vid):
        idb = vid.encode()
        await self.ws.send_bytes(bytes([0x02, len(idb)]) + idb + self.lec.image(vid))

    async def emit(self, ev):
        if ev["t"] == "key":                        # full frame, then deltas against it
            self.prev = self.lec.frame(ev["id"], ev["k"])
            idb = ev["id"].encode()
            await self.ws.send_bytes(bytes([0x02, len(idb)]) + idb + self.prev.tobytes())
            await self.send(t="show", id=ev["id"])
            return
        if ev["t"] == "frame":
            cur = self.lec.frame(ev["id"], ev["k"])
            msg = encode_delta(self.prev, cur)
            self.prev = cur
            if msg:
                await self.ws.send_bytes(msg)
            return
        if ev["t"] == "show":
            await self.send_image(ev["id"])
        msg = {k: v for k, v in ev.items() if k != "at"}
        if msg["t"] == "sub":
            msg["text"] = ascii_text(msg["text"])
        await self.send(**msg)

    async def play(self, pcm, events, base_pos):
        """Stream pcm (bytes) paced to real time + LEAD_S, firing events at their sample offsets."""
        total = len(pcm) // 2
        events = sorted(events, key=lambda e: e["at"])
        t0, sent, ei = time.monotonic(), 0, 0
        while sent < total:
            while ei < len(events) and events[ei]["at"] <= sent:
                await self.emit(events[ei])
                ei += 1
            nxt = min(sent + CHUNK, total)
            if ei < len(events):
                nxt = min(nxt, max(events[ei]["at"], sent + 1))
            pos = ANSWER_POS if base_pos == ANSWER_POS else base_pos + sent
            await self.ws.send_bytes(b"\x01" + struct.pack("<I", pos) + pcm[sent * 2:nxt * 2])
            sent = nxt
            ahead = sent / RATE - (time.monotonic() - t0)
            if ahead > LEAD_S:
                await asyncio.sleep(ahead - LEAD_S)
        for ev in events[ei:]:
            await self.emit(ev)
        await asyncio.sleep(max(0.0, sent / RATE - (time.monotonic() - t0)))

    # ------------------------------------------------------------------ lecture
    def start_task(self, coro):
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = asyncio.create_task(coro)

    async def run_lecture(self, from_pos):
        start = self.lec.line_start(from_pos)
        self.mode = "lecture"
        if start >= self.lec.total:
            self.mode = "done"
            await self.send(t="mode", mode="done")
            return
        pre = [{"at": 0, "t": "mode", "mode": "lecture"}]
        if self.lec.anim:
            cues = [e for e in self.lec.events if e["at"] >= start and e["t"] != "show"]
            cues += self.lec.anim_events(start)
        else:
            vid = self.lec.visual_at(start)
            if vid:
                pre.append({"at": 0, "t": "show", "id": vid})
            cues = [e for e in self.lec.events
                    if e["at"] >= start and not (e["at"] == start and e["t"] == "show")]
        events = pre + [dict(e, at=e["at"] - start) for e in cues]
        log.info("lecture from %.1fs", start / RATE)
        await self.play(self.lec.pcm[start * 2:], events, start)
        self.pos = self.lec.total
        self.mode = "done"
        await self.send(t="mode", mode="done")

    # ------------------------------------------------------------------ questions
    async def interrupt(self, pos):
        if self.mode == "lecture" and isinstance(pos, int) and 0 <= pos < ANSWER_POS:
            self.pos = pos
        if self.task and not self.task.done():
            self.task.cancel()
        self.mode = "listening"
        self.mic.clear()
        self.noise = []
        self.max_rms = 0.0
        self.speech_started = False
        self.listen_started = self.last_voice = time.monotonic()
        await self.send(t="flush")
        await self.send(t="mode", mode="listening")
        await self.send(t="sub", text="")
        self.task = asyncio.create_task(self.watch_listening())
        log.info("interrupt at %.1fs", self.pos / RATE)

    def on_mic(self, pcm):
        if self.mode != "listening":
            return
        self.mic.extend(pcm)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        if not len(samples) or time.monotonic() - self.listen_started < 0.25:
            return                         # skip the speaker's tail right after the button press
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self.max_rms = max(self.max_rms, rms)
        self.noise.append(rms)
        if len(self.noise) < 5:
            return
        # Adaptive: the quiet 20% of what we've heard is the room (and mic hiss); speech stands well above it
        floor = float(np.percentile(self.noise, 20))
        if rms > max(1.8 * floor, floor + 80.0):
            self.speech_started = True
            self.last_voice = time.monotonic()

    async def watch_listening(self):
        while self.mode == "listening":
            await asyncio.sleep(0.1)
            now = time.monotonic()
            if ((self.speech_started and now - self.last_voice > 1.5)
                    or now - self.listen_started > 20
                    or (not self.speech_started and now - self.listen_started > 8)):
                await self.finish_question()
                return

    async def finish_question(self):
        if self.mode != "listening":
            return
        self.mode = "thinking"
        await self.send(t="mode", mode="thinking")
        audio = bytes(self.mic)
        save_debug_wav(audio, self.device)
        floor = float(np.percentile(self.noise, 20)) if self.noise else 0.0
        log.info("mic: %.1fs received, peak rms %.0f, floor %.0f, speech=%s", len(audio) / 2 / RATE,
                 self.max_rms, floor, self.speech_started)
        # Even if the detector never fired, anything clearly above the floor goes to Whisper
        worth_it = self.speech_started or self.max_rms > 1.5 * floor + 40
        question = await asyncio.to_thread(stt.transcribe, normalize(audio)) if worth_it else ""
        if question.strip().strip(".!").lower() in WHISPER_SILENCE:
            question = ""
        log.info("heard: %r", question)
        if not question or not re.search(r"[a-zA-Z]", question):
            await self.send(t="sub", text="(didn't catch that)")
            await asyncio.sleep(1.0)
            self.start_task(self.run_lecture(self.pos))
            return
        await self.send(t="sub", text=ascii_text(f"\"{question}\""))
        self.start_task(self.answer_and_resume(question))

    async def answer_and_resume(self, question):
        t0 = time.monotonic()
        answer, vid = await asyncio.to_thread(
            brain.answer, self.lec.title, self.lec.heard(self.pos), self.lec.visuals, self.history, question)
        log.info("answer (%.1fs, visual=%s): %s", time.monotonic() - t0, vid, answer)
        self.history.append((question, answer))
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer) if s.strip()]
        clips = await asyncio.gather(*(asyncio.to_thread(tts.synth, s) for s in sentences))
        gap = np.zeros(int(0.25 * RATE), dtype=np.int16)
        pcm, events, at = [], [{"at": 0, "t": "mode", "mode": "answering"}], 0
        if vid:
            events.append({"at": 0, "t": "show", "id": vid})
        for s, clip in zip(sentences, clips):
            events.append({"at": at, "t": "sub", "text": s})
            pcm += [clip, gap]
            at += len(clip) + len(gap)
        events.append({"at": at, "t": "sub", "text": ""})
        pcm.append(np.zeros(int(0.6 * RATE), dtype=np.int16))
        self.mode = "answering"
        await self.play(np.concatenate(pcm).astype("<i2").tobytes(), events, ANSWER_POS)
        await self.run_lecture(self.pos)

    # ------------------------------------------------------------------ dispatch
    async def on_text(self, msg):
        t = msg.get("t")
        if t == "start":
            self.pos = 0
            self.history.clear()
            await self.send(t="flush")
            self.start_task(self.run_lecture(0))
        elif t == "interrupt":
            if self.mode == "listening":       # second press = done asking
                await self.finish_question()
            elif self.mode in ("lecture", "answering", "done"):
                await self.interrupt(msg.get("pos"))
        elif t == "ask_done":
            await self.finish_question()
        elif t == "home":
            pos = msg.get("pos")
            if self.mode == "lecture" and isinstance(pos, int) and 0 <= pos < ANSWER_POS:
                self.pos = pos
            if self.task and not self.task.done():
                self.task.cancel()
            self.mode = "home"
            await self.send(t="flush")
            log.info("home (paused at %.1fs)", self.pos / RATE)
        elif t == "resume":
            log.info("resume from %.1fs", self.pos / RATE)
            await self.send(t="flush")
            self.start_task(self.run_lecture(self.pos))
        elif t == "hello":
            self.device = msg.get("device", "?")
            log.info("hello from %s", self.device)
            await self.send(t="hello", lecture=self.lec.timeline["id"], title=self.lec.title, rate=RATE,
                            total=self.lec.total)


async def ws_handler(request):
    ws = web.WebSocketResponse(max_msg_size=4 * 1024 * 1024, heartbeat=10)
    await ws.prepare(request)
    session = Session(ws, request.app["lecture"])
    request.app["sessions"].add(session)
    log.info("client connected from %s", request.remote)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await session.on_text(json.loads(msg.data))
            elif msg.type == WSMsgType.BINARY and msg.data[:1] == b"\x10":
                session.on_mic(msg.data[1:])
    finally:
        request.app["sessions"].discard(session)
        if session.task:
            session.task.cancel()
        log.info("client disconnected")
    return ws


# What Whisper tends to "hear" in silence or hiss
WHISPER_SILENCE = {"", "you", "thank you", "thanks for watching", "bye", "okay"}


def normalize(pcm):
    """Scale quiet mic audio up to a healthy level before Whisper (peak at ~-3 dBFS, max 30x)."""
    a = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    a -= a.mean()
    peak = float(np.abs(a).max()) if len(a) else 0.0
    if peak < 1:
        return pcm
    gain = min(30.0, 23000.0 / peak)
    return np.clip(a * gain, -32768, 32767).astype("<i2").tobytes()


def save_debug_wav(pcm, device):
    """Keep every question's raw mic audio in build/debug/ for diagnosing the device mics."""
    import wave
    d = ROOT / "build" / "debug"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"question-{device}-{time.strftime('%H%M%S')}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    log.info("saved %s", path.name)


async def debug_interrupt(request):
    """POST /debug/interrupt: put every connected device into listening mode, as if its button was pressed."""
    hit = [s for s in request.app["sessions"] if s.device != "sim"]
    for s in hit:
        await s.interrupt(None)
    return web.json_response({"interrupted": [s.device for s in hit]})


async def index(request):
    return web.FileResponse(ROOT / "sim" / "index.html")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = web.Application()
    app["lecture"] = Lecture(os.environ.get("FEYNMAN_LECTURE", "quantum-behavior"))
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/debug/interrupt", debug_interrupt)
    app["sessions"] = set()
    log.info("brain backend: %s (%s)", brain.backend(), brain.MODEL)
    log.info("warming up whisper (%s)...", stt.MODEL)
    stt.warm_up()
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8780)), print=None)


if __name__ == "__main__":
    main()
