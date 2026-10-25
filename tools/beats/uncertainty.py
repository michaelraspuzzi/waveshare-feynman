"""Uncertainty: why looking costs you the wiggles.

Lines (B[i]):
 0 "This is the uncertainty principle at work."                          -> the formula punches in, then docks
 1 "...Any way you could possibly find out which hole ... destroys it"    -> a breathing wave packet and its
                                                                            momentum spread; a photon pins down
                                                                            the position, the momentum blows up,
                                                                            and the fringe strip smears out
 2 "If it were possible to beat this... Nobody has ever found a way."    -> try to squeeze both: denied, NOBODY HAS
"""
import math

from make_visuals import AMBER, DIM, GREEN, INK, VIOLET, text
from motion import (callout, clamp01, cross, draw_path, ease_in_out, ease_out, g, kinetic, lerp, pop, prog,
                    pulse)
from scenes import overlay

RED = "#ff6b6b"
X0, X1, XC = 40, 440, 240
PY, MY = 116, 288           # baselines: position packet, momentum spread


def sigma_at(t, B):
    """Position spread: breathes, gets pinned by the photon, relaxes, then gets squeezed in the attempt."""
    base = 46 + 22 * math.sin(2 * math.pi * t / 5.0)
    kick = B.sub(1, 1, 3) + 0.8
    if t >= kick:
        k = clamp01((t - kick) / 0.25) * (1 - clamp01((t - kick - 3.0) / 1.5))
        base = lerp(base, 14, k)
    squeeze = B[2] + 1.0
    if t >= squeeze:
        base = lerp(base, 16, ease_out((t - squeeze) / 0.8))
    return base


def packet(t, sigma, appear):
    pts = []
    for x in range(X0, X1 + 1, 2):
        u = (x - XC) / sigma
        pts.append((x, PY - 52 * math.exp(-u * u / 2) * math.cos(0.32 * (x - XC) - 5 * t)))
    body = draw_path(pts, appear, GREEN, 2.5)
    if appear >= 1:
        body += (f'<line x1="{XC - sigma:.1f}" y1="{PY + 64}" x2="{XC + sigma:.1f}" y2="{PY + 64}" stroke="{GREEN}" stroke-width="2"/>'
                 f'<line x1="{XC - sigma:.1f}" y1="{PY + 58}" x2="{XC - sigma:.1f}" y2="{PY + 70}" stroke="{GREEN}" stroke-width="2"/>'
                 f'<line x1="{XC + sigma:.1f}" y1="{PY + 58}" x2="{XC + sigma:.1f}" y2="{PY + 70}" stroke="{GREEN}" stroke-width="2"/>'
                 + text(XC, PY + 86, "Δx", 15, GREEN, "middle", "700"))
    return body


def momentum(sp, appear, color=AMBER, dash=None, opacity=1.0):
    pts = []
    for x in range(X0, X1 + 1, 3):
        u = (x - XC) / sp
        pts.append((x, MY - 58 * math.exp(-u * u / 2)))
    body = draw_path(pts, appear, color, 2.2, opacity, dash)
    if appear >= 1 and dash is None:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        body = (f'<polygon points="{X0},{MY} {poly} {X1},{MY}" fill="{color}" opacity="{0.3 * opacity:.2f}"/>' + body)
    return body


def fringe_strip(t, visibility, o):
    """A little screen at the bottom: the two-hole pattern, sharp or smeared."""
    if o <= 0:
        return ""
    out = []
    for i in range(30):
        x = 105 + i * 9
        env = math.exp(-((i - 14.5) / 9) ** 2)
        v = env * (1 - visibility + visibility * (0.5 + 0.5 * math.cos(i * 1.05)))
        out.append(f'<rect x="{x}" y="306" width="7" height="18" rx="2" fill="{VIOLET}" opacity="{0.08 + 0.9 * v:.2f}"/>')
    return g("".join(out) + text(96, 320, "pattern", 12, DIM, "end"), o=o)


def photon(t, t0, y):
    """A wiggly photon flying in from the left to hit the packet."""
    d = t - t0
    if not 0 <= d <= 0.8:
        return ""
    x = lerp(-20, XC - 10, ease_out(d / 0.8))
    pts = [(x - 40 + i, y + 6 * math.sin(i / 2.5)) for i in range(0, 41, 2)]
    return draw_path(pts, 1, AMBER, 2.5)


def scene(T, t, B):
    body = ""

    # 0. the formula punches in, then docks under the graphs
    if t > B[0] + 0.1:
        dock = ease_in_out((t - B[0] - 2.1) / 0.7)
        s = lerp(1.0, 0.62, dock) * (ease_out((t - B[0] - 0.1) / 0.35) * 0.15 + 0.85 if t < B[0] + 0.45 else 1)
        o = clamp01((t - B[0] - 0.1) / 0.2)
        eq = text(240, 224, "Δx · Δp ≥ ħ/2", 48, INK, "middle", "800")
        body += g(eq, y=lerp(0, 146, dock), s=s, o=o, origin=(240, 210))
        body += g(text(240, 262, "the uncertainty principle", 18, DIM, "middle"), o=o * (1 - dock))

    # 1. packet + momentum; then a photon looks, and pays for it
    appear = prog(t, B[1] + 0.2, 1.2)
    sigma = sigma_at(t, B)
    sp = min(230.0, 1500 / sigma)
    if appear > 0:
        body += packet(t, sigma, appear)
        body += momentum(sp, prog(t, B[1] + 0.8, 1.2))
        lab = text(X1, PY + 44, "where it is", 13, DIM, "end") + text(X0, MY - 66, "how it's moving", 13, DIM)
        body += g(lab, o=prog(t, B[1] + 0.6, 0.4))
        if t > B[1] + 2.0:
            body += pop(text(X1, MY - 6, "Δp", 15, AMBER, "end", "700"), t, B[1] + 2.0, (X1 - 10, MY - 10))
    kick = B.sub(1, 1, 3) + 0.8
    body += photon(t, kick - 0.8, PY - 6)
    body += pulse(XC, PY, t, kick, AMBER, r=22, rings=2, period=0.5)
    body += callout(XC + 18, PY - 22, "found it!", t, kick + 0.1, AMBER, dx=70, dy=-24, out=kick + 2.4, size=13)
    body += callout(XC + 120, MY - 30, "kicked", t, kick + 0.6, RED, dx=60, dy=-20, out=kick + 2.8, size=13)

    # the pattern at the bottom: sharp until we look, smeared after
    smear = prog(t, kick + 0.3, 1.0) * (1 - prog(t, B[2] - 0.6, 0.6))
    body += fringe_strip(t, 1 - smear, prog(t, B.sub(1, 1, 3) - 0.6, 0.5) * (1 - prog(t, B[2] + 0.4, 0.4)))
    if smear > 0.5:
        body += g(text(384, 320, "smeared", 13, RED, "start", "700"), o=smear)

    # 2. try to beat it: squeeze Δx AND Δp — denied
    if t > B[2] + 1.0:
        wish = prog(t, B[2] + 1.6, 0.9)
        body += momentum(22, wish, RED, dash="5 4", opacity=0.9)
        body += pop(text(XC + 60, MY - 88, "both small?", 15, RED, "start", "700"), t, B[2] + 1.8, (XC + 100, MY - 92))
        body += cross(XC, MY - 34, t, B[2] + 3.0, RED, 36)
        body += pulse(272, 362, t, B[2] + 3.2, GREEN, r=18, rings=2, period=0.8)
    body += kinetic("NOBODY HAS", t, B.sub(2, 2, 3) + 0.4, hold=2.2, color=INK, y=208, size=50,
                    sub="ever found a way", sub_color=DIM)
    return overlay(body, "UNCERTAINTY", GREEN), None
