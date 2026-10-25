"""Motion toolkit for explainer-style scenes: easing, entrances, draw-on lines, kinetic type, callouts.

Everything returns SVG strings (or "" when not visible yet), so scenes compose by concatenation:

    body += pop(gun_svg, t, B[1], origin=(44, 200))
    body += draw_line(168, 74, 168, 326, prog(t, B[2], 0.8), INK, 5)
    body += kinetic("LUMPS", t, B[5], hold=2.0, color=AMBER)

Beats: B[i] is the start (seconds into the segment) of narration line i, B.end(i) its end, and
B.sub(i, k, n) the k-th of n equal slices of line i (for "Click. Click. Click.").
"""
import math

from make_visuals import FONT, INK, text  # noqa: F401  (re-exported for scene modules)

FAR = 1e9


class Beats:
    def __init__(self, starts, ends):
        self.starts, self.ends = list(starts), list(ends)

    def __getitem__(self, i):
        return self.starts[i] if 0 <= i < len(self.starts) else FAR

    def __len__(self):
        return len(self.starts)

    def end(self, i):
        return self.ends[i] if 0 <= i < len(self.ends) else FAR

    def sub(self, i, k, n):
        return self[i] + (self.end(i) - self[i]) * k / n

    def active(self, t):
        """Index of the line being spoken (or most recently finished) at time t."""
        idx = -1
        for i, s in enumerate(self.starts):
            if t >= s:
                idx = i
        return idx


# ---------------------------------------------------------------- easing

def clamp01(x):
    return 0.0 if x <= 0 else 1.0 if x >= 1 else x


def ease_out(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_back(x, s=1.70158):
    x = clamp01(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def prog(t, t0, dur=0.6, ease=ease_out):
    """Eased 0..1 progress of an animation that starts at t0 and lasts dur."""
    return ease((t - t0) / dur) if dur > 0 else float(t >= t0)


def between(t, t0, t1, fade=0.3):
    """Opacity for something visible from t0 to t1 with short fades at both ends."""
    if t < t0 or t > t1 + fade:
        return 0.0
    return min(clamp01((t - t0) / fade), 1 - clamp01((t - t1) / fade))


def lerp(a, b, p):
    return a + (b - a) * p


def osc(t, period=2.0, lo=0.0, hi=1.0):
    return lo + (hi - lo) * (0.5 - 0.5 * math.cos(2 * math.pi * t / period))


# ---------------------------------------------------------------- grouping / entrances

def g(content, x=0.0, y=0.0, s=1.0, o=1.0, rot=0.0, origin=(0.0, 0.0)):
    if not content or o <= 0.001 or s <= 0.001:
        return ""
    ox, oy = origin
    tf = f"translate({x:.1f},{y:.1f})"
    if s != 1 or rot:
        tf += f" translate({ox:.1f},{oy:.1f}) scale({s:.3f}) rotate({rot:.1f}) translate({-ox:.1f},{-oy:.1f})"
    op = f' opacity="{o:.2f}"' if o < 1 else ""
    return f'<g transform="{tf}"{op}>{content}</g>'


def pop(content, t, t0, origin, dur=0.45, out=None):
    """Scale up from nothing with a little overshoot; optional exit at `out`."""
    if t < t0:
        return ""
    s = ease_back((t - t0) / dur)
    o = clamp01((t - t0) / (dur * 0.5))
    if out is not None and t > out:
        k = clamp01((t - out) / 0.35)
        s, o = s * (1 - 0.3 * k), o * (1 - k)
    return g(content, s=s, o=o, origin=origin)


def slide_in(content, t, t0, dx=-70.0, dy=0.0, dur=0.55, out=None):
    if t < t0:
        return ""
    p = ease_out((t - t0) / dur)
    o = clamp01((t - t0) / (dur * 0.6))
    if out is not None and t > out:
        o *= 1 - clamp01((t - out) / 0.35)
    return g(content, x=dx * (1 - p), y=dy * (1 - p), o=o)


def fade(content, t, t0, t1=FAR, dur=0.35):
    return g(content, o=between(t, t0, t1, dur))


# ---------------------------------------------------------------- lines and paths

def draw_line(x1, y1, x2, y2, p, color, width=2.5, opacity=1.0, dash=None, cap="round"):
    if p <= 0:
        return ""
    x, y = lerp(x1, x2, p), lerp(y1, y2, p)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="{cap}" opacity="{opacity:.2f}"{d}/>')


def draw_path(points, p, color, width=2.5, opacity=1.0, dash=None, fill="none"):
    """Polyline revealed along its length: p=0 nothing, p=1 complete. points: [(x, y), ...]."""
    if p <= 0 or len(points) < 2:
        return ""
    seg = [math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
           for i in range(len(points) - 1)]
    goal, acc, out = sum(seg) * clamp01(p), 0.0, [points[0]]
    for i, L in enumerate(seg):
        if acc + L >= goal:
            f = (goal - acc) / L if L else 0
            out.append((lerp(points[i][0], points[i + 1][0], f), lerp(points[i][1], points[i + 1][1], f)))
            break
        out.append(points[i + 1])
        acc += L
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in out)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{pts}" fill="{fill}" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity="{opacity:.2f}"{d}/>')


def arrow_draw(x1, y1, x2, y2, p, color, width=3.0):
    """Arrow that grows from its tail; head appears once it has length."""
    if p <= 0:
        return ""
    x, y = lerp(x1, x2, p), lerp(y1, y2, p)
    ang = math.atan2(y - y1, x - x1)
    h = min(12, math.hypot(x - x1, y - y1) * 0.6)
    head = ""
    if h > 2:
        a1, a2 = ang - 0.42, ang + 0.42
        head = (f'<polygon points="{x:.1f},{y:.1f} {x - h * math.cos(a1):.1f},{y - h * math.sin(a1):.1f} '
                f'{x - h * math.cos(a2):.1f},{y - h * math.sin(a2):.1f}" fill="{color}"/>')
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round"/>' + head)


# ---------------------------------------------------------------- type

def typewriter(x, y, s, t, t0, cps=28.0, size=16, color=INK, anchor="start", weight="400"):
    if t < t0:
        return ""
    n = int((t - t0) * cps)
    return text(x, y, s[:n], size, color, anchor, weight) if n > 0 else ""


def kinetic(word, t, t0, hold=1.6, color=INK, x=240, y=210, size=58, sub=None, sub_color=None):
    """Big headline word: punches in, holds, then lifts away. The YouTube-explainer beat."""
    if t < t0 or t > t0 + hold + 0.45:
        return ""
    s = ease_back((t - t0) / 0.4, 2.2)
    o = clamp01((t - t0) / 0.15)
    dy = 0.0
    if t > t0 + hold:
        k = ease_in_out((t - t0 - hold) / 0.45)
        o *= 1 - k
        dy = -30 * k
    body = text(x, y, word, size, color, "middle", "800")
    if sub:
        body += text(x, y + size * 0.62, sub, 18, sub_color or INK, "middle", "500")
    backing = f'<rect x="0" y="{y - size * 1.05:.0f}" width="480" height="{size * 1.6 + (26 if sub else 0):.0f}" fill="#000" opacity="0.72"/>'
    return g(backing + body, y=dy, s=s, o=o, origin=(x, y - size * 0.35))


def pill(x, y, label, color, size=14, anchor="middle", bg="#111"):
    w = len(label) * size * 0.58 + 18
    x0 = x - w / 2 if anchor == "middle" else x if anchor == "start" else x - w
    return (f'<rect x="{x0:.1f}" y="{y - size - 4:.1f}" width="{w:.1f}" height="{size + 12:.1f}" rx="{(size + 12) / 2:.1f}" '
            f'fill="{bg}" stroke="{color}" stroke-width="1.5"/>'
            + text(x0 + w / 2, y + 1, label, size, color, "middle", "700"))


def callout(px, py, label, t, t0, color, dx=46, dy=-36, out=None, size=14):
    """Leader line from a point of interest, then a label pill pops at its end."""
    if t < t0:
        return ""
    p = prog(t, t0, 0.35)
    o = 1.0 if out is None else 1 - clamp01((t - out) / 0.35)
    if o <= 0:
        return ""
    lx, ly = px + dx, py + dy
    body = f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}"/>'
    body += draw_line(px, py, lx, ly, p, color, 1.6)
    body += pop(pill(lx, ly, label, color, size), t, t0 + 0.25, (lx, ly - size / 2))
    return g(body, o=o)


def pulse(x, y, t, t0, color, r=16, rings=2, period=0.7):
    """Expanding highlight rings to point at something as it's mentioned."""
    out = ""
    for i in range(rings):
        k = (t - t0 - i * period * 0.5) / period
        if 0 <= k <= 1:
            out += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * (0.6 + 1.2 * k):.1f}" fill="none" '
                    f'stroke="{color}" stroke-width="{3 * (1 - k) + 0.5:.1f}" opacity="{1 - k:.2f}"/>')
    return out


def check(x, y, t, t0, color, size=26):
    p = prog(t, t0, 0.4)
    pts = [(x - size * 0.5, y), (x - size * 0.15, y + size * 0.35), (x + size * 0.55, y - size * 0.45)]
    return draw_path(pts, p, color, size * 0.16)


def cross(x, y, t, t0, color, size=22):
    p1, p2 = prog(t, t0, 0.22), prog(t, t0 + 0.15, 0.22)
    h = size / 2
    return (draw_line(x - h, y - h, x + h, y + h, p1, color, size * 0.16)
            + draw_line(x + h, y - h, x - h, y + h, p2, color, size * 0.16))


def strike(x1, x2, y, t, t0, color, width=4):
    return draw_line(x1, y, x2, y, prog(t, t0, 0.3), color, width)


def shake(t, t0, dur=0.5, amp=6.0):
    """(dx, dy) camera jitter that decays over dur."""
    if not (t0 <= t <= t0 + dur):
        return 0.0, 0.0
    k = 1 - (t - t0) / dur
    return amp * k * math.sin(55 * t), amp * k * math.cos(43 * t)


def counter_text(x, y, value, label, color, size=15, anchor="end"):
    return text(x, y, f"{label} {value}", size, color, anchor, "700")
