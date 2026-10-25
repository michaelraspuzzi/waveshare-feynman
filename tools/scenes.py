"""Animated scenes for the Quantum Behavior lecture.

Each scene is a function scene(T, t) -> (svg_overlay, background) where T is the length of the
lecture segment it plays over (seconds) and t is the time within it. The background is an
optional 480x480x3 uint8 array (fields, accumulated dots) drawn under the transparent SVG.
The renderer samples every scene at FPS frames per second.
"""
import math
import random
from functools import lru_cache

import numpy as np

import make_visuals as mv
from make_visuals import (AMBER, CYAN, DIM, GREEN, HOLE1, HOLE2, INK, STOP_X, SRC_X, VIOLET, WALL_X, Y_BOT,
                          Y_MID, Y_TOP, CURVE_X0, CURVE_W, arrow, backstop, caption, filament, flash, gun, lamp,
                          text, wall)

FPS = 15
LAMBDA = 26.0                     # wavelength in px (also sets the fringe spacing)
K = 2 * math.pi / LAMBDA
SPEED = 70.0                      # wave speed px/s
BIN = 6                           # histogram bin height px


def ramp(t, start, length=1.0):
    """0 before start, 1 after start+length, linear between."""
    return max(0.0, min(1.0, (t - start) / length))


def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)


def overlay(body, title, accent):
    return mv.svg(body, title, accent, bg=False)


# ---------------------------------------------------------------- physics shared by scenes

def amp_phase(y):
    """Path-length phase difference between the two holes for a point on the backstop."""
    r1 = math.hypot(STOP_X - WALL_X, y - HOLE1)
    r2 = math.hypot(STOP_X - WALL_X, y - HOLE2)
    return K * (r1 - r2)


def p_both(y):
    a, b = mv.p1(y), mv.p2(y)
    return a + b + 2 * math.sqrt(a * b) * math.cos(amp_phase(y))


def p_sum(y):
    return mv.p1(y) + mv.p2(y)


def sampler(fn, seed):
    rnd = random.Random(seed)
    ys = list(range(Y_TOP, Y_BOT + 1))
    peak = max(fn(y) for y in ys)

    def draw():
        while True:
            y = rnd.uniform(Y_TOP, Y_BOT)
            if rnd.uniform(0, peak) < fn(y):
                return y
    return draw, rnd


def curve_pts(fn, peak, x0=CURVE_X0, w=CURVE_W):
    return " ".join(f"{x0 + w * fn(y) / peak:.1f},{y}" for y in range(Y_TOP, Y_BOT + 1, 2))


def polyline(pts, color, width=2.5, opacity=1.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round" opacity="{opacity:.2f}"{d}/>')


def histogram(ys, color, x0=CURVE_X0, w=CURVE_W, opacity=0.85, norm=None):
    """Horizontal bars to the right of the backstop; returns (svg, peak count)."""
    nb = (Y_BOT - Y_TOP) // BIN + 1
    counts = np.zeros(nb)
    for y in ys:
        counts[int((y - Y_TOP) // BIN)] += 1
    peak = norm or max(counts.max(), 3)
    out = []
    for i, c in enumerate(counts):
        if c:
            out.append(f'<rect x="{x0}" y="{Y_TOP + i * BIN}" width="{w * c / peak:.1f}" '
                       f'height="{BIN - 1}" fill="{color}" opacity="{opacity}"/>')
    return "".join(out), counts


def paint_dots(bg, dots, color, early=12):
    """First few dots are big and solid; after that each adds light, so density shows as brightness."""
    c = hexrgb(color)
    for i, (x, y) in enumerate(dots):
        xi, yi = int(x), int(y)
        if i < early:
            bg[yi - 2:yi + 3, xi - 2:xi + 3] = c
        else:
            bg[yi - 1:yi + 1, xi - 1:xi + 1] += c * 0.3
    np.clip(bg, 0, 255, out=bg)
    return bg


def blank():
    return np.zeros((480, 480, 3), dtype=np.float32)


# ---------------------------------------------------------------- scenes

def title(T, t):
    bars = []
    for i in range(-11, 12):
        v = 0.5 + 0.5 * math.cos(i * 0.9 - 2.4 * t) * math.exp(-(i * i) / 70)
        h = 70 + 50 * v
        bars.append(f'<rect x="{240 + i * 14 - 4}" y="{156 - h / 2:.1f}" width="8" height="{h:.1f}" rx="4" '
                    f'fill="{VIOLET}" opacity="{0.10 + 0.85 * v:.2f}"/>')
    body = "".join(bars)
    body += text(240, 272, "Quantum", 46, INK, "middle", "700")
    body += text(240, 320, "Behavior", 46, INK, "middle", "700")
    return overlay(body, "FEYNMAN TUTOR", VIOLET), None


@lru_cache(maxsize=None)
def _bullets(T):
    rnd = random.Random(1)
    n = int(min(420, max(60, T * 9)))
    out = []
    for i in range(n):
        t0 = 0.4 + (T * 0.82) * (i / n) ** 1.7
        y_wall = rnd.uniform(Y_TOP + 6, Y_BOT - 6)
        hole = None
        if rnd.random() < 0.65:                       # aimed well enough to make it through
            hole = HOLE1 if rnd.random() < 0.5 else HOLE2
            y_wall = hole + rnd.uniform(-5, 5)
            fn = mv.p1 if hole == HOLE1 else mv.p2
            peak = fn(hole)
            while True:
                y_land = rnd.uniform(Y_TOP, Y_BOT)
                if rnd.uniform(0, peak) < fn(y_land):
                    break
        else:
            y_land = None
        out.append((t0, y_wall, hole, y_land))
    return out


def bullets(T, t):
    p = t / T
    body = gun(AMBER) + wall() + backstop()
    landed = []
    for t0, y_wall, hole, y_land in _bullets(T):
        dt = t - t0
        if dt < 0:
            continue
        if dt < 0.55:                                          # gun -> wall
            f = dt / 0.55
            x = SRC_X + 30 + (WALL_X - SRC_X - 30) * f
            y = Y_MID + (y_wall - Y_MID) * f
            body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{AMBER}"/>'
        elif hole is None:
            if dt < 0.75:                                      # ricochet spark
                body += flash(WALL_X - 4, y_wall, AMBER, 7 * (1 - (dt - 0.55) / 0.2))
        elif dt < 0.95:                                        # hole -> backstop
            f = (dt - 0.55) / 0.4
            x = WALL_X + (STOP_X - 4 - WALL_X) * f
            y = y_wall + (y_land - y_wall) * f
            body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{AMBER}"/>'
        else:
            landed.append(y_land)
    bars, _ = histogram(landed, AMBER, opacity=0.75)
    body += bars
    pk = mv.peak_of(p_sum)
    a = ramp(p, 0.45, 0.1)
    if a:
        body += polyline(curve_pts(mv.p1, pk), AMBER, 1.6, 0.7 * a, "4 4")
        body += polyline(curve_pts(mv.p2, pk), AMBER, 1.6, 0.7 * a, "4 4")
    b = ramp(p, 0.62, 0.1)
    if b:
        body += polyline(curve_pts(p_sum, pk), INK, 2.5, b)
        body += caption("P₁₂ = P₁ + P₂", AMBER)
    body += text(446, 46, f"{len(landed)} bullets", 13, DIM, "end")
    return overlay(body, "BULLETS", AMBER), None


_YY, _XX = np.mgrid[0:480:2, 0:480:2].astype(np.float32)


def wave_field(t):
    """Instantaneous water-wave height, half resolution, posterized; returns 480x480x3."""
    w = SPEED * K
    field = np.zeros_like(_XX)
    r0 = np.hypot(_XX - SRC_X, _YY - Y_MID)
    left = (_XX < WALL_X) & (r0 < SPEED * t)
    field[left] = (np.cos(K * r0 - w * t) / np.sqrt(r0 / 30 + 1))[left]
    t_hole = math.hypot(WALL_X - SRC_X, HOLE1 - Y_MID) / SPEED
    right = (_XX > WALL_X + 2) & (_XX < STOP_X - 2)
    for hy in (HOLE1, HOLE2):
        r = np.hypot(_XX - WALL_X, _YY - hy)
        on = right & (r < SPEED * (t - t_hole))
        field[on] += (0.8 * np.cos(K * r - w * (t - t_hole)) / np.sqrt(r / 30 + 1))[on]
    field[(_YY < Y_TOP) | (_YY > Y_BOT)] = 0
    v = np.clip(np.round(field * 2.5) / 2.5, -1, 1)          # posterize: compresses well, reads as water
    rgb = np.zeros(v.shape + (3,), np.float32)
    c = hexrgb(CYAN)
    rgb += np.clip(v, 0, 1)[..., None] * c * 0.75
    rgb += np.clip(-v, 0, 1)[..., None] * np.array([10, 30, 60], np.float32)
    return np.repeat(np.repeat(rgb, 2, axis=0), 2, axis=1)


def waves(T, t):
    p = t / T
    body = wall() + backstop() + f'<circle cx="{SRC_X}" cy="{Y_MID}" r="6" fill="{CYAN}"/>'
    pk = mv.peak_of(p_both)
    t_reach = (math.hypot(WALL_X - SRC_X, HOLE1 - Y_MID) + (STOP_X - WALL_X)) / SPEED
    a = ramp(t, t_reach, 1.5)
    if a:
        body += polyline(curve_pts(p_both, pk), CYAN, 3, a)
    b = ramp(p, 0.55, 0.1)
    if b:
        body += polyline(curve_pts(mv.p1, pk), DIM, 1.4, b, "4 4")
        body += polyline(curve_pts(mv.p2, pk), DIM, 1.4, b, "4 4")
        body += caption("I₁₂ ≠ I₁ + I₂", CYAN)
        body += text(240, 376, "add heights, then square", 14, DIM, "middle")
    return overlay(body, "WATER WAVES", CYAN), wave_field(t)


@lru_cache(maxsize=None)
def _arrivals(T, kind, seed):
    """Electron arrival times: the first few slow and dramatic, then a rising flood."""
    draw_both, rnd = sampler(p_both, seed)
    draw1, _ = sampler(mv.p1, seed + 1)
    draw2, _ = sampler(mv.p2, seed + 2)
    slow = 7 if T > 20 else 3
    times = [1.2 + 1.3 * i for i in range(slow)]
    start, end = times[-1] + 1.3, T * 0.92
    m = int(min(1600, max(200, (end - start) * 70)))
    times += [start + (end - start) * (j / m) ** 0.55 for j in range(m)]
    out = []
    for t0 in times:
        hole = 1 if rnd.random() < 0.5 else 2
        seen = kind == "watch" or (kind == "dim" and rnd.random() < 0.45)
        if seen:
            y = draw1() if hole == 1 else draw2()
        else:
            y = draw_both()
        x = STOP_X - 6 - rnd.uniform(0, 40)
        out.append((t0, x, y, hole, seen))
    return out, slow


def electron_flight(t, t0, hole, seen, body_color=VIOLET):
    """Probability wave for one electron: a ring from the gun, then rings from both holes."""
    dt = t - t0 + 1.0
    out = ""
    if 0 < dt < 0.55:
        r = (WALL_X - SRC_X) * dt / 0.55
        out += f'<circle cx="{SRC_X}" cy="{Y_MID}" r="{r:.1f}" fill="none" stroke="{body_color}" stroke-width="2" opacity="{0.8 - dt:.2f}"/>'
    elif 0.55 <= dt < 1.0:
        r = (STOP_X - WALL_X) * (dt - 0.55) / 0.45
        holes = [HOLE1 if hole == 1 else HOLE2] if seen else [HOLE1, HOLE2]
        for hy in holes:
            out += (f'<path d="M {WALL_X} {hy - r:.1f} A {r:.1f} {r:.1f} 0 0 1 {WALL_X} {hy + r:.1f}" fill="none" '
                    f'stroke="{body_color}" stroke-width="2" opacity="{0.9 - (dt - 0.55):.2f}"/>')
    return out


def electron_scene(T, t, kind):
    p = t / T
    events, slow = _arrivals(T, kind, {"plain": 7, "watch": 11, "dim": 13}[kind])
    body = filament(VIOLET) + wall() + backstop()
    if kind != "plain":
        on = 0.45 if kind == "dim" else 1.0
        body += lamp(WALL_X + 52, Y_MID, AMBER if kind == "watch" else DIM).replace(
            f'fill="{AMBER}"', f'fill="{AMBER}" opacity="{on}"')
    bg = blank()
    seen_dots, unseen_dots, seen_y, unseen_y = [], [], [], []
    for i, (t0, x, y, hole, seen) in enumerate(events):
        if t < t0 - 1.0:
            break
        if i < slow:
            body += electron_flight(t, t0, hole, seen)
        if seen and -0.1 < t - (t0 - 0.45) < 0.2:              # light flash as it passes the hole
            body += flash(WALL_X + 12, HOLE1 if hole == 1 else HOLE2, AMBER, 13 if i < slow else 9)
        if t >= t0:
            (seen_dots if seen else unseen_dots).append((x, y))
            (seen_y if seen else unseen_y).append(y)
            if t - t0 < 0.35:                                   # the click
                body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3 + 12 * (t - t0):.1f}" fill="none" stroke="{INK}" stroke-width="2" opacity="{1 - (t - t0) / 0.35:.2f}"/>'
                if i < slow:
                    body += text(STOP_X - 60, y + 5, "click!", 14, INK, "middle", "700")
    paint_dots(bg, unseen_dots, VIOLET)
    paint_dots(bg, seen_dots, AMBER)
    n = len(seen_y) + len(unseen_y)
    if kind == "dim":
        half = CURVE_W // 2 - 4
        h1, _ = histogram(seen_y, AMBER, x0=CURVE_X0, w=half, opacity=0.8)
        h2, _ = histogram(unseen_y, VIOLET, x0=CURVE_X0 + half + 8, w=half, opacity=0.8)
        body += h1 + h2
        body += text(CURVE_X0 + half / 2, Y_TOP - 6, "seen", 13, AMBER, "middle", "700")
        body += text(CURVE_X0 + half * 1.5 + 8, Y_TOP - 6, "missed", 13, VIOLET, "middle", "700")
        if ramp(p, 0.5, 0.1):
            body += caption("which-way  OR  wiggles", INK)
            body += text(240, 376, "never both", 14, DIM, "middle")
    else:
        color = AMBER if kind == "watch" else VIOLET
        bars, _ = histogram(seen_y + unseen_y, color, opacity=0.8)
        body += bars
        fn = p_sum if kind == "watch" else p_both
        a = ramp(p, 0.7, 0.12)
        if a:
            body += polyline(curve_pts(fn, mv.peak_of(fn)), INK, 2.2, a)
            if kind == "watch":
                body += polyline(curve_pts(p_both, mv.peak_of(p_both)), VIOLET, 1.4, 0.5 * a, "3 5")
                body += caption("watching:  P₁ + P₂", AMBER)
                body += text(240, 376, "the wiggles disappear", 14, DIM, "middle")
            else:
                body += caption("arrive like lumps · add like waves", VIOLET, size=17)
    body += text(446, 46, f"{n} electrons", 13, DIM, "end")
    title_ = {"plain": ("ELECTRONS", VIOLET), "watch": ("WHICH HOLE?", AMBER), "dim": ("DIMMER LIGHT", DIM)}[kind]
    return overlay(body, *title_), bg


def electrons(T, t):
    return electron_scene(T, t, "plain")


def watching(T, t):
    return electron_scene(T, t, "watch")


def dim_light(T, t):
    return electron_scene(T, t, "dim")


def amplitudes(T, t):
    """A detector sweeps the backstop; phasors for the two holes add; the trace draws P(y)."""
    period = max(8.0, T / 2.2)
    span = (Y_BOT - Y_TOP) / 2 - 8

    def det_y(tt):
        return Y_MID - span * math.cos(2 * math.pi * tt / period)

    y = det_y(t)
    body = ""
    # left: backstop with detector, and the traced probability
    bx = 170
    body += f'<line x1="{bx}" y1="{Y_TOP}" x2="{bx}" y2="{Y_BOT}" stroke="{DIM}" stroke-width="3"/>'
    pk = mv.peak_of(p_both)
    trace = [f"{bx - 8 - 120 * p_both(det_y(s)) / pk:.1f},{det_y(s):.1f}"
             for s in np.arange(0, min(t, period), 1 / FPS)]
    if len(trace) > 1:
        body += polyline(" ".join(trace), GREEN, 2.5)
    body += f'<rect x="{bx - 6}" y="{y - 7:.1f}" width="14" height="14" rx="3" fill="{INK}"/>'
    body += text(bx - 70, Y_TOP - 6, "P at detector", 12, DIM, "middle")
    # right: phasors
    ox, oy, L = 300, 214, 58
    spin = 0.9 * t                                      # overall phase turns; only the difference matters
    d = amp_phase(y)
    a1 = spin
    a2 = spin + d
    x1, y1 = ox + L * math.cos(a1), oy - L * math.sin(a1)
    x2, y2 = x1 + L * math.cos(a2), y1 - L * math.sin(a2)
    body += f'<circle cx="{ox}" cy="{oy}" r="{2 * L}" fill="none" stroke="#222" stroke-width="1"/>'
    body += arrow(ox, oy, x1, y1, VIOLET, 3.5)
    body += arrow(x1, y1, x2, y2, CYAN, 3.5)
    if math.hypot(x2 - ox, y2 - oy) > 6:
        body += arrow(ox, oy, x2, y2, GREEN, 2.5)
    body += text(ox - 52, Y_TOP + 4, "φ₁", 18, VIOLET, weight="700") + text(ox - 22, Y_TOP + 4, "+", 18, DIM)
    body += text(ox, Y_TOP + 4, "φ₂", 18, CYAN, weight="700") + text(ox + 32, Y_TOP + 4, "=", 18, DIM)
    body += text(ox + 56, Y_TOP + 4, "sum", 16, GREEN, weight="700")
    prob = (2 * math.cos(d / 2)) ** 2 / 4                 # |φ1+φ2|² normalized to 1
    body += f'<rect x="238" y="314" width="{190 * prob:.1f}" height="10" rx="5" fill="{GREEN}"/>'
    body += f'<rect x="238" y="314" width="190" height="10" rx="5" fill="none" stroke="#333"/>'
    body += text(238, 306, "|sum|²", 13, DIM)
    body += text(240, 360, "P = |φ₁ + φ₂|²", 26, INK, "middle", "700")
    return overlay(body, "AMPLITUDES", VIOLET), None


def uncertainty(T, t):
    sigma = 46 + 32 * math.sin(2 * math.pi * t / 6.0)      # breathing wave packet
    pts = []
    for x in range(40, 441, 2):
        u = (x - 240) / sigma
        yv = 128 - 58 * math.exp(-u * u / 2) * math.cos(0.32 * (x - 240) - 5 * t)
        pts.append(f"{x},{yv:.1f}")
    body = polyline(" ".join(pts), GREEN, 2.5)
    body += f'<line x1="{240 - sigma:.1f}" y1="196" x2="{240 + sigma:.1f}" y2="196" stroke="{GREEN}" stroke-width="2"/>'
    body += text(240, 216, "Δx", 15, GREEN, "middle", "700")
    sp = 1500 / sigma                                      # momentum spread is the inverse
    mom = []
    for x in range(40, 441, 3):
        u = (x - 240) / sp
        mom.append(f"{x},{300 - 64 * math.exp(-u * u / 2):.1f}")
    body += f'<polygon points="40,300 {" ".join(mom)} 440,300" fill="{AMBER}" opacity="0.35"/>'
    body += polyline(" ".join(mom), AMBER, 2)
    body += text(446, 296, "Δp", 15, AMBER, "end", "700")
    body += text(40, 222, "where it is", 12, DIM) + text(40, 322, "how it's moving", 12, DIM)
    body += text(240, 364, "Δx · Δp ≥ ħ/2", 30, INK, "middle", "700")
    return overlay(body, "UNCERTAINTY", GREEN), None


def closing(T, t):
    def card(y, head, rule, color, a):
        return (f'<g opacity="{a:.2f}"><rect x="36" y="{y}" width="408" height="108" rx="14" fill="none" stroke="{color}" stroke-width="2"/>'
                + text(56, y + 34, head, 15, DIM) + text(56, y + 80, rule, 30, color, weight="700") + "</g>")
    a1, a2 = ramp(t, 0.5, 0.8), ramp(t, T * 0.3, 0.8)
    body = card(76, "can't tell which way", "P = |φ₁ + φ₂|²", VIOLET, a1)
    body += card(204, "can tell which way", "P = P₁ + P₂", AMBER, a2)
    if a1:                                              # little spinning phasors
        ox, oy, L = 372, 130, 22
        s = 1.6 * t
        x1, y1 = ox + L * math.cos(s), oy - L * math.sin(s)
        x2, y2 = x1 + L * math.cos(s + 1.1 * math.sin(t)), y1 - L * math.sin(s + 1.1 * math.sin(t))
        body += f'<g opacity="{a1:.2f}">' + arrow(ox, oy, x1, y1, VIOLET, 2.5) + arrow(x1, y1, x2, y2, CYAN, 2.5) + "</g>"
    if a2:                                              # two humps drawing in
        g = ramp(t, T * 0.3 + 0.5, 3)
        pts = [f"{340 + i:.0f},{290 - 34 * (math.exp(-((i - 30) / 12) ** 2) + math.exp(-((i - 70) / 12) ** 2)):.1f}"
               for i in range(0, int(100 * g) + 1, 2)]
        if len(pts) > 1:
            body += polyline(" ".join(pts), AMBER, 2.5, a2)
    return overlay(body, "THE RULES", INK), None


def _legacy(fn):
    """Older scenes animate on their own clock and ignore the narration beats."""
    return lambda T, t, B: fn(T, t)


def _load():
    import importlib
    table = {
        "00-title": title, "01-bullets": bullets, "02-waves": waves, "03-electrons": electrons,
        "04-amplitudes": amplitudes, "05-watching": watching, "06-dim-light": dim_light,
        "07-uncertainty": uncertainty, "08-closing": closing,
    }
    out = {}
    for name, fn in table.items():
        mod = name.split("-", 1)[1].replace("-", "_")
        try:
            out[name] = importlib.import_module(f"beats.{mod}").scene
        except ModuleNotFoundError:
            out[name] = _legacy(fn)
    return out


SCENES = _load()

DESCRIPTIONS = {
    "00-title": "title card",
    "01-bullets": "bullets through two holes pile up into P1 + P2, no interference",
    "02-waves": "water waves through two holes interfere; intensity has fringes",
    "03-electrons": "single electrons click one at a time and build an interference pattern",
    "04-amplitudes": "two amplitude arrows add; their sum squared traces the fringe pattern",
    "05-watching": "a light shows which hole each electron used; fringes vanish into P1 + P2",
    "06-dim-light": "dim light: seen electrons give humps, missed ones give fringes",
    "07-uncertainty": "wave packet: narrower in position means wider in momentum",
    "08-closing": "the two rules: add amplitudes if you can't tell, probabilities if you can",
}
