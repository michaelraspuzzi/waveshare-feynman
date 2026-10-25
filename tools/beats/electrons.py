"""Electrons: lumps that add like waves, choreographed to the narration.

Lines (B[i]):
 0 "Now we do it with electrons."                                -> ELECTRONS punches in
 1 "An electron gun: a hot wire and a little voltage. Same wall..." -> filament heats, +V, wall draws
 2 "...a little counter that goes click..."                        -> backstop + counter box, "click"
 3 "...The clicks are all the same size. Click. Click. Click."     -> three identical clicks + meter pulses
 4 "Never half a click. So electrons come in lumps, like bullets."  -> 1/2 click crossed, LUMPS
 5 "Turn the gun down very low, and still each click is a whole electron." -> dial turns down, single electrons
 6 "So we move the counter around, and we count clicks..."         -> counter sweeps, the flood begins
 7 "And what do we get? Big, small, big, small. The wave pattern." -> fringes, big/small labels, curve
 8 "Lumps when they arrive, but they add up with interference."    -> split panel: lumps | waves
 9 "That should bother you. It bothered everybody."                -> shake + ?!
"""
import math
import random
from functools import lru_cache

import numpy as np

import make_visuals as mv
from make_visuals import (DIM, HOLE1, HOLE2, HOLE_R, INK, SRC_X, STOP_X, VIOLET, WALL_X, Y_BOT, Y_MID, Y_TOP,
                          text)
from motion import (Beats, callout, cross, draw_line, draw_path, g, kinetic, lerp, pill, pop, prog, pulse,
                    shake, slide_in)
from scenes import curve_pts, electron_flight, histogram, overlay, p_both, paint_dots, sampler

RED = "#ff6b6b"
GREEN = "#7be38f"


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def heat_color(k):
    """Filament glow: dull grey -> orange -> near white as it warms up."""
    stops = [(0.0, "#555555"), (0.5, "#ff8a3d"), (1.0, "#fff3c4")]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if k <= b:
            f = (k - a) / (b - a)
            c = [round(lerp(x, y, f)) for x, y in zip(_hex(ca), _hex(cb))]
            return "#%02x%02x%02x" % tuple(c)
    return stops[-1][1]


def gun_svg(t, B):
    k = prog(t, B[1] + 0.4, 2.2)
    col = heat_color(k)
    pts = " ".join(f"{SRC_X - 14 + i * 4},{Y_MID + (6 if i % 2 else -6)}" for i in range(8))
    out = ""
    if k > 0.2:                                           # glow halo
        out += f'<circle cx="{SRC_X}" cy="{Y_MID}" r="{18 + 6 * k:.1f}" fill="{col}" opacity="{0.18 * k:.2f}"/>'
    out += f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.8"/>'
    out += f'<circle cx="{SRC_X}" cy="{Y_MID}" r="24" fill="none" stroke="{VIOLET}" stroke-width="1.4" opacity="0.6"/>'
    return out


def wall_svg(t, t0):
    p = prog(t, t0, 0.9)
    if p <= 0:
        return ""
    out = draw_line(WALL_X, Y_TOP, WALL_X, Y_TOP + (Y_BOT - Y_TOP) * p, 1, INK, 5, cap="butt")
    if p >= 1:
        gap = HOLE_R * prog(t, t0 + 0.9, 0.3)
        for hy in (HOLE1, HOLE2):
            out += f'<rect x="{WALL_X - 4}" y="{hy - gap:.1f}" width="8" height="{2 * gap:.1f}" fill="#000"/>'
        out += pop(text(WALL_X - 16, HOLE1 + 5, "1", 14, DIM, "middle"), t, t0 + 1.0, (WALL_X - 16, HOLE1))
        out += pop(text(WALL_X - 16, HOLE2 + 5, "2", 14, DIM, "middle"), t, t0 + 1.1, (WALL_X - 16, HOLE2))
    return out


def detector_y(t, B):
    """The counter sits still for the first clicks, then sweeps the backstop while we count."""
    y0 = Y_MID - 34
    if t < B[6]:
        return y0
    return y0 + 105 * math.sin(2 * math.pi * (t - B[6]) / 3.6)


@lru_cache(maxsize=None)
def _arrivals(T, starts, ends):
    """(time, x, y, flight) for every electron that lands. flight=True shows its wave crossing both holes."""
    B = Beats(starts, ends)
    draw, rnd = sampler(p_both, 21)
    out = []
    y0 = Y_MID - 34
    for k in (2, 3, 4):                                   # "Click. Click. Click." on the counter
        out.append((B.sub(3, k, 5) + 0.25, STOP_X - 8 - rnd.uniform(0, 30), y0 + rnd.uniform(-4, 4), True))
    for k in (1, 2, 3):                                   # gun turned down low: lone electrons
        out.append((B.sub(5, k, 4) + 0.6, STOP_X - 8 - rnd.uniform(0, 30), draw(), True))
    a, b = B[6] + 0.8, T - 0.6
    n = 1500
    for j in range(n):                                    # the flood, speeding up
        out.append((a + (b - a) * (j / n) ** 0.6, STOP_X - 6 - rnd.uniform(0, 40), draw(), False))
    return sorted(out)


def fringe_marks():
    """(y, is_peak) for the visible maxima and minima of the pattern."""
    ys = list(range(Y_TOP + 2, Y_BOT - 1))
    v = [p_both(y) for y in ys]
    pk = max(v)
    out = []
    for i in range(1, len(ys) - 1):
        if v[i] > v[i - 1] and v[i] >= v[i + 1] and v[i] > 0.3 * pk:
            out.append((ys[i], True))
        elif v[i] < v[i - 1] and v[i] <= v[i + 1] and 0.18 * pk < max(v[i - 6:i + 7]):
            out.append((ys[i], False))
    return out


def scene(T, t, B):
    body = kinetic("ELECTRONS", t, B[0] + 0.1, hold=max(1.2, B.end(0) - B[0] + 0.6), color=VIOLET, size=52)

    # 1. the gun warms up, a little voltage, the same wall
    body += slide_in(gun_svg(t, B), t, B[1], dx=-80)
    body += callout(SRC_X + 6, Y_MID - 20, "hot wire", t, B[1] + 1.4, "#ff8a3d", dx=30, dy=-58, out=B[2])
    body += callout(SRC_X + 18, Y_MID + 16, "+V", t, B.sub(1, 1, 3), VIOLET, dx=30, dy=60, out=B[2] + 0.4)
    body += wall_svg(t, B.sub(1, 2, 3) - 0.3)

    # 2. backstop + the counter
    body += draw_line(STOP_X, Y_TOP, STOP_X, Y_BOT, prog(t, B[2], 0.7), DIM, 3)
    dy = detector_y(t, B)
    if t > B[2] + 0.6 and t < B[7] + 0.5:
        box = f'<rect x="{STOP_X - 10}" y="{dy - 11:.1f}" width="20" height="22" rx="4" fill="#111" stroke="{INK}" stroke-width="2"/>'
        box += f'<circle cx="{STOP_X}" cy="{dy:.1f}" r="3" fill="{INK}"/>'
        fade_out = 1 - prog(t, B[7], 0.5)
        body += g(pop(box, t, B[2] + 0.6, (STOP_X, dy)), o=fade_out)
        body += callout(STOP_X + 10, dy, "counter", t, B[2] + 1.2, INK, dx=40, dy=-26, out=B[3], size=13)
    if B[6] < t < B[7]:
        body += pop(text(446, 64, "sweeping...", 13, DIM, "end"), t, B[6] + 0.3, (420, 60))

    # 3. click meter: every pulse the same height
    events = _arrivals(T, tuple(B.starts), tuple(B.ends))
    meter_on = B[3] < t < B[4] + 0.4
    if meter_on:
        mx, my = 40, 344
        meter = text(mx, my - 40, "click size", 12, DIM)
        meter += f'<line x1="{mx}" y1="{my}" x2="{mx + 110}" y2="{my}" stroke="#333" stroke-width="1.5"/>'
        for i, (t0, *_rest) in enumerate(events[:3]):
            if t >= t0:
                h = 30 * prog(t, t0, 0.15)
                x = mx + 12 + i * 34
                meter += f'<rect x="{x}" y="{my - h:.1f}" width="16" height="{h:.1f}" rx="2" fill="{VIOLET}"/>'
        meter += draw_line(mx, my - 30, mx + 110, my - 30, prog(t, events[2][0] + 0.3, 0.4), GREEN, 1.4, dash="4 3")
        body += g(meter, o=1 - prog(t, B[4], 0.4))

    # 4. never half a click -> LUMPS
    body += kinetic("LUMPS", t, B.sub(4, 1, 3), hold=B.end(4) - B.sub(4, 1, 3) - 0.2, color=VIOLET, y=190,
                    sub="like bullets", sub_color=DIM)
    if B[4] < t < B.end(4) + 0.3:
        body += pop(text(240, 300, "½ click", 22, INK, "middle", "700"), t, B[4] + 0.2, (240, 294))
        body += cross(240, 293, t, B[4] + 0.6, RED, 36)

    # 5. turn the gun down: a dial
    if B[5] < t < B[6] + 0.5:
        cx, cy = SRC_X + 6, Y_MID + 82
        ang = lerp(-35, -150, prog(t, B[5] + 0.4, 1.4))     # degrees, sweeping down to "low"
        a = math.radians(ang)
        dial = f'<circle cx="{cx}" cy="{cy}" r="20" fill="#111" stroke="{INK}" stroke-width="2"/>'
        dial += draw_line(cx, cy, cx + 15 * math.cos(a), cy - 15 * math.sin(a), 1, VIOLET, 3)
        dial += text(cx, cy + 36, "low", 12, DIM, "middle")
        body += g(pop(dial, t, B[5] + 0.1, (cx, cy)), o=1 - prog(t, B[6], 0.5))

    # electrons: waves through both holes for the lone ones, then dots on the screen
    bg = np.zeros((480, 480, 3), np.float32)
    dots, ys = [], []
    for t0, x, y, flight in events:
        if t < t0 - 1.0:
            break
        if flight:
            body += electron_flight(t, t0, 1, False)
        if t >= t0:
            dots.append((x, y))
            if t0 >= B[6]:
                ys.append(y)
            if t - t0 < 0.4 and flight:                   # the click
                body += pulse(x, y, t, t0, INK, r=8, rings=1, period=0.4)
                body += pop(pill(x - 52, y + 5, "click!", INK, 13), t, t0, (x - 52, y), out=t0 + 0.55)
    paint_dots(bg, dots, VIOLET)

    # 6-7. histogram, fringes, big/small
    if t > B[6] + 1.0:
        bars, _ = histogram(ys, VIOLET, opacity=0.7)
        body += bars
        body += text(446, 382, f"{len(dots)} electrons", 13, DIM, "end")
    pk = mv.peak_of(p_both)
    pts = [tuple(map(float, s.split(","))) for s in curve_pts(p_both, pk).split()]
    body += draw_path(pts, prog(t, B.sub(7, 3, 5), 1.6), INK, 2.4)
    if B[7] < t < B[8] + 0.4:
        marks = [m for m in fringe_marks() if Y_TOP + 20 < m[0] < Y_BOT - 20][:4]
        for i, (fy, peak) in enumerate(marks):
            label = "big" if peak else "small"
            col = GREEN if peak else DIM
            body += g(pop(pill(222, fy + 5, label, col, 12), t, B.sub(7, i + 1, 6), (222, fy)),
                      o=1 - prog(t, B[8], 0.4))

    # 8. lumps when they arrive | like waves when they add
    if t > B[8]:
        def card(x, title, sub, col):
            return (f'<rect x="{x}" y="330" width="196" height="52" rx="12" fill="#111" stroke="{col}" stroke-width="2"/>'
                    + text(x + 98, 352, title, 17, col, "middle", "800") + text(x + 98, 372, sub, 12, DIM, "middle"))
        o = 1 - prog(t, B[9] + 1.6, 0.4)
        lump = card(36, "arrive: LUMPS", "one click at a time", VIOLET)
        wave = card(248, "add: like WAVES", "big, small, big, small", GREEN)
        body += g(slide_in(lump, t, B[8] + 0.2, dx=-40) + slide_in(wave, t, B.sub(8, 1, 2), dx=40), o=o)

    # 9. that should bother you
    sx, sy = shake(t, B[9] + 0.2, 0.6, 7)
    body += kinetic("?!", t, B[9] + 0.2, hold=B.end(9) - B[9], color="#ff8a3d", y=190, size=80,
                    sub="it bothered everybody", sub_color=DIM)
    if sx or sy:
        body = g(body, x=sx, y=sy)
        bg = np.roll(bg, (int(round(sy)), int(round(sx))), axis=(0, 1))
    return overlay(body, "ELECTRONS", VIOLET), bg
