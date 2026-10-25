"""Pack a rendered lecture into one flash image the board plays with no network.

  build/lectures/<id>/{audio.pcm, timeline.json, anim/*.bin}  ->  build/lectures/<id>/lecture.fqv

Layout (all integers little-endian, offsets absolute from the start of the image):

  header (64 B)
    0  "FQV1"            4  u32 image size      8  u32 sample rate
    12 u16 fps           14 u16 scenes          16 u16 lines        18 u16 subtitles
    20 u32 total samples 24 u32 audio offset    28 u32 audio bytes
    32 u16 mp3 frame bytes                      34 u16 samples per mp3 frame
    36 u32 scene table   40 u32 line table      44 u32 subtitle table   48 u32 strings   52 u32 title string
  scene record (64 B): char id[24] | u32 start | u32 end | u32 frames | u32 palette (256 x u16 RGB565)
                       | u32 frame index ((frames+1) x u32 offsets) | u32 final keyframe | u32 its length | u32 description
  line record (16 B):  u32 start | u32 end | u16 scene | u16 0 | u32 text
  subtitle (8 B):      u32 at | u32 text ("" clears)
  audio: constant-bitrate MP3 (MPEG-2 layer III, 16 kHz mono, 32 kbps, no bit reservoir) so any frame is seekable
  frames: FQV blobs (see tools/fqv.py)
"""
import json
import struct
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import animate  # noqa: E402
import fqv  # noqa: E402
import scenes  # noqa: E402
from server.app import ascii_text  # noqa: E402

MP3_KBPS = 32


def encode_scene(args):
    lecture_dir, vid, a = args
    blob = (lecture_dir / "anim" / f"{vid}.bin").read_bytes()
    frames = [animate.frame_to_rgb(blob[a["offsets"][k]:a["offsets"][k + 1]]) for k in range(a["frames"])]
    pal, out = fqv.encode_scene(frames)
    # the last frame as a standalone keyframe (shown during answers)
    prev = None
    for b in out:
        prev = fqv.decode_frame(b, prev)
    final = fqv.encode_frame(None, prev)
    return vid, pal.tobytes(), out, final


def mp3(pcm_path, rate):
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", str(pcm_path),
         "-c:a", "libmp3lame", "-b:a", f"{MP3_KBPS}k", "-reservoir", "0", "-write_xing", "0",
         "-id3v2_version", "0", "-f", "mp3", "-"], check=True, capture_output=True).stdout


def pack(lecture_id):
    d = ROOT / "build" / "lectures" / lecture_id
    tl = json.loads((d / "timeline.json").read_text())
    rate, fps = tl["rate"], tl["fps"]
    order = sorted(tl["anim"], key=lambda v: tl["anim"][v]["start"])
    with Pool() as pool:
        enc = {r[0]: r[1:] for r in pool.map(encode_scene, [(d, v, tl["anim"][v]) for v in order])}
    audio = mp3(d / "audio.pcm", rate)
    frame_bytes = 72 * MP3_KBPS * 1000 // rate                     # MPEG-2 layer III, no padding at 16 kHz

    strings = bytearray()

    def s(text):
        off = len(strings)
        strings.extend(text.encode("utf-8") + b"\0")
        return off

    subs = [e for e in tl["events"] if e["t"] == "sub"]
    n_scenes, n_lines = len(order), len(tl["lines"])
    hdr_size, scene_size = 64, 64
    scenes_off = hdr_size
    lines_off = scenes_off + scene_size * n_scenes
    subs_off = lines_off + 16 * n_lines
    strings_off = subs_off + 8 * len(subs)

    # strings first (so records can reference them), then binary payloads after the string table
    title = s(tl["title"])
    scene_desc = {v: s(scenes.DESCRIPTIONS.get(v, v)) for v in order}
    line_txt = [s(ln["text"]) for ln in tl["lines"]]
    sub_txt = [s(ascii_text(e["text"])) for e in subs]
    payload_off = strings_off + len(strings)
    payload_off += (-payload_off) % 4

    payload = bytearray()

    def put(b):
        off = payload_off + len(payload)
        payload.extend(b)
        payload.extend(b"\0" * ((-len(payload)) % 4))
        return off

    audio_off = put(audio)
    scene_recs = []
    for v in order:
        pal, frames, final = enc[v]
        pal_off = put(pal)
        offs = []
        for f in frames:
            offs.append(put(f))
        offs.append(payload_off + len(payload))
        idx_off = put(struct.pack(f"<{len(offs)}I", *offs))
        final_off = put(final)
        a = tl["anim"][v]
        scene_recs.append(struct.pack("<24sIIIIIIII8x", v.encode(), a["start"], a["end"], len(frames), pal_off,
                                      idx_off, final_off, len(final), scene_desc[v]))
    total = payload_off + len(payload)
    header = struct.pack("<4sII HHHH III HH IIIII 8x", b"FQV1", total, rate, fps, n_scenes, n_lines, len(subs),
                         tl["total"], audio_off, len(audio), frame_bytes, 576,
                         scenes_off, lines_off, subs_off, strings_off, title)
    assert len(header) == 64, len(header)
    scene_of = {v: i for i, v in enumerate(order)}
    lines = b"".join(struct.pack("<IIHHI", ln["start"], ln["end"], scene_of[ln["visual"]], 0, line_txt[i])
                     for i, ln in enumerate(tl["lines"]))
    sub_recs = b"".join(struct.pack("<II", e["at"], sub_txt[i]) for i, e in enumerate(subs))
    image = bytearray(header + b"".join(scene_recs) + lines + sub_recs + strings)
    image.extend(b"\0" * (payload_off - len(image)))
    image.extend(payload)
    assert len(image) == total
    out = d / "lecture.fqv"
    out.write_bytes(image)
    frames_mb = sum(len(f) for v in order for f in enc[v][1]) / 1e6
    print(f"packed {out.name}: {total / 1e6:.2f} MB  (frames {frames_mb:.2f} MB, audio {len(audio) / 1e6:.2f} MB, "
          f"{tl['total'] / rate / 60:.1f} min)")
    return out


if __name__ == "__main__":
    pack(sys.argv[1] if len(sys.argv) > 1 else "quantum-behavior")
