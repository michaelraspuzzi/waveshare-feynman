"""Amplitudes: the rule, choreographed to the narration.

Lines (B[i]):
 0 "The rule that works is this. For each way the electron can go, there's a number..." -> THE RULE, two glowing paths
 1 "Phi one for going through hole one. Phi two for hole two."  -> labels pop on the paths
 2 "...little arrows if you like, with a length and a direction." -> labels fly over and become arrows
 3 "When there are two ways... you add the arrows."              -> head-to-tail, the sum draws
 4 "...the probability is the length of the total arrow, squared." -> a literal square on the sum
 5 "Same way: big. Opposite: they cancel..."                      -> phi2 swings round, the square collapses
 6 "That's all there is to it. That's the rule..."                -> detector sweeps, traces P(y), boxed rule
"""
import math

import make_visuals as mv
from make_visuals import CYAN, DIM, INK, VIOLET, text
from motion import (arrow_draw, between, callout, draw_line, draw_path, ease_in_out, g, kinetic, lerp, pill,
                    pop, prog, pulse)
from scenes import amp_phase, overlay, p_both

GREEN = "#7be38f"

# mini apparatus on the left
GX, GY = 40, 200                 # gun
WX = 120                         # wall
H1, H2 = 168, 232                # holes (same heights as the big scenes)
DX = 210                         # detector / backstop
# phasor stage on the right
OX, OY, L = 362, 214, 42


def det_y(t, B):
    if t < B[6] + 0.4:
        return 186.0
    return 200 - 110 * math.cos(2 * math.pi * (t - B[6] - 0.4) / 4.2)


def paths(y):
    return [(GX + 16, GY), (WX, H1), (DX, y)], [(GX + 16, GY), (WX, H2), (DX, y)]


def apparatus(t, B):
    out = f'<rect x="{GX - 14}" y="{GY - 10}" width="28" height="20" rx="4" fill="none" stroke="{VIOLET}" stroke-width="2"/>'
    for a, b in ((74, H1 - 8), (H1 + 8, H2 - 8), (H2 + 8, 326)):
        out += f'<line x1="{WX}" y1="{a}" x2="{WX}" y2="{b}" stroke="{INK}" stroke-width="4"/>'
    out += f'<line x1="{DX}" y1="74" x2="{DX}" y2="326" stroke="{DIM}" stroke-width="3"/>'
    y = det_y(t, B)
    out += f'<rect x="{DX - 7}" y="{y - 7:.1f}" width="14" height="14" rx="3" fill="{INK}"/>'
    return out


def along(path, f):
    seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])]
    d = sum(seg) * (f % 1.0)
    for (a, b), s in zip(zip(path, path[1:]), seg):
        if d <= s:
            return lerp(a[0], b[0], d / s), lerp(a[1], b[1], d / s)
        d -= s
    return path[-1]


def phase_diff(t, B):
    """Angle between the two arrows over the scene."""
    if t < B[3]:
        return 0.9
    if t < B[5]:
        return lerp(0.9, 0.55, prog(t, B[3], 1.0))
    if t < B[6]:
        aligned = lerp(0.55, 0.0, prog(t, B[5], 0.8, ease_in_out))
        return lerp(aligned, math.pi, prog(t, B.sub(5, 1, 2) - 0.3, 1.6, ease_in_out))
    return amp_phase(det_y(t, B))


def scene(T, t, B):
    body = kinetic("THE RULE", t, B[0] + 0.2, hold=2.2, color=VIOLET, size=54)
    p1, p2 = paths(det_y(t, B))
    show_app = t > B[0] + 2.4
    if show_app:
        body += g(apparatus(t, B), o=prog(t, B[0] + 2.4, 0.5))
        # each way the electron can go glows, with a dot travelling along it
        pa = prog(t, B.sub(0, 2, 4), 1.0)
        body += draw_path(p1, pa, VIOLET, 3, 0.85) + draw_path(p2, prog(t, B.sub(0, 2, 4) + 0.4, 1.0), CYAN, 3, 0.85)
        if t > B.sub(0, 2, 4) + 1.0 and t < B[6]:
            for path, col, off in ((p1, VIOLET, 0.0), (p2, CYAN, 0.5)):
                x, y = along(path, (t - B[0]) / 1.8 + off)
                body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{col}"/>'
        body += callout(DX, det_y(t, B), "a number for each way", t, B.sub(0, 3, 4), INK, dx=-10, dy=150,
                        out=B[1] + 0.2, size=12)

    # 1. labels on the paths, 2. they fly to the phasor stage
    fly = prog(t, B[2] + 0.2, 0.9, ease_in_out)
    a1 = 0.25 + (0.6 * (t - B[2]) if t > B[2] else 0.0) * (1 - prog(t, B[3], 0.6))
    d = phase_diff(t, B)
    tip1 = (OX + L * math.cos(a1), OY - L * math.sin(a1))
    tail2_free = (OX, OY)
    head_to_tail = prog(t, B[3] + 0.3, 0.9, ease_in_out)
    tail2 = (lerp(tail2_free[0], tip1[0], head_to_tail), lerp(tail2_free[1], tip1[1], head_to_tail))
    tip2 = (tail2[0] + L * math.cos(a1 + d), tail2[1] - L * math.sin(a1 + d))
    for i, (src, col, lab, tail, tip) in enumerate(((p1[1], VIOLET, "φ₁", (OX, OY), tip1),
                                                     (p2[1], CYAN, "φ₂", tail2, tip2))):
        lx0, ly0 = src[0] + 26, src[1] + (-14 if i == 0 else 22)
        # land beside the arrow's middle, on the side away from the other arrow
        mx, my = (tail[0] + tip[0]) / 2, (tail[1] + tip[1]) / 2
        ux, uy = tip[0] - tail[0], tip[1] - tail[1]
        n = math.hypot(ux, uy) or 1
        side = 1 if i == 0 else -1
        bx, by = mx + side * 18 * uy / n, my - side * 18 * ux / n + 7     # beside the middle (once added)
        ex, ey = tip[0] + 17 * ux / n, tip[1] + 17 * uy / n + 7            # past the tip (side by side)
        lx1, ly1 = lerp(ex, bx, head_to_tail), lerp(ey, by, head_to_tail)
        x, y = lerp(lx0, lx1, fly), lerp(ly0, ly1, fly)
        body += pop(text(x, y, lab, 22, col, "middle", "800"), t, B.sub(1, i, 2) + 0.3, (x, y - 8))
    if t > B[2] + 0.6:
        grow = prog(t, B[2] + 0.6, 0.6)
        body += f'<circle cx="{OX}" cy="{OY}" r="{2 * L}" fill="none" stroke="#222" stroke-width="1"/>'
        body += arrow_draw(OX, OY, tip1[0], tip1[1], grow, VIOLET, 3.5)
        body += arrow_draw(tail2[0], tail2[1], tip2[0], tip2[1], grow, CYAN, 3.5)
        mid = ((OX + tip1[0]) / 2, (OY + tip1[1]) / 2)
        body += callout(mid[0], mid[1], "length", t, B.sub(2, 1, 3), INK, dx=-62, dy=40, out=B[3], size=12)
        body += callout(tip2[0], tip2[1], "direction", t, B.sub(2, 2, 3), INK, dx=40, dy=-40, out=B[3], size=12)

    # 3. the sum, 4. its square
    if t > B[3] + 1.0:
        sp = prog(t, B[3] + 1.1, 0.7)
        body += arrow_draw(OX, OY, tip2[0], tip2[1], sp, GREEN, 3)
        body += pop(text(OX - 14, OY + 26, "sum", 15, GREEN, "middle", "700"), t, B[3] + 1.6, (OX - 14, OY + 20),
                    out=B[4] + 0.2)
    if t > B[4] + 0.4 and t < B[6] + 0.6:
        vx, vy = tip2[0] - OX, tip2[1] - OY
        nx, ny = vy, -vx                                     # perpendicular, same length
        if ny > 0:                                           # keep the square on the upper side
            nx, ny = -nx, -ny
        k = prog(t, B[4] + 0.4, 0.9)
        quad = [(OX, OY), (tip2[0], tip2[1]), (tip2[0] + nx * k, tip2[1] + ny * k), (OX + nx * k, OY + ny * k)]
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in quad)
        o = 1 - prog(t, B[6], 0.5)
        body += g(f'<polygon points="{pts}" fill="{GREEN}" fill-opacity="0.28" stroke="{GREEN}" stroke-width="2"/>', o=o)
        cx = sum(q[0] for q in quad) / 4
        cy = sum(q[1] for q in quad) / 4
        if math.hypot(vx, vy) > 18:
            body += g(pop(text(cx, cy + 6, "P", 20, GREEN, "middle", "800"), t, B[4] + 1.0, (cx, cy)), o=o)
        body += g(pop(pill(240, 360, "probability = length²", GREEN, 15), t, B.sub(4, 1, 2), (240, 352)),
                  o=1 - prog(t, B[5], 0.4))

    # 5. same way vs opposite
    if B[5] < t < B[6] + 0.3:
        o = between(t, B[5] + 0.6, B.sub(5, 1, 2) - 0.2)
        body += g(pill(240, 360, "same way: BIG", GREEN, 16), o=o)
        o2 = between(t, B.sub(5, 1, 2) + 1.2, B.end(5))
        body += g(pill(240, 360, "opposite: they cancel", "#ff6b6b", 16), o=o2)
        if o2 > 0.5:
            body += pulse(OX, OY, t, B.sub(5, 1, 2) + 1.2, "#ff6b6b", r=14, rings=2)

    # 6. sweep the detector, trace P(y), box the rule
    if t > B[6]:
        pk = mv.peak_of(p_both)
        start = B[6] + 0.4
        pts = []
        s = start
        while s <= t and s < start + 4.2:
            y = det_y(s, B)
            pts.append((DX + 8 + 58 * p_both(y) / pk, y))
            s += 1 / 15
        if len(pts) > 1:
            body += draw_path(pts, 1, GREEN, 2.5)
        rule = (f'<rect x="100" y="336" width="280" height="46" rx="12" fill="#111" stroke="{INK}" stroke-width="2"/>'
                + text(240, 367, "P = |φ₁ + φ₂|²", 26, INK, "middle", "800"))
        body += pop(rule, t, B.sub(6, 1, 3), (240, 360))
    return overlay(body, "AMPLITUDES", VIOLET), None
