"""Closing: the two rules, and the honest limit of what we know.

Lines (B[i]):
 0 "...Add the amplitudes for the ways you can't tell apart, then square."  -> rule card 1 slides in, phasors spin
 1 "If you can tell them apart ... add the probabilities instead."         -> rule card 2 slides in, humps draw
 2 "And can we say how it really works underneath? ... No."                -> cards tuck away, gears turn, NO. stamp
 3 "We can only predict the odds..."                                       -> odds bars fill like a dice tally
 4 "...it agrees with every experiment ever done."                         -> rapid-fire checklist
 5 "Next time, we'll start using these amplitudes for real."               -> NEXT: amplitudes teaser
"""
import math
import random

from make_visuals import AMBER, CYAN, DIM, GREEN, INK, VIOLET, text
from motion import (arrow_draw, between, check, clamp01, draw_path, ease_back, ease_in_out, g, kinetic, lerp,
                    pop, prog, pulse, shake, slide_in)
from scenes import overlay

RED = "#ff6b6b"


def phasors(cx, cy, L, t):
    s = 1.6 * t
    d = 1.1 * math.sin(0.9 * t)
    x1, y1 = cx + L * math.cos(s), cy - L * math.sin(s)
    x2, y2 = x1 + L * math.cos(s + d), y1 - L * math.sin(s + d)
    return (f'<circle cx="{cx}" cy="{cy}" r="{2 * L}" fill="none" stroke="#2a2a2a" stroke-width="1"/>'
            + arrow_draw(cx, cy, x1, y1, 1, VIOLET, 2.5) + arrow_draw(x1, y1, x2, y2, 1, CYAN, 2.5)
            + arrow_draw(cx, cy, x2, y2, 1, GREEN, 2))


def humps(x0, y0, p):
    pts = [(x0 + i, y0 - 30 * (math.exp(-((i - 26) / 11) ** 2) + math.exp(-((i - 64) / 11) ** 2)))
           for i in range(0, 91, 2)]
    return draw_path(pts, p, AMBER, 2.5)


def card(y, head, rule, color, extra=""):
    return (f'<rect x="36" y="{y}" width="408" height="100" rx="14" fill="#0b0b0b" stroke="{color}" stroke-width="2"/>'
            + text(56, y + 30, head, 15, DIM) + text(56, y + 74, rule, 30, color, weight="700") + extra)


def gear(cx, cy, r, teeth, rot, color):
    out = [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="5"/>',
           f'<circle cx="{cx}" cy="{cy}" r="{r * 0.3:.1f}" fill="{color}"/>']
    for k in range(teeth):
        a = rot + 2 * math.pi * k / teeth
        x, y = cx + (r + 6) * math.cos(a), cy + (r + 6) * math.sin(a)
        out.append(f'<rect x="{x - 5:.1f}" y="{y - 5:.1f}" width="10" height="10" fill="{color}" '
                   f'transform="rotate({math.degrees(a):.1f} {x:.1f} {y:.1f})"/>')
    return "".join(out)


ODDS_RNG = random.Random(4)
ODDS_WEIGHTS = [math.exp(-((i - 5.5) / 2.6) ** 2) * (0.6 + 0.4 * math.cos(i * 1.5)) + 0.05 for i in range(12)]
ODDS_DRAWS = ODDS_RNG.choices(range(12), weights=ODDS_WEIGHTS, k=400)

CHECKS = ["two holes", "electrons", "photons", "atoms", "lasers", "computer chips"]


def scene(T, t, B):
    body = ""

    # 0-1. the two rules
    tuck = prog(t, B[2] + 0.2, 0.7, ease_in_out)        # cards shrink to the top when the big question comes
    c1 = card(70, "can't tell which way:  add amplitudes", "P = |φ₁ + φ₂|²", VIOLET,
              phasors(390, 120, 18, t) if t > B[0] + 0.8 else "")
    c2 = card(186, "can tell which way:  add probabilities", "P = P₁ + P₂", AMBER,
              humps(332, 262, prog(t, B[1] + 1.0, 1.4)))
    cards = slide_in(c1, t, B[0] + 0.3, dx=-120) + slide_in(c2, t, B[1] + 0.2, dx=120)
    cards += pulse(170, 136, t, B.sub(0, 1, 2), VIOLET, r=40, rings=1, period=0.9)
    cards += pulse(170, 252, t, B.sub(1, 1, 2), AMBER, r=40, rings=1, period=0.9)
    body += g(cards, s=lerp(1, 0.0, tuck), o=1 - tuck, origin=(240, 60))

    # 2. how does it really work? gears turn... No.
    if B[2] <= t < B[3] + 0.4:
        o = between(t, B[2] + 0.5, B[3] - 0.1)
        dx, dy = shake(t, B.sub(2, 2, 3) + 0.4, 0.5, 7)
        gears = gear(196, 200, 42, 10, t * 1.2, DIM) + gear(276, 172, 28, 8, -t * 1.8 + 0.3, DIM)
        gears += text(240, 290, "the machinery underneath?", 17, INK, "middle", "700")
        gears += pop(text(318, 140, "?", 38, AMBER, "middle", "800"), t, B[2] + 1.2, (318, 128))
        stamp_t = B.sub(2, 2, 3) + 0.4
        if t > stamp_t:
            s = lerp(2.2, 1.0, ease_back((t - stamp_t) / 0.35))
            stamp = (f'<rect x="170" y="164" width="140" height="70" rx="10" fill="#000" fill-opacity="0.6" '
                     f'stroke="{RED}" stroke-width="5"/>' + text(240, 218, "NO.", 44, RED, "middle", "900"))
            gears += g(stamp, s=s, rot=-12, o=clamp01((t - stamp_t) / 0.15), origin=(240, 199))
        body += g(gears, x=dx, y=dy, o=o)

    # 3. we can only predict the odds
    if B[3] <= t < B[4] + 0.4:
        o = between(t, B[3] + 0.2, B[4] - 0.1)
        n = int(len(ODDS_DRAWS) * prog(t, B[3] + 0.6, B.end(3) - B[3] - 1.0, lambda x: clamp01(x) ** 1.4))
        counts = [0] * 12
        for k in ODDS_DRAWS[:n]:
            counts[k] += 1
        bars = text(240, 92, "the odds", 26, INK, "middle", "800")
        bars += text(240, 116, "not which one — how often", 14, DIM, "middle")
        peak = max(max(counts), 8)
        for i, c in enumerate(counts):
            h = 170 * c / peak
            bars += f'<rect x="{78 + i * 28}" y="{320 - h:.1f}" width="22" height="{h:.1f}" rx="3" fill="{VIOLET}" opacity="0.85"/>'
        if n and n < len(ODDS_DRAWS):
            k = ODDS_DRAWS[n - 1]
            bars += f'<circle cx="{89 + k * 28}" cy="{306 - 170 * counts[k] / peak:.1f}" r="5" fill="{INK}"/>'
        bars += f'<line x1="70" y1="321" x2="410" y2="321" stroke="{DIM}" stroke-width="2"/>'
        body += g(bars, o=o)

    # 4. agrees with every experiment ever done
    if B[4] <= t < B[5] + 0.4:
        o = between(t, B[4] + 0.1, B[5] - 0.1)
        lst = text(240, 92, "agrees with every experiment", 22, INK, "middle", "800")
        for k, name in enumerate(CHECKS):
            tk = B.sub(4, k, len(CHECKS)) + 0.3
            row = text(176, 142 + k * 36, name, 18, INK, "start", "600") + check(150, 136 + k * 36, t, tk + 0.1, GREEN, 22)
            lst += slide_in(row, t, tk, dx=40, dur=0.3)
        body += g(lst, o=o)

    # 5. next time
    if t > B[5]:
        nx = pop(text(240, 150, "NEXT", 20, DIM, "middle", "800") + text(240, 196, "amplitudes", 40, VIOLET, "middle", "800"),
                 t, B[5] + 0.2, (240, 180))
        nx += pop(phasors(240, 282, 34, t * 1.4), t, B[5] + 0.8, (240, 282))
        body += nx
    return overlay(body, "THE RULES", INK), None
