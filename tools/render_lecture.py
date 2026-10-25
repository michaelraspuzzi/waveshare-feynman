"""Render a lecture script into streamable assets.

  content/<id>/lecture.json + tools/scenes.py (animated diagrams)
    -> build/lectures/<id>/audio.pcm      16 kHz mono s16le (what the device plays)
       build/lectures/<id>/audio.wav      same audio, for the browser simulator
       build/lectures/<id>/timeline.json  sample-accurate subtitle + visual cues, animation index
       build/lectures/<id>/anim/<v>.bin   zlib RGB565 frames at 15 fps, one segment each
       build/lectures/<id>/visuals/<v>.png / .rgb565  last frame of each scene (shown during answers)
       build/preview/<id>.mp4             the whole lecture as a video, for checking

Run: python tools/render_lecture.py quantum-behavior
"""
import json
import subprocess
import sys
import wave
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.tts import synth  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animate  # noqa: E402
import scenes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000
LINE_GAP_S = 0.15
SEGMENT_GAP_S = 0.50
PACE = 1.08         # narration sped up 8% (pitch kept) so the lecture fits the board's flash
SUB_MAX_CHARS = 64  # ~2 lines of subtitle on a 480px screen


def chunk_subtitle(line, max_chars=SUB_MAX_CHARS):
    """Split a line into roughly balanced pieces of <= max_chars, on word boundaries."""
    words = line.split()
    n = max(1, -(-len(line) // max_chars))
    target = len(line) / n
    chunks, cur = [], ""
    for w in words:
        nxt = f"{cur} {w}".strip()
        if cur and (len(nxt) > max_chars or (len(cur) >= target and len(chunks) < n - 1)):
            chunks.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        chunks.append(cur)
    return chunks


def pace(audio, tempo=PACE):
    if tempo == 1.0:
        return audio
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-",
                          "-filter:a", f"atempo={tempo}", "-f", "s16le", "-"],
                         input=audio.astype("<i2").tobytes(), check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<i2").copy()


def render_animations(out, events, total, lines):
    """Render each segment's scene over exactly the time it is on screen."""
    shows = [e for e in sorted(events, key=lambda e: e["at"]) if e["t"] == "show"]
    (out / "anim").mkdir(exist_ok=True)
    anim = {}
    with Pool() as pool:
        for i, ev in enumerate(shows):
            start = ev["at"]
            end = shows[i + 1]["at"] if i + 1 < len(shows) else total
            T = (end - start) / RATE
            ls = [ln for ln in lines if ln["visual"] == ev["id"]]
            beats = (tuple((ln["start"] - start) / RATE for ln in ls), tuple((ln["end"] - start) / RATE for ln in ls))
            frames = animate.render_scene(ev["id"], T, beats, pool)
            offsets, blob = [0], bytearray()
            for f in frames:
                blob += f
                offsets.append(len(blob))
            (out / "anim" / f"{ev['id']}.bin").write_bytes(bytes(blob))
            last = animate.frame_to_rgb(frames[-1])
            Image.fromarray(last).save(out / "visuals" / f"{ev['id']}.png")
            (out / "visuals" / f"{ev['id']}.rgb565").write_bytes(animate.to_rgb565(last).tobytes())
            anim[ev["id"]] = {"start": start, "end": end, "frames": len(frames), "offsets": offsets}
            print(f"  animated {ev['id']}: {T:.1f}s, {len(frames)} frames, {len(blob) / 1e6:.1f} MB")
    return anim


def preview_video(out, lecture_id, anim):
    """Stitch every segment's frames + the audio into an mp4 for review."""
    path = ROOT / "build" / "preview" / f"{lecture_id}.mp4"
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", "480x480", "-r", str(scenes.FPS), "-i", "-", "-i", str(out / "audio.wav"),
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-shortest",
                           str(path)], stdin=subprocess.PIPE)
    for vid, a in sorted(anim.items(), key=lambda kv: kv[1]["start"]):
        blob = (out / "anim" / f"{vid}.bin").read_bytes()
        n = round((a["end"] - a["start"]) / RATE * scenes.FPS)
        for k in range(n):
            j = min(k, a["frames"] - 1)
            ff.stdin.write(animate.frame_to_rgb(blob[a["offsets"][j]:a["offsets"][j + 1]]).tobytes())
    ff.stdin.close()
    ff.wait()
    print("preview video:", path)


def render(lecture_id):
    src = ROOT / "content" / lecture_id
    out = ROOT / "build" / "lectures" / lecture_id
    (out / "visuals").mkdir(parents=True, exist_ok=True)
    lecture = json.loads((src / "lecture.json").read_text())

    pcm, lines, events = [], [], []
    pos = 0

    def silence(seconds):
        nonlocal pos
        n = int(seconds * RATE)
        pcm.append(np.zeros(n, dtype=np.int16))
        pos += n

    for si, seg in enumerate(lecture["segments"]):
        events.append({"at": pos, "t": "show", "id": seg["visual"]})
        for text in seg["lines"]:
            audio = pace(synth(text))
            start, end = pos, pos + len(audio)
            pcm.append(audio)
            pos = end
            # subtitle pieces share the line's duration in proportion to their length
            pieces = chunk_subtitle(text)
            total = sum(len(p) for p in pieces)
            at = start
            for p in pieces:
                events.append({"at": at, "t": "sub", "text": p})
                at += int((end - start) * len(p) / total)
            lines.append({"i": len(lines), "segment": si, "visual": seg["visual"],
                          "text": text, "start": start, "end": end})
            silence(LINE_GAP_S)
            events.append({"at": pos, "t": "sub", "text": ""})
            print(f"  [{start / RATE:6.1f}s] {text[:70]}")
        silence(SEGMENT_GAP_S - LINE_GAP_S)

    audio = np.concatenate(pcm)
    (out / "audio.pcm").write_bytes(audio.astype("<i2").tobytes())
    with wave.open(str(out / "audio.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.astype("<i2").tobytes())

    anim = render_animations(out, events, len(audio), lines)
    timeline = {"id": lecture["id"], "title": lecture["title"], "rate": RATE,
                "total": int(len(audio)), "lines": lines, "fps": scenes.FPS, "anim": anim,
                "events": sorted(events, key=lambda e: e["at"])}
    (out / "timeline.json").write_text(json.dumps(timeline, indent=1))
    print(f"rendered {lecture_id}: {len(audio) / RATE / 60:.1f} min, {len(lines)} lines -> {out}")
    preview_video(out, lecture_id, anim)


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else "quantum-behavior")
