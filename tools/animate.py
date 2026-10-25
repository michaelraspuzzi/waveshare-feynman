"""Rasterize animated scenes into frames.

  render_frame(scene, T, t) -> 480x480x3 uint8
  render_scene(scene, T)    -> list of zlib-compressed little-endian RGB565 frames at scenes.FPS

The server streams these as dirty-rect deltas (see server/frames.py).
"""
import io
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenes  # noqa: E402
from motion import Beats  # noqa: E402


def render_frame(name, T, t, beats=((), ())):
    svg, bg = scenes.SCENES[name](T, t, Beats(*beats))
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=480, output_height=480)
    ov = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"), dtype=np.float32)
    base = bg if bg is not None else np.zeros((480, 480, 3), np.float32)
    a = ov[..., 3:4] / 255.0
    return np.clip(base * (1 - a) + ov[..., :3] * a, 0, 255).astype(np.uint8)


def to_rgb565(rgb):
    r = rgb[..., 0].astype(np.uint16) >> 3
    g = rgb[..., 1].astype(np.uint16) >> 2
    b = rgb[..., 2].astype(np.uint16) >> 3
    return ((r << 11) | (g << 5) | b).astype("<u2")


def _job(args):
    name, T, k, beats = args
    rgb = render_frame(name, T, k / scenes.FPS, beats)
    return zlib.compress(to_rgb565(rgb).tobytes(), 6)


def render_scene(name, T, beats=((), ()), pool=None):
    n = int(T * scenes.FPS) + 1
    jobs = [(name, T, k, beats) for k in range(n)]
    if pool:
        return pool.map(_job, jobs, chunksize=8)
    return [_job(j) for j in jobs]


def frame_to_rgb(blob):
    v = np.frombuffer(zlib.decompress(blob), dtype="<u2").reshape(480, 480)
    return np.stack([(v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3], -1).astype(np.uint8)


def segment_beats(lecture_id="quantum-behavior"):
    """{scene: (T, (starts, ends))} from the rendered timeline, for previews."""
    import json
    root = Path(__file__).resolve().parent.parent
    tl = json.loads((root / "build" / "lectures" / lecture_id / "timeline.json").read_text())
    out = {}
    for vid, a in tl["anim"].items():
        ls = [ln for ln in tl["lines"] if ln["visual"] == vid]
        rate = tl["rate"]
        out[vid] = ((a["end"] - a["start"]) / rate,
                    (tuple((ln["start"] - a["start"]) / rate for ln in ls),
                     tuple((ln["end"] - a["start"]) / rate for ln in ls)))
    return out


if __name__ == "__main__":
    # Contact sheet for one scene: a frame shortly after each narration line starts.
    #   python tools/animate.py 01-bullets   -> build/preview/beats-01-bullets.png
    name = sys.argv[1]
    T, beats = segment_beats()[name]
    times = [s + 1.4 for s in beats[0]] + [T - 0.1]
    cols = 4
    rows = -(-len(times) // cols)
    sheet = Image.new("RGB", (cols * 488, rows * 488), (40, 40, 40))
    for i, t in enumerate(times):
        sheet.paste(Image.fromarray(render_frame(name, T, min(t, T), beats)), ((i % cols) * 488, (i // cols) * 488))
    out = Path(__file__).resolve().parent.parent / "build" / "preview" / f"beats-{name}.png"
    sheet.resize((sheet.width // 2, sheet.height // 2)).save(out)
    print(out)
