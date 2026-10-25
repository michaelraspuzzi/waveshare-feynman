"""Bullets: the classical baseline, choreographed to the narration.

Lines (B[i]):
 0 "Let's start with an experiment we understand. Bullets."   -> BULLETS punches in
 1 "We have a gun that sprays bullets in all directions..."   -> gun slides in, sprays wildly
 2 "...an armor plate with two holes in it."                   -> wall draws itself, holes open, pulse
 3 "...a backstop, with a little box ... slide that box"       -> backstop draws, box glides up/down
 4 "We count how many bullets land in the box..."              -> bullets land, histogram grows, tally
 5 "Now, bullets come in lumps... never half a bullet."        -> LUMPS, 1 · 2 · not 1/2
 6 "If we close hole two... Call it P one."                    -> plug slides into hole 2, P1 draws
 7 "Close hole one, we get P two."                             -> plug moves to hole 1, P2 draws
 8 "Open both... P one plus P two."                            -> plug leaves, curves add, equation
 9 "Every bullet went through one hole or the other... Good."  -> check mark
"""
import math
import random
from functools import lru_cache

import make_visuals as mv
from make_visuals import (AMBER, DIM, HOLE1, HOLE2, HOLE_R, INK, SRC_X, STOP_X, WALL_X, Y_BOT, Y_MID,
                          Y_TOP, CURVE_X0, CURVE_W, flash, gun, text)
from motion import (callout, check, cross, draw_line, draw_path, ease_in_out, g, kinetic, lerp, pop, prog,
                    pulse, slide_in, typewriter)
from scenes import curve_pts, histogram, overlay, p_sum

SPEED = 430.0                      # px/s
MUZZLE = (SRC_X + 30, Y_MID)


def plug_y(t, B):
    """Where the hole plug sits (None when it's out of the way)."""
    if t < B[6] or t > B[8] + 0.6:
        return None
    if t < B[7]:
        return HOLE2
    if t < B[8]:
        return lerp(HOLE2, HOLE1, ease_in_out((t - B[7]) / 0.6))
    return HOLE1


def open_holes(t, B):
    if B[6] <= t < B[7]:
        return [HOLE1]
    if B[7] <= t < B[8]:
        return [HOLE2]
    return [HOLE1, HOLE2]


@lru_cache(maxsize=None)
def _bullets(T, starts, ends):
    """Every bullet's flight, decided by what the apparatus looks like when it is fired."""
    from motion import Beats
    B = Beats(starts, ends)
    rnd = random.Random(5)
    out = []
    t = B[1] + 0.5
    while t < T - 0.4:
        rate = 5 if t < B[4] else 11                       # fire faster once we're counting
        t += rnd.expovariate(rate)
        wall_up = t > B[2] + 0.6
        stop_up = t > B[3] + 0.6
        if not wall_up:                                     # spraying everywhere
            a = rnd.uniform(-0.75, 0.75)
            out.append({"t0": t, "path": [MUZZLE, (MUZZLE[0] + 600 * math.cos(a), MUZZLE[1] + 600 * math.sin(a))],
                        "land": None, "spark": None})
            continue
        holes = open_holes(t, B)
        if rnd.random() < 0.6:                              # makes it through an open hole
            hy = rnd.choice(holes)
            fn = mv.p1 if hy == HOLE1 else mv.p2
            while True:
                y = rnd.uniform(Y_TOP, Y_BOT)
                if rnd.uniform(0, fn(hy - 14 if hy == HOLE1 else hy + 14)) < fn(y):
                    break
            through = (WALL_X, hy + rnd.uniform(-HOLE_R + 2, HOLE_R - 2))
            if stop_up:
                path, land = [MUZZLE, through, (STOP_X - 4, y)], (y, t, tuple(holes))
            else:
                path, land = [MUZZLE, through, (520, through[1] + (y - through[1]) * 2.6)], None
            out.append({"t0": t, "path": path, "land": land, "spark": None})
        else:                                               # rings off the armor plate
            y = rnd.uniform(Y_TOP + 4, Y_BOT - 4)
            if any(abs(y - h) < HOLE_R + 2 for h in holes):
                y += 3 * HOLE_R
            out.append({"t0": t, "path": [MUZZLE, (WALL_X - 3, y)], "land": None, "spark": (WALL_X - 3, y)})
    return out


def _pos(path, d):
    """Point at distance d along a polyline (None once past the end)."""
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        if d <= L:
            f = d / L
            return x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
        d -= L
    return None


def _length(path):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:]))


def wall_svg(t, B):
    """Armor plate drawn top to bottom, then the holes punch open."""
    p = prog(t, B[2], 0.9)
    if p <= 0:
        return ""
    out = draw_line(WALL_X, Y_TOP, WALL_X, Y_TOP + (Y_BOT - Y_TOP) * p, p > 0, INK, 5, cap="butt")
    if p >= 1:                                              # holes appear by covering the line with black
        o = prog(t, B[2] + 0.9, 0.3)
        gap = HOLE_R * o
        for hy in (HOLE1, HOLE2):
            out += f'<rect x="{WALL_X - 4}" y="{hy - gap:.1f}" width="8" height="{2 * gap:.1f}" fill="#000"/>'
        out += pop(text(WALL_X - 16, HOLE1 + 5, "1", 14, DIM, "middle"), t, B[2] + 1.1, (WALL_X - 16, HOLE1))
        out += pop(text(WALL_X - 16, HOLE2 + 5, "2", 14, DIM, "middle"), t, B[2] + 1.25, (WALL_X - 16, HOLE2))
        out += pulse(WALL_X, HOLE1, t, B[2] + 1.1, AMBER) + pulse(WALL_X, HOLE2, t, B[2] + 1.3, AMBER)
    return out


def scene(T, t, B):
    body = kinetic("BULLETS", t, B[0] + 0.3, hold=2.4, color=AMBER, sub="an experiment we understand", sub_color=DIM)

    # 1. the gun, spraying
    body += slide_in(gun(AMBER), t, B[1], dx=-90)
    body += callout(SRC_X + 4, Y_MID - 14, "not very accurate", t, B[1] + 2.4, AMBER, dx=40, dy=-62, out=B[2] + 0.5)

    # 2-3. the wall, the backstop and the sliding box
    body += wall_svg(t, B)
    body += draw_line(STOP_X, Y_TOP, STOP_X, Y_BOT, prog(t, B[3], 0.8), DIM, 3)
    box_y = Y_MID + 95 * math.sin(2 * math.pi * (t - B[3]) / 4.0) if t < B[5] else None
    if box_y is not None and t > B[3] + 0.9:
        box = f'<rect x="{STOP_X - 9}" y="{box_y - 10:.1f}" width="18" height="20" rx="3" fill="none" stroke="{INK}" stroke-width="2"/>'
        body += pop(box, t, B[3] + 0.9, (STOP_X, box_y))
        body += callout(STOP_X + 9, box_y, "box", t, B[3] + 1.6, INK, dx=34, dy=-20, out=B[4] + 0.3, size=13)

    # plug for "close hole two / one"
    py = plug_y(t, B)
    if py is not None:
        out_k = prog(t, B[8], 0.6, ease_in_out)
        plug = (f'<rect x="{WALL_X - 7}" y="{py - HOLE_R - 3:.1f}" width="14" height="{2 * HOLE_R + 6}" rx="2" '
                f'fill="#555" stroke="{INK}" stroke-width="1.5"/>')
        body += g(slide_in(plug, t, B[6], dx=-50), x=-60 * out_k, o=1 - out_k)

    # bullets in flight, sparks, and the pile on the backstop
    phase = 0 if t < B[6] else 1 if t < B[7] else 2 if t < B[8] else 3
    phase_start = [B[4], B[6], B[7], B[8]][phase]
    landed = []
    for b in _bullets(T, tuple(B.starts), tuple(B.ends)):
        dt = t - b["t0"]
        if dt < 0:
            break
        d = dt * SPEED
        L = _length(b["path"])
        if d < L:
            pt = _pos(b["path"], d)
            if pt and pt[0] < 470:
                body += f'<circle cx="{pt[0]:.1f}" cy="{pt[1]:.1f}" r="3.5" fill="{AMBER}"/>'
        elif b["spark"] and d < L + 60:
            body += flash(*b["spark"], AMBER, 8 * (1 - (d - L) / 60))
        elif b["land"] and b["t0"] >= phase_start:
            landed.append(b["land"][0])

    if t > B[4]:
        bars, _ = histogram(landed, AMBER, opacity=0.55)
        body += bars
        body += pop(text(446, 64, f"count {len(landed)}", 15, AMBER, "end", "700"), t, B[4] + 0.5, (420, 60))

    # 5. lumps
    body += kinetic("LUMPS", t, B[5] + 0.2, hold=B.end(5) - B[5] - 0.6, color=AMBER, y=200)
    if B[5] < t < B.end(5) + 0.3:
        y0 = 268
        body += pop(text(150, y0, "1 bullet", 18, INK, "middle", "700"), t, B.sub(5, 1, 4), (150, y0))
        body += pop(text(260, y0, "2 bullets", 18, INK, "middle", "700"), t, B.sub(5, 2, 4), (260, y0))
        body += pop(text(360, y0, "½", 24, INK, "middle", "700"), t, B.sub(5, 3, 4), (360, y0 - 8))
        body += cross(360, y0 - 8, t, B.sub(5, 3, 4) + 0.3, "#ff6b6b", 30)

    # 6-8. single-hole curves, then the sum
    pk = mv.peak_of(p_sum)
    pts1 = [tuple(map(float, s.split(","))) for s in curve_pts(mv.p1, pk).split()]
    pts2 = [tuple(map(float, s.split(","))) for s in curve_pts(mv.p2, pk).split()]
    pts12 = [tuple(map(float, s.split(","))) for s in curve_pts(p_sum, pk).split()]
    body += draw_path(pts1, prog(t, B[6] + 1.2, 1.6), AMBER, 2.2, 0.9, "5 4")
    if t > B[6] + 1.6:
        body += pop(text(452, HOLE1 - 40, "P₁", 18, AMBER, "end", "700"), t, B[6] + 2.2, (440, HOLE1 - 46))
    body += draw_path(pts2, prog(t, B[7] + 0.8, 1.4), AMBER, 2.2, 0.9, "5 4")
    if t > B[7] + 1.2:
        body += pop(text(452, HOLE2 + 58, "P₂", 18, AMBER, "end", "700"), t, B[7] + 1.6, (440, HOLE2 + 52))
    body += draw_path(pts12, prog(t, B[8] + 1.6, 1.8), INK, 3.2)
    eq_t = B.sub(8, 2, 3)
    if t > eq_t:
        eq = (f'<rect x="120" y="334" width="240" height="40" rx="20" fill="#111" stroke="{AMBER}" stroke-width="2"/>'
              + text(240, 361, "P₁₂ = P₁ + P₂", 22, AMBER, "middle", "800"))
        body += pop(eq, t, eq_t, (240, 354))
        body += pulse(240, 354, t, eq_t + 0.2, AMBER, r=60, rings=1, period=0.9)

    # 9. nothing strange
    body += check(392, 352, t, B[9] + 0.6, "#7be38f", 30)
    body += typewriter(240, 392 - 6, "one hole or the other. nothing strange.", t, B[9] + 0.3, 30, 14, DIM, "middle")
    return overlay(body, "BULLETS", AMBER), None
