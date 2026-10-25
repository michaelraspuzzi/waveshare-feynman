"""Which hole? Watching the electrons, choreographed to the narration.

Lines (B[i]):
 0 "Now, you say, wait a minute. Each electron must go through one hole or the other." -> "1 or 2?" at the holes
 1 "Let's just look and see which one it goes through."             -> an eye opens
 2 "So we put a light behind the wall... we see a flash..."         -> lamp slides in, flashes at holes
 3 "...a flash at one hole or the other. Never both. Never half."    -> live tallies, both: 0
 4 "So we sort the clicks. ...hole one give P one. Hole two... P two." -> two histograms -> P1, P2
 5 "And the total, when we're watching? It's P one plus P two..."    -> sum curve, ghost fringes fade, INTERFERENCE GONE
 6 "Turn off the light, and the wiggles come back."                  -> lamp off, violet fringes regrow
 7 "So the electron behaves differently when we look at it."         -> eye + "looking changes it"
"""
import math
import random
from functools import lru_cache

import numpy as np

import make_visuals as mv
from make_visuals import (AMBER, DIM, HOLE1, HOLE2, INK, STOP_X, SRC_X, VIOLET, WALL_X, Y_BOT, Y_MID, Y_TOP,
                          CURVE_X0, CURVE_W, backstop, filament, flash, text, wall)
from motion import (Beats, between, callout, cross, draw_path, ease_in_out, g, kinetic, osc, pill, pop, prog,
                    pulse, slide_in)
from scenes import blank, curve_pts, electron_flight, hexrgb, histogram, overlay, p_both, p_sum

CORAL = "#ff7a59"                       # hole-2 electrons, so the sort is visible
LAMP = (WALL_X + 52, Y_MID)
HOLE_COLOR = {1: AMBER, 2: CORAL}


def lamp_svg(t, on, x=LAMP[0], y=LAMP[1]):
    """Lamp with breathing rays; on is 0..1 brightness."""
    color = AMBER if on > 0.05 else DIM
    out = f'<circle cx="{x}" cy="{y}" r="9" fill="{color}" opacity="{0.35 + 0.65 * on:.2f}"/>'
    if on > 0.05:
        out += f'<circle cx="{x}" cy="{y}" r="{16 + 3 * osc(t, 1.2):.1f}" fill="{AMBER}" opacity="{0.12 * on:.2f}"/>'
    for i in range(8):
        a = i * math.pi / 4 + 0.25 * t
        r1, r2 = 13, 13 + (8 + 5 * osc(t + i * 0.2, 0.9)) * on
        if r2 - r1 > 1:
            out += (f'<line x1="{x + r1 * math.cos(a):.1f}" y1="{y + r1 * math.sin(a):.1f}" '
                    f'x2="{x + r2 * math.cos(a):.1f}" y2="{y + r2 * math.sin(a):.1f}" '
                    f'stroke="{AMBER}" stroke-width="2" stroke-linecap="round" opacity="{on:.2f}"/>')
    return out


def eye(x, y, s=1.0, color=INK, look=0.0, blink=1.0):
    """Almond eye; look shifts the iris sideways (-1..1), blink squashes it (1 = open)."""
    h = 15 * s * blink
    w = 24 * s
    out = (f'<path d="M {x - w:.1f} {y:.1f} Q {x:.1f} {y - 2 * h:.1f} {x + w:.1f} {y:.1f} '
           f'Q {x:.1f} {y + 2 * h:.1f} {x - w:.1f} {y:.1f} Z" fill="none" stroke="{color}" stroke-width="{2.5 * s:.1f}"/>')
    if blink > 0.3:
        out += f'<circle cx="{x + 7 * s * look:.1f}" cy="{y:.1f}" r="{7 * s * min(1, blink):.1f}" fill="{color}"/>'
        out += f'<circle cx="{x + 7 * s * look + 2 * s:.1f}" cy="{y - 2 * s:.1f}" r="{2 * s:.1f}" fill="#000"/>'
    return out


@lru_cache(maxsize=None)
def _electrons(T, starts, ends):
    """Each electron: (t0, hole, y, seen). Seen while the light is on, so it lands from P1 or P2."""
    B = Beats(starts, ends)
    rnd = random.Random(11)

    def draw(fn):
        pk = mv.peak_of(fn)
        while True:
            y = rnd.uniform(Y_TOP, Y_BOT)
            if rnd.uniform(0, pk) < fn(y):
                return y

    out = []
    # a few slow, dramatic ones while we wonder which hole
    for k in range(3):
        out.append((B[0] + 1.6 + 1.6 * k, rnd.choice((1, 2)), draw(p_both), False))
    t = B[2] + 2.0
    while t < min(T - 0.3, B[6]):
        rate = 2.0 if t < B[3] else 7.0 if t < B[4] else 16.0
        t += rnd.expovariate(rate)
        hole = 1 if rnd.random() < 0.5 else 2
        out.append((t, hole, draw(mv.p1 if hole == 1 else mv.p2), True))
    t = B[6] + 0.3
    while t < T - 0.3:
        t += rnd.expovariate(45.0)                         # flood: the fringes must come back fast
        out.append((t, rnd.choice((1, 2)), draw(p_both), False))
    out.sort()
    return out


def scene(T, t, B):
    els = _electrons(T, tuple(B.starts), tuple(B.ends))

    # apparatus fades back for the closing beat
    dim_k = prog(t, B[7], 0.6, ease_in_out)
    body = filament(VIOLET) + wall() + backstop()

    # 0. one hole or the other?
    if t < B[2] + 0.5:
        o = between(t, B[0] + 0.6, B[2])
        for hy, lab in ((HOLE1, "1?"), (HOLE2, "2?")):
            s = 1 + 0.12 * math.sin(2 * math.pi * t / 0.9 + (hy == HOLE2) * 1.5)
            q = text(WALL_X + 24, hy + 7, lab, 22, AMBER, "middle", "800")
            body += g(q, s=s, o=o, origin=(WALL_X + 24, hy))
        body += callout(WALL_X, HOLE1 - 30, "one or the other?", t, B[0] + 2.4, AMBER, dx=60, dy=-40, out=B[1])

    # 1. look and see: an eye opens above the electron gun
    if B[1] <= t < B[7]:
        blink = min(1.0, prog(t, B[1], 0.5)) * (0.15 if 0 < (t - B[1] - 2.2) % 5 < 0.15 else 1.0)
        look = math.sin(2 * math.pi * (t - B[1]) / 3)
        body += pop(eye(78, 118, 1.0, INK, look, blink), t, B[1], (78, 118))
        body += pop(text(78, 152, "look", 13, DIM, "middle"), t, B[1] + 0.4, (78, 150))

    # 2. the lamp slides in behind the wall; dims off at line 6
    lamp_on = 1.0 - prog(t, B[6] + 0.2, 0.5)
    if t >= B[2]:
        body += slide_in(lamp_svg(t, lamp_on), t, B[2], dx=90)
        body += callout(LAMP[0] + 8, LAMP[1] + 10, "light", t, B[2] + 0.8, AMBER, dx=36, dy=48, out=B[3])
    if B[6] + 0.2 < t < B[6] + 1.6:
        body += pop(pill(LAMP[0], LAMP[1] + 44, "light off", DIM, 13), t, B[6] + 0.3, (LAMP[0], LAMP[1] + 40),
                    out=B[6] + 1.4)

    # electrons: flights, flashes, clicks, and the dots on the screen
    bg = blank()
    seen_y = {1: [], 2: []}
    watched_dots, fringe_dots, fringe_y = [], [], []
    tallies = {1: 0, 2: 0}
    for i, (t0, hole, y, seen) in enumerate(els):
        if t < t0 - 1.0:
            break
        hy = HOLE1 if hole == 1 else HOLE2
        slow = (not seen and t0 < B[2]) or (seen and t0 < B[3])
        if slow:
            body += electron_flight(t, t0, hole, seen)
        if seen and -0.1 < t - (t0 - 0.45) < 0.25:                    # the flash at its hole
            body += flash(WALL_X + 12, hy, HOLE_COLOR[hole], 14 if slow else 10)
        if t < t0:
            continue
        x = STOP_X - 6 - (i * 37 % 40)
        if seen:
            tallies[hole] += 1
            seen_y[hole].append(y)
            watched_dots.append((x, y, hole))
        elif t0 > B[6]:
            fringe_dots.append((x, y))
            fringe_y.append(y)
        if t - t0 < 0.3 and (slow or len(watched_dots) % 3 == 0):        # click ring
            body += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3 + 12 * (t - t0):.1f}" fill="none" stroke="{INK}" '
                     f'stroke-width="2" opacity="{1 - (t - t0) / 0.3:.2f}"/>')

    # dots: watched ones colored by hole, dimmed once the light is off; then the violet fringes
    fade_w = 1.0 - 0.7 * prog(t, B[6], 0.8)
    for hole in (1, 2):
        c = hexrgb(HOLE_COLOR[hole]) * fade_w
        for x, y, h in watched_dots:
            if h == hole:
                bg[int(y) - 1:int(y) + 2, int(x) - 1:int(x) + 2] = c
    cv = hexrgb(VIOLET)
    for x, y in fringe_dots:
        bg[int(y) - 1:int(y) + 1, int(x) - 1:int(x) + 1] += cv * 0.35
    np.clip(bg, 0, 255, out=bg)

    # 3. tallies
    if t > B[3]:
        body += pop(text(268, 46, f"hole 1: {tallies[1]}", 13, AMBER, "middle", "700"), t, B[3] + 0.3, (268, 42))
        body += pop(text(358, 46, f"hole 2: {tallies[2]}", 13, CORAL, "middle", "700"), t, B[3] + 0.7, (358, 42))
        both = text(440, 46, "both: 0", 13, INK, "end", "700")
        body += pop(both, t, B.sub(3, 2, 4), (420, 42))
        body += pulse(418, 42, t, B.sub(3, 2, 4) + 0.2, INK, r=14, rings=1)
        if B.sub(3, 3, 4) < t < B[4] + 0.4:
            half_flash = flash(84, 282, AMBER, 12) + text(84, 316, "never half", 13, DIM, "middle")
            body += pop(half_flash, t, B.sub(3, 3, 4), (84, 290))
            body += cross(84, 282, t, B.sub(3, 3, 4) + 0.3, "#ff6b6b", 34)

    # 4. sorted: two half-width histograms that grow into P1 and P2
    half = CURVE_W // 2 - 4
    x2 = CURVE_X0 + half + 8
    split = between(t, B[4], B[5] + 0.4, 0.4)
    if split:
        h1, _ = histogram(seen_y[1], AMBER, x0=CURVE_X0, w=half, opacity=0.75)
        h2, _ = histogram(seen_y[2], CORAL, x0=x2, w=half, opacity=0.75)
        c1 = [tuple(map(float, s.split(","))) for s in curve_pts(mv.p1, mv.peak_of(mv.p1), CURVE_X0, half).split()]
        c2 = [tuple(map(float, s.split(","))) for s in curve_pts(mv.p2, mv.peak_of(mv.p2), x2, half).split()]
        lab = (text(CURVE_X0 + half / 2, Y_TOP - 6, "P₁", 16, AMBER, "middle", "800")
               + text(x2 + half / 2, Y_TOP - 6, "P₂", 16, CORAL, "middle", "800"))
        cur = (draw_path(c1, prog(t, B[4] + 1.5, 1.4), INK, 2, 0.9, "4 3")
               + draw_path(c2, prog(t, B[4] + 2.2, 1.4), INK, 2, 0.9, "4 3"))
        body += g(h1 + h2 + lab + cur, o=split)
        body += callout(WALL_X + 12, HOLE1, "hole 1: P₁", t, B[4] + 0.6, AMBER, dx=40, dy=-78, out=B[5])

    # 5. the total when watching: P1 + P2, the fringes we'd expect fade away
    whole = between(t, B[5] + 0.2, B[6] + 0.3, 0.4)
    if whole:
        hsum, _ = histogram(seen_y[1] + seen_y[2], AMBER, opacity=0.6)
        psum = [tuple(map(float, s.split(","))) for s in curve_pts(p_sum, mv.peak_of(p_sum)).split()]
        ghost = curve_pts(p_both, mv.peak_of(p_both))
        ghost_o = 0.8 * (1 - prog(t, B[5] + 1.6, 2.2))
        part = hsum + draw_path(psum, prog(t, B[5] + 0.5, 1.4), INK, 3)
        if ghost_o > 0.02:
            part += (f'<polyline points="{ghost}" fill="none" stroke="{VIOLET}" stroke-width="2" '
                     f'stroke-dasharray="3 4" opacity="{ghost_o:.2f}"/>')
        body += g(part, o=whole)
    body += kinetic("INTERFERENCE", t, B[5] + 2.4, hold=2.6, color=AMBER, y=196, size=44,
                    sub="gone: just P₁ + P₂", sub_color=INK)

    # 6. light off: the violet fringes regrow
    if t > B[6] + 0.3:
        hf, _ = histogram(fringe_y, VIOLET, opacity=0.75)
        pf = [tuple(map(float, s.split(","))) for s in curve_pts(p_both, mv.peak_of(p_both)).split()]
        body += hf + draw_path(pf, prog(t, B[6] + 1.6, 1.5), INK, 2.4)
        body += pop(pill(CURVE_X0 + CURVE_W / 2, Y_TOP - 4, "wiggles back", VIOLET, 13), t, B[6] + 1.2,
                    (CURVE_X0 + CURVE_W / 2, Y_TOP - 10), out=B[7])

    body = g(body, o=1 - 0.75 * dim_k)

    # 7. looking changes it
    if t > B[7]:
        card = '<rect x="90" y="150" width="300" height="150" rx="18" fill="#000" opacity="0.85"/>'
        card += eye(240, 196, 1.9, AMBER, osc(t, 2.4, -1, 1))
        card += text(240, 262, "looking changes it", 24, INK, "middle", "800")
        card += text(240, 286, "the electron knows it's watched", 13, DIM, "middle")
        body += pop(card, t, B[7] + 0.1, (240, 225))
        body += pulse(240, 196, t, B[7] + 0.5, AMBER, r=40, rings=2, period=0.9)

    return overlay(body, "WHICH HOLE?", AMBER), bg
