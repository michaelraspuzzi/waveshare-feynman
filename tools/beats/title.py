"""Title: the promise of the lecture, choreographed to the narration.

Lines (B[i]):
 0 "Today we're going to talk about how very small things behave."      -> title types in over rippling fringes
 1 "...they don't behave like anything you've ever seen."               -> title docks up, a particle appears
                                                                           that keeps morphing dot <-> wave
 2 "Not like billiard balls. Not like waves... springs, or clouds..."   -> 4 icons pop in and get crossed out
 3 "So you're going to have to put up with that."                       -> icons drop away, particle pulses
 4 "I can't explain it ... there isn't anything familiar."              -> "particle? wave?" tags flicker,
                                                                           NOTHING FAMILIAR punches in
 5 "What I can do is tell you exactly what happens..."                  -> two-hole apparatus sketches itself
"""
import math

from make_visuals import AMBER, CYAN, DIM, GREEN, INK, VIOLET, text
from motion import (between, clamp01, cross, draw_line, draw_path, ease_in_out, g, kinetic, lerp, osc, pop,
                    prog, pulse, typewriter)
from scenes import overlay

RED = "#ff6b6b"
PX, PY = 240, 214                      # where the quantum "thing" lives


def fringes(t, o):
    if o <= 0:
        return ""
    bars = []
    for i in range(-11, 12):
        v = 0.5 + 0.5 * math.cos(i * 0.9 - 2.4 * t) * math.exp(-(i * i) / 70)
        h = 60 + 46 * v
        bars.append(f'<rect x="{240 + i * 14 - 4}" y="{150 - h / 2:.1f}" width="8" height="{h:.1f}" rx="4" '
                    f'fill="{VIOLET}" opacity="{(0.10 + 0.8 * v) * o:.2f}"/>')
    return "".join(bars)


def particle(t, scale=1.0):
    """Something that is a dot one moment and a wave packet the next."""
    m = ease_in_out(osc(t, 3.2))                    # 0 = dot, 1 = wave
    pts = []
    for i in range(-60, 61, 3):
        u = i / 26
        pts.append((PX + i * scale, PY - 34 * scale * m * math.exp(-u * u) * math.cos(0.45 * i - 6 * t)))
    body = draw_path(pts, 1.0, VIOLET, 3, 0.25 + 0.75 * m)
    body += f'<circle cx="{PX}" cy="{PY}" r="{10 * scale * (1 - m) + 1:.1f}" fill="{VIOLET}" opacity="{1 - 0.8 * m:.2f}"/>'
    body += f'<circle cx="{PX}" cy="{PY}" r="{22 * scale * (1 - m) + 2:.1f}" fill="{VIOLET}" opacity="{0.18 * (1 - m):.2f}"/>'
    return body


# --------------------------------------------------------------- the four "not like" icons

def ball(x, y):
    return (f'<circle cx="{x}" cy="{y}" r="20" fill="{AMBER}"/>'
            f'<circle cx="{x}" cy="{y}" r="9" fill="#fff"/>' + text(x, y + 4, "8", 11, "#000", "middle", "800"))


def pond(x, y):
    pts = [(x - 24 + i, y + 7 * math.sin(i / 4)) for i in range(0, 49, 2)]
    pts2 = [(x - 24 + i, y + 12 + 5 * math.sin(i / 4 + 1)) for i in range(0, 49, 2)]
    return draw_path(pts, 1, CYAN, 3) + draw_path(pts2, 1, CYAN, 2, 0.6)


def spring(x, y):
    pts = [(x - 26, y)] + [(x - 20 + i * 5, y + (9 if i % 2 else -9)) for i in range(9)] + [(x + 26, y)]
    return draw_path(pts, 1, GREEN, 3)


def cloud(x, y):
    c = "#cfd6e6"
    return (f'<circle cx="{x - 12}" cy="{y + 4}" r="11" fill="{c}"/><circle cx="{x + 2}" cy="{y - 5}" r="14" fill="{c}"/>'
            f'<circle cx="{x + 15}" cy="{y + 5}" r="10" fill="{c}"/><rect x="{x - 22}" y="{y + 3}" width="44" height="12" rx="6" fill="{c}"/>')


ICONS = [(ball, "billiard ball"), (pond, "pond wave"), (spring, "spring"), (cloud, "cloud")]


def apparatus(t, t0):
    """A quick sketch of the two-hole setup, drawing itself."""
    out = ""
    y0 = 236
    out += pop(f'<circle cx="92" cy="{y0}" r="8" fill="{VIOLET}"/>', t, t0, (92, y0))
    segs = [(200, y0 - 70, 200, y0 - 22), (200, y0 - 10, 200, y0 + 10), (200, y0 + 22, 200, y0 + 70)]
    for i, (x1, y1, x2, y2) in enumerate(segs):
        out += draw_line(x1, y1, x2, y2, prog(t, t0 + 0.3 + 0.2 * i, 0.4), INK, 5, cap="butt")
    out += draw_line(330, y0 - 75, 330, y0 + 75, prog(t, t0 + 1.0, 0.6), DIM, 3)
    # dotted guesses at the paths
    for hy in (y0 - 16, y0 + 16):
        out += draw_path([(100, y0), (200, hy), (330, hy + (hy - y0) * 1.8)], prog(t, t0 + 1.5, 0.9), VIOLET, 1.6, 0.8, "3 5")
    out += pop(text(380, y0 + 6, "?", 34, AMBER, "middle", "800"), t, t0 + 2.4, (380, y0 - 4))
    return out


def scene(T, t, B):
    body = ""

    # 0. the title types in over rippling fringes, then docks at the top when the particle arrives
    dock = prog(t, B[1] + 0.2, 0.8, ease_in_out)
    body += fringes(t, 1 - dock)
    title = (typewriter(240, 252, "Quantum", t, B[0] + 0.2, 14, 46, INK, "middle", "700")
             + typewriter(240, 300, "Behavior", t, B[0] + 0.9, 14, 46, INK, "middle", "700"))
    body += g(title, y=lerp(0, -168, dock), s=lerp(1, 0.6, dock), origin=(240, 276))

    # 1. the quantum thing: dot <-> wave, forever undecided
    if t > B[1] + 0.6:
        shrink = lerp(1, 0.75, prog(t, B[2], 0.6)) * lerp(1, 1.25, prog(t, B[3], 0.6)) * lerp(1, 0.8, prog(t, B[5], 0.6))
        body += pop(particle(t, shrink), t, B[1] + 0.6, (PX, PY))
        body += g(typewriter(240, 290, "like nothing you've ever seen", t, B[1] + 1.4, 30, 16, DIM, "middle"),
                  o=between(t, B[1] + 1.4, B[2] - 0.2))

    # 2. not like... (each icon on its quarter of the line, then crossed out)
    xs = [84, 182, 298, 396]
    drop = prog(t, B[3] + 0.3, 0.8, ease_in_out)
    for k, ((fn, label), x) in enumerate(zip(ICONS, xs)):
        t0 = B.sub(2, k, 4) + 0.15
        icon = fn(x, 318) + text(x, 360, label, 12, DIM, "middle")
        icon = pop(icon, t, t0, (x, 318)) + cross(x, 318, t, t0 + 0.75, RED, 40)
        body += g(icon, y=70 * drop, o=1 - drop)

    # 3. put up with it: the particle gets a highlight
    body += pulse(PX, PY, t, B[3] + 0.4, VIOLET, r=30, rings=3, period=0.8)

    # 4. particle? wave? nothing familiar
    if B[4] <= t < B[5] + 0.4:
        o = between(t, B[4] + 0.2, B[5] - 0.1)
        m = ease_in_out(osc(t, 3.2))
        tags = text(150, PY + 5, "particle?", 18, AMBER, "middle", "700")
        body += g(tags, o=o * (1 - m) + 0.15 * o)
        body += g(text(340, PY + 5, "wave?", 18, CYAN, "middle", "700"), o=o * m + 0.15 * o)
    body += kinetic("NOTHING FAMILIAR", t, B.sub(4, 1, 2), hold=2.0, color=INK, y=316, size=36)

    # 5. but I can tell you exactly what happens
    body += kinetic("WHAT HAPPENS", t, B[5] + 0.2, hold=1.4, color=AMBER, y=236, size=44)
    if t > B[5] + 1.8:
        fade_particle = prog(t, B[5] + 1.6, 0.4)
        body += f'<rect x="150" y="150" width="180" height="130" fill="#000" opacity="{fade_particle:.2f}"/>'
        body += apparatus(t, B[5] + 1.9)
    return overlay(body, "FEYNMAN TUTOR", VIOLET), None
