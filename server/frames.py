"""Dirty-rect delta encoding for animation frames.

A frame message is
  0x03 | u8 n | n x ( u16 x | u16 y | u16 w | u16 h | u32 len | zlib(rgb565 LE pixels, row-major) )
and patches the image currently on screen. The screen is split into 16-row bands; each band that
changed sends one rect spanning its changed columns, so decoding needs at most 480*16*2 bytes.
"""
import struct
import zlib

import numpy as np

BAND = 16


def encode_delta(prev, cur):
    """prev/cur: (480, 480) uint16 arrays. Returns the message, or None if nothing changed."""
    diff = prev != cur
    rects = []
    for y0 in range(0, 480, BAND):
        cols = np.flatnonzero(diff[y0:y0 + BAND].any(axis=0))
        if not len(cols):
            continue
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        block = cur[y0:y0 + BAND, x0:x1]
        data = zlib.compress(block.astype("<u2").tobytes(), 6)
        rects.append(struct.pack("<HHHHI", x0, y0, x1 - x0, block.shape[0], len(data)) + data)
    if not rects:
        return None
    return bytes([0x03, len(rects)]) + b"".join(rects)
