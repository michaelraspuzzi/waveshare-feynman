"""Generate the 480x480 SVG explainer diagrams for the Quantum Behavior lecture.

The bottom band (y > 340) is left empty: the device draws subtitles there.
Run: python tools/make_visuals.py  ->  content/quantum-behavior/visuals/*.svg
"""
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "content" / "quantum-behavior" / "visuals"

BG = "#000000"
INK = "#e8e6e1"
DIM = "#6b6a66"
AMBER = "#ffb547"
CYAN = "#4fd6ff"
VIOLET = "#b993ff"
GREEN = "#7be38f"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"

# Experiment geometry (shared by all two-slit scenes)
SRC_X, WALL_X, STOP_X = 44, 168, 298
Y_TOP, Y_BOT, Y_MID = 74, 326, 200
HOLE1, HOLE2, HOLE_R = 168, 232, 9
CURVE_X0, CURVE_W = 304, 138


def svg(body, title, accent, bg=True):
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480" viewBox="0 0 480 480">'
        + (f'<rect width="480" height="480" fill="{BG}"/>' if bg else "")
        + f'<g font-family="{FONT}">'
    )
    label = (
        f'<text x="36" y="46" fill="{accent}" font-size="17" font-weight="700" letter-spacing="3">{title}</text>'
        if title else ""
    )
    return head + label + body + "</g></svg>"


def text(x, y, s, size=16, fill=INK, anchor="start", weight="400", style=""):
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {style}>{s}</text>')


def gauss(y, mu, s=48):
    return math.exp(-((y - mu) ** 2) / (2 * s * s))


def p1(y): return gauss(y, HOLE1 - 14)
def p2(y): return gauss(y, HOLE2 + 14)


def interference(y, visibility=1.0, k=0.19):
    a, b = p1(y), p2(y)
    return a + b + visibility * 2 * math.sqrt(a * b) * math.cos(k * (y - Y_MID))


def curve(fn, peak, color, width=2.2, dash=None, opacity=1.0):
    pts = []
    for y in range(Y_TOP, Y_BOT + 1, 2):
        x = CURVE_X0 + CURVE_W * fn(y) / peak
        pts.append(f"{x:.1f},{y}")
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round" opacity="{opacity}"{d}/>')


def peak_of(fn):
    return max(fn(y) for y in range(Y_TOP, Y_BOT + 1))


def wall(color=INK):
    segs = [(Y_TOP, HOLE1 - HOLE_R), (HOLE1 + HOLE_R, HOLE2 - HOLE_R), (HOLE2 + HOLE_R, Y_BOT)]
    out = "".join(f'<line x1="{WALL_X}" y1="{a}" x2="{WALL_X}" y2="{b}" stroke="{color}" stroke-width="5"/>'
                  for a, b in segs)
    out += text(WALL_X - 16, HOLE1 + 5, "1", 13, DIM, "middle")
    out += text(WALL_X - 16, HOLE2 + 5, "2", 13, DIM, "middle")
    return out


def backstop():
    return f'<line x1="{STOP_X}" y1="{Y_TOP}" x2="{STOP_X}" y2="{Y_BOT}" stroke="{DIM}" stroke-width="3"/>'


def caption(s, color=INK, y=354, size=18):
    return text(240, y, s, size, color, "middle", "600")


def arcs(cx, cy, radii, x_min, x_max, color, opacity=0.55):
    out = []
    for r in radii:
        # sweep the right half-circle, clipped to [x_min, x_max]
        pts = []
        for i in range(-90, 91, 3):
            a = math.radians(i)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            if x_min <= x <= x_max and Y_TOP <= y <= Y_BOT:
                pts.append(f"{x:.1f},{y:.1f}")
            elif pts:
                break
        if len(pts) > 1:
            out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
                       f'stroke-width="1.6" opacity="{opacity}"/>')
    return "".join(out)


def gun(color):
    return (f'<rect x="{SRC_X - 20}" y="{Y_MID - 12}" width="34" height="24" rx="4" fill="none" '
            f'stroke="{color}" stroke-width="2.5"/>'
            f'<line x1="{SRC_X + 14}" y1="{Y_MID}" x2="{SRC_X + 26}" y2="{Y_MID}" stroke="{color}" stroke-width="5"/>')


def filament(color):
    pts = " ".join(f"{SRC_X - 14 + i * 4},{Y_MID + (6 if i % 2 else -6)}" for i in range(8))
    return (f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>'
            f'<circle cx="{SRC_X}" cy="{Y_MID}" r="24" fill="none" stroke="{color}" stroke-width="1.2" opacity="0.5"/>')


# --------------------------------------------------------------------------- scenes

def title_scene():
    fringes = []
    for i in range(-11, 12):
        v = 0.5 + 0.5 * math.cos(i * 0.9) * math.exp(-(i * i) / 70)
        fringes.append(f'<rect x="{240 + i * 14 - 4}" y="96" width="8" height="120" rx="4" '
                       f'fill="{VIOLET}" opacity="{0.08 + 0.85 * v:.2f}"/>')
    body = "".join(fringes)
    body += text(240, 272, "Quantum", 46, INK, "middle", "700")
    body += text(240, 320, "Behavior", 46, INK, "middle", "700")
    return svg(body, "FEYNMAN TUTOR", VIOLET)


def bullets_scene():
    pk = peak_of(lambda y: p1(y) + p2(y))
    body = gun(AMBER) + wall() + backstop()
    rnd = random.Random(3)
    for _ in range(14):  # bullets in flight
        y = rnd.uniform(Y_TOP + 20, Y_BOT - 20)
        x = rnd.uniform(SRC_X + 40, WALL_X - 12)
        body += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="{AMBER}" opacity="0.7"/>'
    body += curve(p1, pk, AMBER, 1.6, "4 4", 0.6)
    body += curve(p2, pk, AMBER, 1.6, "4 4", 0.6)
    body += curve(lambda y: p1(y) + p2(y), pk, AMBER, 3)
    body += text(446, HOLE1 - 52, "P₁", 15, DIM, "end")
    body += text(446, HOLE2 + 66, "P₂", 15, DIM, "end")
    body += caption("P₁₂ = P₁ + P₂", AMBER)
    return svg(body, "BULLETS", AMBER)


def waves_scene():
    pk = peak_of(interference)
    body = (f'<circle cx="{SRC_X}" cy="{Y_MID}" r="6" fill="{CYAN}"/>'
            + arcs(SRC_X, Y_MID, range(18, 140, 16), SRC_X, WALL_X - 3, CYAN)
            + arcs(WALL_X, HOLE1, range(12, 150, 16), WALL_X + 3, STOP_X - 3, CYAN, 0.4)
            + arcs(WALL_X, HOLE2, range(12, 150, 16), WALL_X + 3, STOP_X - 3, CYAN, 0.4)
            + wall() + backstop())
    body += curve(p1, pk, CYAN, 1.4, "4 4", 0.5)
    body += curve(p2, pk, CYAN, 1.4, "4 4", 0.5)
    body += curve(interference, pk, CYAN, 3)
    body += caption("I₁₂ ≠ I₁ + I₂", CYAN)
    body += text(240, 376, "add heights, then square", 14, DIM, "middle")
    return svg(body, "WATER WAVES", CYAN)


def electrons_scene():
    pk = peak_of(interference)
    body = filament(VIOLET) + wall() + backstop()
    rnd = random.Random(7)
    hits = 0
    while hits < 260:  # rejection-sample clicks from the interference pattern
        y = rnd.uniform(Y_TOP, Y_BOT)
        if rnd.uniform(0, pk) < interference(y):
            x = STOP_X - 4 - rnd.uniform(0, 14)
            body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{VIOLET}" opacity="0.85"/>'
            hits += 1
    body += curve(interference, pk, VIOLET, 3)
    body += text(STOP_X - 70, Y_TOP + 4, "click!", 14, INK, "middle", "700")
    body += caption("arrive like lumps · add like waves", VIOLET, size=17)
    return svg(body, "ELECTRONS", VIOLET)


def arrow(x1, y1, x2, y2, color, w=3.5, label=None, lx=0, ly=0):
    ang = math.atan2(y2 - y1, x2 - x1)
    h = 12
    hx1, hy1 = x2 - h * math.cos(ang - 0.4), y2 - h * math.sin(ang - 0.4)
    hx2, hy2 = x2 - h * math.cos(ang + 0.4), y2 - h * math.sin(ang + 0.4)
    out = (f'<line x1="{x1}" y1="{y1}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{w}" '
           f'stroke-linecap="round"/>'
           f'<polygon points="{x2:.1f},{y2:.1f} {hx1:.1f},{hy1:.1f} {hx2:.1f},{hy2:.1f}" fill="{color}"/>')
    if label:
        out += text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, 16, color, "middle", "600")
    return out


def amplitudes_scene():
    body = ""
    # in step: arrows line up -> big
    body += text(120, 96, "in step", 15, DIM, "middle")
    body += arrow(40, 250, 120, 196, VIOLET, label="φ₁", lx=-16, ly=-8)
    body += arrow(120, 196, 168, 116, CYAN, label="φ₂", lx=-16, ly=-4)
    body += arrow(40, 250, 168, 116, GREEN, 2.5)
    body += text(150, 214, "big", 16, GREEN, "start", "700")
    # opposite: arrows cancel -> nothing
    body += text(360, 96, "opposite", 15, DIM, "middle")
    body += arrow(296, 196, 420, 146, VIOLET, label="φ₁", lx=-4, ly=-16)
    body += arrow(420, 162, 308, 210, CYAN, label="φ₂", lx=12, ly=24)
    body += f'<circle cx="302" cy="204" r="5" fill="{GREEN}"/>'
    body += text(360, 250, "nothing", 16, GREEN, "middle", "700")
    body += text(240, 312, "P = |φ₁ + φ₂|²", 30, INK, "middle", "700")
    return svg(body, "AMPLITUDES", VIOLET)


def lamp(cx, cy, color):
    rays = "".join(
        f'<line x1="{cx + 14 * math.cos(a):.1f}" y1="{cy + 14 * math.sin(a):.1f}" '
        f'x2="{cx + 24 * math.cos(a):.1f}" y2="{cy + 24 * math.sin(a):.1f}" stroke="{color}" stroke-width="2"/>'
        for a in [i * math.pi / 4 for i in range(8)])
    return f'<circle cx="{cx}" cy="{cy}" r="9" fill="{color}"/>' + rays


def flash(cx, cy, color, r=16):
    pts = []
    for i in range(16):
        rr = r if i % 2 == 0 else r * 0.4
        a = i * math.pi / 8
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{color}"/>'


def watching_scene():
    fn = lambda y: p1(y) + p2(y)
    pk = peak_of(fn)
    body = filament(VIOLET) + wall() + backstop()
    body += lamp(WALL_X + 52, Y_MID, AMBER)
    body += flash(WALL_X + 12, HOLE1, AMBER)
    body += curve(interference, peak_of(interference), VIOLET, 1.4, "3 5", 0.35)
    body += curve(fn, pk, VIOLET, 3)
    body += caption("watching → P₁ + P₂", AMBER)
    body += text(240, 376, "the wiggles disappear", 14, DIM, "middle")
    return svg(body, "WHICH HOLE?", AMBER)


def dim_light_scene():
    fn = lambda y: interference(y, visibility=0.5)
    pk = peak_of(fn)
    body = filament(VIOLET) + wall() + backstop()
    body += lamp(WALL_X + 52, Y_MID, DIM)
    body += f'<circle cx="{WALL_X + 14}" cy="{HOLE2}" r="4" fill="{AMBER}" opacity="0.5"/>'
    body += curve(lambda y: p1(y) + p2(y), peak_of(lambda y: p1(y) + p2(y)), AMBER, 1.4, "4 4", 0.6)
    body += curve(fn, pk, VIOLET, 3)
    body += caption("which-way  OR  wiggles", INK)
    body += text(240, 376, "never both", 14, DIM, "middle")
    return svg(body, "DIMMER LIGHT", DIM)


def uncertainty_scene():
    pts = []
    for i in range(0, 361, 2):
        x = 60 + i
        t = (x - 240) / 48
        y = 160 - 52 * math.exp(-t * t) * math.cos(3.2 * t)
        pts.append(f"{x},{y:.1f}")
    body = f'<polyline points="{" ".join(pts)}" fill="none" stroke="{GREEN}" stroke-width="2.5"/>'
    body += text(240, 268, "Δx · Δp ≥ ħ/2", 34, INK, "middle", "700")
    body += text(240, 310, "any way to know the hole", 15, DIM, "middle")
    body += text(240, 330, "kicks the pattern away", 15, DIM, "middle")
    return svg(body, "UNCERTAINTY", GREEN)


def closing_scene():
    def card(y, head, rule, color):
        return (f'<rect x="36" y="{y}" width="408" height="108" rx="14" fill="none" stroke="{color}" stroke-width="2"/>'
                + text(56, y + 34, head, 15, DIM)
                + text(56, y + 80, rule, 30, color, weight="700"))
    body = card(76, "can't tell which way", "P = |φ₁ + φ₂|²", VIOLET)
    body += card(204, "can tell which way", "P = P₁ + P₂", AMBER)
    return svg(body, "THE RULES", INK)


SCENES = {
    "00-title": title_scene,
    "01-bullets": bullets_scene,
    "02-waves": waves_scene,
    "03-electrons": electrons_scene,
    "04-amplitudes": amplitudes_scene,
    "05-watching": watching_scene,
    "06-dim-light": dim_light_scene,
    "07-uncertainty": uncertainty_scene,
    "08-closing": closing_scene,
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in SCENES.items():
        (OUT / f"{name}.svg").write_text(fn())
        print("wrote", name)
