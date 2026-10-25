"""FQV: a tiny animation codec the ESP32 can decode straight out of flash.

Per scene: one 256-colour RGB565 palette. Per frame: a bitmap of which 16x16 tiles changed since the
previous frame, then those tiles' 8-bit palette indices, deflated. A keyframe is simply a frame where
every tile changed. Decoding is: inflate, then for each changed tile look up 256 palette entries.

  encode_scene(frames_rgb) -> (palette_rgb565 (256,), [frame blobs])
  frame blob = u16 n_tiles | u8 tile_bitmap[113] | zlib(indices of changed tiles, tile-major)
"""
import struct
import zlib

import numpy as np
from PIL import Image

TILE = 16
GRID = 480 // TILE                 # 30 x 30 tiles
BITMAP = (GRID * GRID + 7) // 8    # 113 bytes


def build_palette(sample_rgb):
    """256-colour palette from a sample of frames (median cut), as an (N,3) uint8 array."""
    strip = np.concatenate([f.reshape(-1, 3) for f in sample_rgb])[None, :, :]
    img = Image.fromarray(strip.astype(np.uint8), "RGB")
    pal_img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    pal = np.array(pal_img.getpalette()[:256 * 3], dtype=np.uint8).reshape(-1, 3)
    return pal, pal_img


def index_frame(rgb, pal_img):
    img = Image.fromarray(rgb, "RGB").quantize(palette=pal_img, dither=Image.Dither.NONE)
    return np.asarray(img, dtype=np.uint8)


def to565(pal):
    r, g, b = (pal[:, 0].astype(np.uint16) >> 3), (pal[:, 1].astype(np.uint16) >> 2), (pal[:, 2].astype(np.uint16) >> 3)
    return ((r << 11) | (g << 5) | b).astype("<u2")


def tiles(idx):
    """(480,480) -> (900, 256) tile-major."""
    return idx.reshape(GRID, TILE, GRID, TILE).swapaxes(1, 2).reshape(GRID * GRID, TILE * TILE)


def encode_frame(prev_tiles, cur_tiles, level=9):
    changed = np.ones(GRID * GRID, bool) if prev_tiles is None else (prev_tiles != cur_tiles).any(axis=1)
    bitmap = np.packbits(changed, bitorder="little").tobytes()
    data = zlib.compress(cur_tiles[changed].tobytes(), level) if changed.any() else b""
    return struct.pack("<H", int(changed.sum())) + bitmap + data


def encode_scene(frames_rgb, keyframes_at=()):
    """frames_rgb: list of (480,480,3) uint8. keyframes_at: frame numbers that must be self-contained."""
    sample = frames_rgb[:: max(1, len(frames_rgb) // 24)]
    pal, pal_img = build_palette(sample)
    out, prev = [], None
    keys = set(keyframes_at) | {0}
    for k, f in enumerate(frames_rgb):
        cur = tiles(index_frame(f, pal_img))
        out.append(encode_frame(None if k in keys else prev, cur))
        prev = cur
    return to565(pal), out


def decode_frame(blob, prev_tiles):
    n = struct.unpack_from("<H", blob)[0]
    changed = np.unpackbits(np.frombuffer(blob[2:2 + BITMAP], np.uint8), bitorder="little")[:GRID * GRID].astype(bool)
    cur = prev_tiles.copy() if prev_tiles is not None else np.zeros((GRID * GRID, TILE * TILE), np.uint8)
    if n:
        cur[changed] = np.frombuffer(zlib.decompress(blob[2 + BITMAP:]), np.uint8).reshape(n, TILE * TILE)
    return cur


def untile(t):
    return t.reshape(GRID, GRID, TILE, TILE).swapaxes(1, 2).reshape(480, 480)
