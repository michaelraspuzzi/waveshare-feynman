"""Dimmer light: you can't sneak a look, choreographed to the narration.

Lines (B[i]):
 0 "Well, maybe our light is too strong. It knocks the electron around."  -> photon squiggle kicks an electron off course
 1 "So let's make it gentler. Make the light dimmer."                     -> dimmer knob turns, rays shrink
 2 "But light comes in lumps too, photons. Dimmer ... fewer photons..."   -> PHOTONS, discrete dots fly out, "fewer, not softer"
 3 "So sometimes the electron goes by and we miss it. No flash at all."   -> "missed" tags on flash-less electrons
 4 "The ones we saw make P one plus P two. The ones we missed..."         -> seen vs missed histograms: humps vs fringes
 5 "Use longer wavelength light... the flash is so blurry..."             -> squiggle stretches and reddens, flash blurs over both holes
 6 "Right when you lose the ability to say which hole, the interference comes back." -> curve morphs humps -> fringes
 7 "Nature is very careful. You can never have both..."                   -> seesaw: which-way vs wiggles
"""
import math
import random
from functools import lru_cache

import numpy as np

import make_visuals as mv
from make_visuals import (AMBER, DIM, HOLE1, HOLE2, INK, SRC_X, STOP_X, VIOLET, WALL_X, Y_BOT, Y_MID, Y_TOP,
                          CURVE_X0, CURVE_W, backstop, filament, flash, text, wall)
from motion import (Beats, between, callout, draw_path, ease_in_out, g, kinetic, lerp, osc, pill, pop, prog,
                    pulse, slide_in)
from scenes import blank, curve_pts, electron_flight, hexrgb, histogram, overlay, p_both, p_sum

RED = "#ff5a4d"
LAMP = (WALL_X + 52, Y_MID)
KNOB = (WALL_X + 58, 300)
MID = (HOLE1 + HOLE2) / 2


def brightness(t, B):
    return lerp(1.0, 0.35, prog(t, B[1] + 0.6, 1.6, ease_in_out))


def blur(t, B):
    """0 = sharp flash at one hole, 1 = a glow too wide to tell the holes apart."""
    return prog(t, B[5] + 2.5, 4.0, ease_in_out)


def mix_color(a, b, k):
    ca, cb = hexrgb(a), hexrgb(b)
    c = ca + (cb - ca) * k
    return "#" + "".join(f"{int(v):02x}" for v in c)


def lamp_svg(t, on):
    x, y = LAMP
    out = f'<circle cx="{x}" cy="{y}" r="9" fill="{AMBER}" opacity="{0.4 + 0.6 * on:.2f}"/>'
    for i in range(8):
        a = i * math.pi / 4 + 0.2 * t
        r2 = 13 + (9 + 4 * osc(t + i * 0.2, 0.9)) * on
        out += (f'<line x1="{x + 13 * math.cos(a):.1f}" y1="{y + 13 * math.sin(a):.1f}" '
                f'x2="{x + r2 * math.cos(a):.1f}" y2="{y + r2 * math.sin(a):.1f}" stroke="{AMBER}" '
                f'stroke-width="2" stroke-linecap="round" opacity="{0.3 + 0.7 * on:.2f}"/>')
    return out


def squiggle(x1, y1, x2, y2, wavelength, amp, color, phase=0.0, width=2.5, p0=0.0, p1=1.0):
    """Sine wave along a line segment, drawn between fractions p0..p1 of its length."""
    L = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    pts = []
    for i in range(41):
        f = lerp(p0, p1, i / 40)
        d = f * L
        off = amp * math.sin(2 * math.pi * d / wavelength - phase)
        pts.append((x1 + ux * d - uy * off, y1 + uy * d + ux * off))
    return draw_path(pts, 1.0, color, width)


def knob(t, B):
    x, y = KNOB
    a = math.radians(lerp(150, 30, prog(t, B[1] + 0.4, 1.6, ease_in_out)))
    out = f'<circle cx="{x}" cy="{y}" r="17" fill="#151515" stroke="{INK}" stroke-width="2"/>'
    out += (f'<line x1="{x}" y1="{y}" x2="{x - 13 * math.cos(a):.1f}" y2="{y - 13 * math.sin(a):.1f}" '
            f'stroke="{AMBER}" stroke-width="3" stroke-linecap="round"/>')
    for i in range(5):                                     # tick marks
        b = math.radians(150 - 30 * i)
        out += (f'<line x1="{x - 21 * math.cos(b):.1f}" y1="{y - 21 * math.sin(b):.1f}" '
                f'x2="{x - 25 * math.cos(b):.1f}" y2="{y - 25 * math.sin(b):.1f}" stroke="{DIM}" stroke-width="1.5"/>')
    out += text(x, y + 38, "dimmer", 12, DIM, "middle")
    return out


@lru_cache(maxsize=None)
def _photons(T, starts, ends):
    B = Beats(starts, ends)
    rnd = random.Random(3)
    out, t = [], B[2]
    while t < B[5]:
        t += rnd.expovariate(9.0 * brightness(t, B))
        out.append((t, rnd.uniform(0, 2 * math.pi)))
    return out


@lru_cache(maxsize=None)
def _electrons(T, starts, ends):
    """(t0, hole, y, seen). Seen ones land from P1/P2; missed ones (and all after the blur) from the fringes."""
    B = Beats(starts, ends)
    rnd = random.Random(17)

    def draw(fn):
        pk = mv.peak_of(fn)
        while True:
            y = rnd.uniform(Y_TOP, Y_BOT)
            if rnd.uniform(0, pk) < fn(y):
                return y

    out, t = [], B[3] + 0.3
    while t < T - 0.3:
        rate = 2.2 if t < B[4] else 14.0 if t < B[6] else 40.0
        t += rnd.expovariate(rate)
        hole = 1 if rnd.random() < 0.5 else 2
        if t < B[6]:
            seen = rnd.random() < 0.45
            y = draw(mv.p1 if hole == 1 else mv.p2) if seen else draw(p_both)
        else:
            seen, y = False, draw(p_both)
        out.append((t, hole, y, seen))
    return out


def kick(t, tk, hy, sign):
    """An electron flies to a hole; a photon squiggle hits it there and knocks it off course."""
    out = ""
    sx, sy = SRC_X + 22, Y_MID
    end = (STOP_X - 30, hy + sign * 120)
    if tk <= t < tk + 0.6:
        f = (t - tk) / 0.6
        out += f'<circle cx="{lerp(sx, WALL_X, f):.1f}" cy="{lerp(sy, hy, f):.1f}" r="5" fill="{VIOLET}"/>'
    elif tk + 0.6 <= t < tk + 1.3:
        f = ease_in_out((t - tk - 0.6) / 0.7)
        out += f'<circle cx="{lerp(WALL_X, end[0], f):.1f}" cy="{lerp(hy, end[1], f):.1f}" r="5" fill="{VIOLET}"/>'
        out += draw_path([(WALL_X, hy), (lerp(WALL_X, end[0], f), lerp(hy, end[1], f))], 1.0, VIOLET, 1.5, 0.5, "3 3")
    if tk + 0.15 <= t < tk + 0.65:                          # photon travelling lamp -> hole
        f = (t - tk - 0.15) / 0.5
        out += squiggle(LAMP[0], LAMP[1], WALL_X + 4, hy, 9, 5, AMBER, phase=20 * t, p0=max(0, f - 0.35), p1=f)
    if tk + 0.6 <= t < tk + 0.95:
        out += flash(WALL_X + 6, hy, AMBER, 15)
    if tk + 0.6 <= t < tk + 2.0:
        out += pop(pill(WALL_X + 70, hy + sign * 46, "kick!", AMBER, 14), t, tk + 0.65, (WALL_X + 70, hy + sign * 40),
                   out=tk + 1.7)
    return out


def scene(T, t, B):
    st, en = tuple(B.starts), tuple(B.ends)
    on = brightness(t, B)
    bk = blur(t, B)
    seesaw_k = prog(t, B[7], 0.6, ease_in_out)

    body = filament(VIOLET) + wall() + backstop() + lamp_svg(t, on)

    # 0. the light is too strong: kicks
    if t < B[1] + 1.0:
        body += kick(t, B[0] + 0.8, HOLE1, -1) + kick(t, B[0] + 3.0, HOLE2, 1)

    # 1. the dimmer
    if t > B[1]:
        body += pop(knob(t, B), t, B[1], KNOB)
        body += pulse(LAMP[0], LAMP[1], t, B[1] + 0.8, AMBER, r=22, rings=2)

    # 2. photons: discrete lumps flying out of the lamp
    body += kinetic("PHOTONS", t, B[2] + 0.2, hold=2.0, color=AMBER, y=150, size=48,
                    sub="light comes in lumps too", sub_color=INK)
    if B[2] < t < B[5] + 0.6:
        for t0, a in _photons(T, st, en):
            if t0 > t:
                break
            d = (t - t0) * 190
            if 10 < d < 95:
                x, y = LAMP[0] + d * math.cos(a), LAMP[1] + d * math.sin(a)
                if x > WALL_X + 4:
                    body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{AMBER}" opacity="{1 - d / 95:.2f}"/>'
        body += callout(LAMP[0] - 8, LAMP[1] - 6, "fewer, not softer", t, B[2] + 2.8, AMBER, dx=-126, dy=-74,
                        out=B[3] + 0.3, size=12)

    # electrons: flashes (sharp, then blurry), "missed" tags, dots
    bg = blank()
    seen_y, missed_y, after_y = [], [], []
    missed_tags = 0
    amber, violet = hexrgb(AMBER), hexrgb(VIOLET)
    old_fade = 1.0 - 0.7 * prog(t, B[6] + 0.3, 0.8)
    for i, (t0, hole, y, seen) in enumerate(_electrons(T, st, en)):
        if t < t0 - 1.0:
            break
        hy = HOLE1 if hole == 1 else HOLE2
        slow = t0 < B[4]
        if slow:
            body += electron_flight(t, t0, hole, seen)
        tp = t - (t0 - 0.45)                                  # time since it passed the wall
        if seen and -0.1 < tp < 0.25:
            if bk < 0.05:
                body += flash(WALL_X + 12, hy, AMBER, 13 if slow else 10)
        if not seen and t0 < B[5] and slow and 0 < tp < 1.0 and missed_tags < 2:
            missed_tags += 1
            body += g(pill(WALL_X + 54, hy + (-26 if hole == 1 else 24), "missed", VIOLET, 12),
                      o=between(t, t0 - 0.45, t0 + 0.4, 0.15))
        if t < t0:
            continue
        x, yi = STOP_X - 6 - (i * 37 % 40), int(y)
        if t0 >= B[6]:
            after_y.append(y)
            bg[yi - 1:yi + 1, x - 1:x + 1] += violet * 0.35
        elif seen:
            seen_y.append(y)
            bg[yi - 1:yi + 2, x - 1:x + 2] = amber * old_fade
        else:
            missed_y.append(y)
            bg[yi - 1:yi + 2, x - 1:x + 2] = violet * old_fade
    np.clip(bg, 0, 255, out=bg)

    # 5. longer wavelength: the photon stretches and reddens; flashes blur over both holes
    if B[5] <= t < B[7] + 0.5:
        k = prog(t, B[5] + 0.3, 3.0, ease_in_out)
        lam, col = lerp(9, 70, k), mix_color(AMBER, RED, k)
        wave = squiggle(LAMP[0], LAMP[1], WALL_X + 6, MID, lam, lerp(5, 11, k), col, phase=6 * t, width=3)
        body += g(wave, o=between(t, B[5], B[6] + 1.0))
        lab = pill(LAMP[0] - 6, 146, "longer λ", col, 13) + text(LAMP[0] - 6, 124, "softer kick", 12, DIM, "middle")
        body += pop(lab, t, B[5] + 0.8, (LAMP[0] - 6, 140), out=B[6] + 0.8)
        if bk > 0.02:
            r = lerp(12, 62, bk)
            glow = "".join(f'<circle cx="{WALL_X + 8}" cy="{MID:.1f}" r="{r * f:.1f}" fill="{RED}" '
                           f'opacity="{0.10 * bk:.2f}"/>' for f in (1.0, 0.8, 0.6, 0.4))
            body += g(glow, o=0.6 + 0.4 * osc(t, 0.5))
            lab = pill(92, 262, "which hole?", RED, 13) + text(92, 286, "can't tell", 12, DIM, "middle")
            body += pop(lab, t, B[5] + 5.5, (92, 262), out=B[7])

    # 4. seen vs missed, side by side
    half = CURVE_W // 2 - 4
    x2 = CURVE_X0 + half + 8
    split = between(t, B[4], B[6] + 0.3, 0.4)
    if split:
        h1, _ = histogram(seen_y, AMBER, x0=CURVE_X0, w=half, opacity=0.75)
        h2, _ = histogram(missed_y, VIOLET, x0=x2, w=half, opacity=0.75)
        c1 = [tuple(map(float, s.split(","))) for s in curve_pts(p_sum, mv.peak_of(p_sum), CURVE_X0, half).split()]
        c2 = [tuple(map(float, s.split(","))) for s in curve_pts(p_both, mv.peak_of(p_both), x2, half).split()]
        part = h1 + h2
        part += text(CURVE_X0 + half / 2, Y_TOP - 6, "seen", 13, AMBER, "middle", "800")
        part += text(x2 + half / 2, Y_TOP - 6, "missed", 13, VIOLET, "middle", "800")
        part += draw_path(c1, prog(t, B[4] + 1.6, 1.4), INK, 2, 0.9, "4 3")
        part += draw_path(c2, prog(t, B[4] + 2.6, 1.4), INK, 2, 0.9, "4 3")
        body += g(part, o=split)
        body += pop(text(CURVE_X0 + half / 2, Y_BOT + 18, "P₁ + P₂", 13, AMBER, "middle", "700"), t, B[4] + 2.0,
                    (CURVE_X0 + half / 2, Y_BOT + 12), out=B[6])
        body += pop(text(x2 + half / 2, Y_BOT + 18, "fringes", 13, VIOLET, "middle", "700"), t, B[4] + 3.0,
                    (x2 + half / 2, Y_BOT + 12), out=B[6])

    # 6. interference comes back: the curve morphs from humps into fringes
    if t > B[6] + 0.1:
        hf, _ = histogram(after_y, VIOLET, opacity=0.7)
        m = prog(t, B[6] + 0.6, 2.4, ease_in_out)
        pa, pb = mv.peak_of(p_sum), mv.peak_of(p_both)
        pts = [(CURVE_X0 + CURVE_W * lerp(p_sum(y) / pa, p_both(y) / pb, m), y) for y in range(Y_TOP, Y_BOT + 1, 2)]
        col = mix_color(AMBER, VIOLET, m)
        body += g(hf + draw_path(pts, 1.0, col, 3), o=prog(t, B[6] + 0.1, 0.4))
        body += pop(pill(CURVE_X0 + CURVE_W / 2, Y_TOP - 4, "wiggles back", VIOLET, 13), t, B[6] + 2.4,
                    (CURVE_X0 + CURVE_W / 2, Y_TOP - 10), out=B[7])

    body = g(body, o=1 - 0.78 * seesaw_k)

    # 7. nature is careful: a seesaw you can never level
    if t > B[7]:
        ang = 9 * math.sin(2 * math.pi * (t - B[7]) / 3.2)
        cx, cy = 240, 236
        beam = f'<rect x="{cx - 150}" y="{cy - 4}" width="300" height="8" rx="4" fill="{INK}"/>'
        left = flash(cx - 128, cy - 22, AMBER, 13) + text(cx - 128, cy - 42, "which-way", 15, AMBER, "middle", "800")
        right_pts = [(cx + 98 + i * 3, cy - 26 + 9 * math.sin(i * 0.9)) for i in range(19)]
        right = draw_path(right_pts, 1.0, VIOLET, 3) + text(cx + 126, cy - 42, "wiggles", 15, VIOLET, "middle", "800")
        tip = (f'<polygon points="{cx},{cy + 4} {cx - 20},{cy + 40} {cx + 20},{cy + 40}" fill="#333" '
               f'stroke="{INK}" stroke-width="2"/>')
        card = '<rect x="50" y="116" width="380" height="240" rx="18" fill="#000" opacity="0.85"/>'
        card += text(240, 150, "nature is careful", 22, INK, "middle", "800")
        card += g(beam + left + right, rot=ang, origin=(cx, cy)) + tip
        card += text(240, 320, "never both", 24, INK, "middle", "800")
        body += pop(card, t, B[7] + 0.1, (240, 238))

    return overlay(body, "DIMMER LIGHT", DIM), bg
