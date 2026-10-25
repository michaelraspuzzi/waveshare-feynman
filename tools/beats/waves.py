"""Water waves: interference with something we can watch, choreographed to the narration.

Lines (B[i]):
 0 "Now let's do the same thing with water waves."                -> WATER WAVES punches in, pool fades up
 1 "A little thing bobbing up and down ... circular waves."        -> bobbing source, rings spread
 2 "Same wall, same two holes. Each hole ... a new source"         -> wall draws, holes light up, callouts
 3 "...we measure how much the water jiggles. The intensity."      -> backstop, buoy sweeps, intensity meter
 4 "...can be any size at all. It doesn't come in lumps."          -> NO LUMPS, meter glides smoothly
 5 "With one hole open, we get a nice smooth bump..."              -> plug in hole 2, I1 bump draws
 6 "But with both holes open ... big, small, big, small."          -> plug out, fringe curve, labels on beat
 7 "At some places the two waves arrive in step..."                -> inset: crests add
 8 "At other places ... going down, and they cancel."              -> inset: crests cancel
 9 "That's interference ... not I one plus I two."                 -> I1+I2 ghost curve, the inequality
10 "You have to add the heights ... then square. The cross term"   -> formula builds, cross term lit up
"""
import math

import numpy as np

import make_visuals as mv
from make_visuals import (CYAN, DIM, HOLE1, HOLE2, HOLE_R, INK, SRC_X, STOP_X, VIOLET, WALL_X, Y_BOT, Y_MID,
                          Y_TOP, CURVE_X0, CURVE_W, text)
from motion import (FAR, between, callout, draw_line, draw_path, ease_in_out, g, kinetic, lerp, pill, pop,
                    prog, pulse, slide_in)
from scenes import K, SPEED, curve_pts, hexrgb, overlay, p_both, p_sum

FIELD_FPS = 7.5

_YY, _XX = np.mgrid[0:480:2, 0:480:2].astype(np.float32)
POOL = np.array([4, 16, 26], np.float32)
D_HOLE = {h: math.hypot(WALL_X - SRC_X, h - Y_MID) for h in (HOLE1, HOLE2)}


def plug_times(B):
    return B[5] + 0.4, B[6] + 0.3          # hole 2 stops / restarts emitting


def field(t, B):
    """Instantaneous water height (half resolution), or None before the source starts."""
    if t < B[1]:
        return None
    t = math.floor(t * FIELD_FPS) / FIELD_FPS     # the ripples step at 7.5 fps: half the bytes, still reads as water
    w = SPEED * K
    ts = t - B[1]
    wall_t = B[2] + 0.9
    r0 = np.hypot(_XX - SRC_X, _YY - Y_MID)
    src = np.where(r0 < SPEED * ts, np.cos(K * r0 - w * ts) / np.sqrt(r0 / 30 + 1), 0.0)
    if t < wall_t:
        f = src
    else:
        f = np.where(_XX < WALL_X - 2, src, 0.0)
        right = _XX > WALL_X + 2
        off2, on2 = plug_times(B)
        for hy, spans in ((HOLE1, [(wall_t, FAR)]), (HOLE2, [(wall_t, off2), (on2, FAR)])):
            r = np.hypot(_XX - WALL_X, _YY - hy)
            wave = 0.8 * np.cos(K * (r + D_HOLE[hy]) - w * ts) / np.sqrt(r / 30 + 1)
            for on, off in spans:
                if t < on:
                    continue
                m = right & (r < SPEED * (t - on))
                if t > off:
                    m &= r > SPEED * (t - off)
                f = f + np.where(m, wave, 0.0)
    f[(_YY < Y_TOP) | (_YY > Y_BOT) | (_XX > STOP_X - 3)] = 0
    return f


def background(t, B, f):
    pool_o = prog(t, B[0] + 0.8, 1.0)
    if pool_o <= 0:
        return None
    rgb = np.zeros(_XX.shape + (3,), np.float32)
    inside = (_YY >= Y_TOP) & (_YY <= Y_BOT) & (_XX < STOP_X - 2)
    rgb[inside] = POOL * pool_o
    if f is not None:
        v = np.clip(np.round(f * 2.5) / 2.5, -1, 1)      # posterized: reads as water, compresses well
        c = hexrgb(CYAN)
        rgb += np.clip(v, 0, 1)[..., None] * c * 0.75
        rgb -= np.clip(-v, 0, 1)[..., None] * POOL * 0.6
    np.clip(rgb, 0, 255, out=rgb)
    return np.repeat(np.repeat(rgb, 2, axis=0), 2, axis=1)


def wall_svg(t, B):
    p = prog(t, B[2], 0.9)
    if p <= 0:
        return ""
    out = draw_line(WALL_X, Y_TOP, WALL_X, Y_TOP + (Y_BOT - Y_TOP) * p, 1, INK, 5, cap="butt")
    if p >= 1:
        gap = HOLE_R * prog(t, B[2] + 0.9, 0.3)
        for hy in (HOLE1, HOLE2):
            out += f'<rect x="{WALL_X - 4}" y="{hy - gap:.1f}" width="8" height="{2 * gap:.1f}" fill="#000"/>'
        out += pop(text(WALL_X - 16, HOLE1 + 5, "1", 14, DIM, "middle"), t, B[2] + 1.1, (WALL_X - 16, HOLE1))
        out += pop(text(WALL_X - 16, HOLE2 + 5, "2", 14, DIM, "middle"), t, B[2] + 1.25, (WALL_X - 16, HOLE2))
    return out


def extrema(fn):
    """Alternating peaks/troughs of fn down the backstop, starting at the biggest peak."""
    ys = list(range(Y_TOP + 2, Y_BOT - 1))
    vals = [fn(y) for y in ys]
    ext = [(ys[i], "big" if vals[i] > vals[i - 1] else "small") for i in range(1, len(ys) - 1)
           if (vals[i] - vals[i - 1]) * (vals[i + 1] - vals[i]) < 0]
    top = max(range(len(ext)), key=lambda i: fn(ext[i][0]) if ext[i][1] == "big" else -1)
    seq = ext[top:top + 4]
    if len(seq) < 4:
        seq = ext[max(0, top - 2):max(0, top - 2) + 4]
    return seq


_EXT = extrema(p_both)


def pts_of(fn, pk):
    return [tuple(map(float, s.split(","))) for s in curve_pts(fn, pk).split()]


def inset(t, B):
    """Card with two waves and their sum: in step (adds), then opposite (cancels)."""
    o = between(t, B[7] + 0.2, B[9] + 0.2)
    if o <= 0:
        return ""
    x0, y0, w, h = 12, 214, 150, 112
    shift = math.pi * prog(t, B[8] + 0.3, 0.9, ease_in_out)
    ph = 4.0 * t

    def wave(yc, amp, phase, color, width=2.2):
        pts = " ".join(f"{x0 + 10 + i:.0f},{yc - amp * math.sin(0.11 * i - phase):.1f}" for i in range(0, w - 19, 2))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"/>'

    body = (f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="12" fill="#0b0b0b" stroke="{CYAN}" stroke-width="1.5"/>'
            + wave(y0 + 20, 8, ph, CYAN) + wave(y0 + 44, 8, ph + shift, VIOLET))
    sum_amp = 16 * abs(math.cos(shift / 2))
    body += draw_line(x0 + 10, y0 + 58, x0 + w - 10, y0 + 58, 1, "#333", 1)
    body += wave(y0 + 82, sum_amp, ph + shift / 2, INK, 2.8)
    label = "in step: 2×" if shift < 1.2 else "opposite: 0"
    color = "#7be38f" if shift < 1.2 else "#ff8a8a"
    body += text(x0 + w / 2, y0 + h - 6, label, 13, color, "middle", "700")
    return g(slide_in(body, t, B[7] + 0.2, dx=-60), o=o)


def scene(T, t, B):
    f = field(t, B)
    body = kinetic("WATER WAVES", t, B[0] + 0.25, hold=2.3, color=CYAN, size=50,
                   sub="same experiment, different stuff", sub_color=DIM)

    # 1. bobbing source
    if t > B[1]:
        bob = 3 * math.sin(SPEED * K * (t - B[1]))
        src = (f'<circle cx="{SRC_X}" cy="{Y_MID + bob:.1f}" r="7" fill="{CYAN}"/>'
               f'<circle cx="{SRC_X}" cy="{Y_MID + bob:.1f}" r="11" fill="none" stroke="{INK}" stroke-width="1.5"/>')
        body += pop(src, t, B[1], (SRC_X, Y_MID))
        body += callout(SRC_X, Y_MID - 12, "bobbing", t, B[1] + 1.0, CYAN, dx=34, dy=-70, out=B[2] + 0.3, size=13)

    # 2. wall: each hole becomes a new source
    body += wall_svg(t, B)
    for i, hy in enumerate((HOLE1, HOLE2)):
        body += pulse(WALL_X, hy, t, B[2] + 1.4 + 0.4 * i, CYAN, r=14, rings=3)
    body += callout(WALL_X + 4, HOLE1, "new source", t, B[2] + 2.2, CYAN, dx=56, dy=-58, out=B[3] + 0.2, size=13)
    body += callout(WALL_X + 4, HOLE2, "new source", t, B[2] + 3.0, CYAN, dx=56, dy=56, out=B[3] + 0.2, size=13)

    # 3. backstop and a buoy that measures the jiggle
    body += draw_line(STOP_X, Y_TOP, STOP_X, Y_BOT, prog(t, B[3], 0.8), DIM, 3)
    pk = mv.peak_of(p_both)
    if B[3] + 0.8 < t < B[5] + 0.4:
        o = 1 - prog(t, B[5], 0.4)
        y = Y_MID + 100 * math.sin(2 * math.pi * (t - B[3] - 0.8) / 7.0)
        h = 0.0
        if f is not None:
            h = float(f[int(y) // 2, (STOP_X - 8) // 2])
        r = 5 + 3 * abs(h)
        meter = (f'<circle cx="{STOP_X - 8}" cy="{y:.1f}" r="{r:.1f}" fill="{INK}"/>'
                 f'<rect x="{CURVE_X0}" y="{y - 6:.1f}" width="{CURVE_W * p_both(y) / pk * (0.85 + 0.15 * h):.1f}" '
                 f'height="12" rx="6" fill="{CYAN}"/>')
        body += g(pop(meter, t, B[3] + 0.8, (STOP_X - 8, y)), o=o)
        body += callout(CURVE_X0 + 20, y - 8, "intensity", t, B[3] + 1.8, CYAN, dx=40, dy=-34, out=B[4], size=13)

    # 4. no lumps
    body += kinetic("NO LUMPS", t, B[4] + 0.2, hold=B.end(4) - B[4] - 0.4, color=CYAN, y=196, size=50,
                    sub="any size at all", sub_color=INK)

    # 5. one hole: the plug, and a smooth bump
    off2, on2 = plug_times(B)
    if B[5] <= t <= B[6] + 0.8:
        k = prog(t, B[6], 0.6, ease_in_out)
        plug = (f'<rect x="{WALL_X - 7}" y="{HOLE2 - HOLE_R - 3}" width="14" height="{2 * HOLE_R + 6}" rx="2" '
                f'fill="#555" stroke="{INK}" stroke-width="1.5"/>')
        body += g(slide_in(plug, t, B[5], dx=-50), x=-60 * k, o=1 - k)
    pts1 = pts_of(mv.p1, pk)
    dim1 = 1 - 0.65 * prog(t, B[6] + 0.6, 0.6)
    body += draw_path(pts1, prog(t, B[5] + 1.0, 1.6), CYAN, 2.4, dim1, "5 4" if t > B[6] else None)
    if t > B[5] + 2.0:
        body += g(pop(pill(442, HOLE1 - 50, "I₁", CYAN, 15), t, B[5] + 2.2, (442, HOLE1 - 56)), o=dim1)

    # 6. both holes: fringes, with big/small on the beat
    body += draw_path(pts_of(p_both, pk), prog(t, B[6] + 0.6, 1.4), CYAN, 3.2)
    for i, (ey, kind) in enumerate(_EXT):
        t0 = B.sub(6, i + 1, 5)
        ex = CURVE_X0 + CURVE_W * p_both(ey) / pk
        lx = min(ex + 26, 448) if kind == "big" else ex + 30
        c = INK if kind == "big" else DIM
        body += g(pop(pill(lx, ey + 5, kind, c, 12), t, t0, (lx, ey)), o=between(t, t0, B[9]))
        body += pulse(ex, ey, t, t0, CYAN, r=10, rings=1, period=0.6)

    # 7-8. in step / opposite
    body += inset(t, B)
    if _EXT:
        big = next((e for e in _EXT if e[1] == "big"), None)
        small = next((e for e in _EXT if e[1] == "small"), None)
        if big:
            body += pulse(CURVE_X0 + CURVE_W * p_both(big[0]) / pk, big[0], t, B[7] + 0.8, "#7be38f", r=14, rings=3)
        if small:
            body += pulse(CURVE_X0 + CURVE_W * p_both(small[0]) / pk, small[0], t, B[8] + 1.2, "#ff8a8a", r=14, rings=3)

    # 9. not I1 + I2
    ps = pts_of(p_sum, pk)
    body += draw_path(ps, prog(t, B[9] + 0.9, 1.4), DIM, 1.8, 0.9, "3 4")
    if t > B[9] + 1.6:
        body += g(pop(pill(424, Y_BOT - 14, "I₁ + I₂", DIM, 12), t, B[9] + 1.6, (424, Y_BOT - 20)),
                  o=between(t, B[9] + 1.6, FAR))
    if B[9] < t < B[10] + 0.4:
        eq = (f'<rect x="130" y="336" width="220" height="40" rx="20" fill="#111" stroke="{CYAN}" stroke-width="2"/>'
              + text(240, 363, "I₁₂ ≠ I₁ + I₂", 22, CYAN, "middle", "800"))
        body += g(pop(eq, t, B[9] + 0.3, (240, 356)), o=1 - prog(t, B[10], 0.4))

    # 10. add heights, then square: the cross term
    if t > B[10] + 0.2:
        body += pop(text(240, 352, "I₁₂ = |h₁ + h₂|²", 20, INK, "middle", "800"), t, B[10] + 0.2, (240, 346))
        t2 = B.sub(10, 1, 2)
        if t > t2:
            hl = prog(t, t2 + 0.6, 0.5)
            row = (text(54, 382, "= I₁ + I₂ +", 18, INK, "start", "700")
                   + f'<rect x="156" y="364" width="164" height="26" rx="8" fill="{CYAN}" opacity="{0.22 * hl:.2f}" '
                     f'stroke="{CYAN}" stroke-width="{1.5 * hl:.1f}"/>'
                   + text(164, 382, "2√(I₁I₂) cos δ", 18, CYAN, "start", "800"))
            body += slide_in(row, t, t2, dy=14, dx=0)
            body += callout(320, 368, "interference", t, t2 + 1.0, CYAN, dx=70, dy=-8, size=12)
    return overlay(body, "WATER WAVES", CYAN), background(t, B, f)
