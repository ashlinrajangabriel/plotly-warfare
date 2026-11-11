"""Generate all SVG icons for the game into assets/icons/  (top-down view).

Run (Docker):
  docker run --rm -v "F:\\PLOTLY:/app" -w /app python:3.12-slim python tools/gen_icons.py

Pure standard library. Every icon is 128x128. Units/effects are transparent and
FACE EAST (+x) so Plotly can rotate them by heading. Terrain tiles are full squares.
"""
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "icons"

STEEL, STEEL_D, STEEL_L = "#c4cad1", "#4f5963", "#eef1f4"


def mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


TEAMS = {"blue": ("#2f6fb5", "#10294a"), "red": ("#c2412f", "#4d130c")}


def svg(inner, defs=""):
    d = f"<defs>{defs}</defs>" if defs else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">{d}{inner}</svg>\n'


def team_defs(k, c, d):
    edge, mid = mix(c, d, .45), mix(c, "#ffffff", .25)
    return (
        f'<linearGradient id="h{k}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{edge}"/>'
        f'<stop offset=".45" stop-color="{mid}"/><stop offset="1" stop-color="{edge}"/></linearGradient>'
        f'<linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{STEEL_D}"/>'
        f'<stop offset=".4" stop-color="{STEEL_L}"/><stop offset="1" stop-color="{STEEL}"/></linearGradient>'
    )


# ---------------- shared drawing parts ----------------
def hull_path(x0, x1, w, bow, st=6):
    t, b = 64 - w / 2, 64 + w / 2
    return (f"M{x0} {t+st} Q{x0} {t} {x0+st} {t} H{x1-bow} Q{x1-bow/4} {t} {x1} 64 "
            f"Q{x1-bow/4} {b} {x1-bow} {b} H{x0+st} Q{x0} {b} {x0} {b-st} Z")


def ship_base(k, d, x0, x1, w, bow):
    hp = hull_path(x0, x1, w, bow)
    deck = hull_path(x0 + 5, x1 - 7, w - 9, max(bow - 6, 8), 4)
    return (f'<path d="{hp}" transform="translate(3 5)" fill="#000" opacity=".28"/>'
            f'<path d="{hp}" fill="url(#h{k})" stroke="{d}" stroke-width="4" stroke-linejoin="round"/>'
            f'<path d="{deck}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2"/>')


PENDING = []


def turret(cx, cy, r, n, ln, d, dr=1):
    offs = {1: [0], 2: [-r * .32, r * .32], 3: [-r * .5, 0, r * .5]}[n]
    bw = max(3.5, r * .32)
    bar = "".join(f'<line x1="{cx+dr*r*.3:.1f}" y1="{cy+o:.1f}" x2="{cx+dr*ln}" y2="{cy+o:.1f}" stroke="#23282d" stroke-width="{bw:.1f}" stroke-linecap="round"/>'
                  f'<line x1="{cx+dr*r*.3:.1f}" y1="{cy+o:.1f}" x2="{cx+dr*ln}" y2="{cy+o:.1f}" stroke="#9aa3ad" stroke-width="1.4" stroke-linecap="round"/>' for o in offs)
    PENDING.append(bar)  # barrels are drawn last so they overlap the next turret (superfiring look)
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#s)" stroke="{d}" stroke-width="3"/>'
            f'<circle cx="{cx-r*.25}" cy="{cy-r*.25}" r="{r*.3:.1f}" fill="#fff" opacity=".55"/>')


def bridge(x, y, w, h, d):
    return (f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="3" fill="url(#s)" stroke="{d}" stroke-width="3"/>'
            f'<rect x="{x+w/2-5}" y="{y-h/2+2}" width="3" height="{h-4}" fill="{d}" opacity=".7"/>')


def funnel(x, y, rx, ry, d):
    return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="#3a4046" stroke="{d}" stroke-width="3"/>'
            f'<ellipse cx="{x}" cy="{y}" rx="{rx*.55:.1f}" ry="{ry*.55:.1f}" fill="#111"/>')


def small_mine(cx, cy, r=7):
    sp = "".join(f'<line x1="{cx}" y1="{cy}" x2="{cx+(r+4)*math.cos(a):.1f}" y2="{cy+(r+4)*math.sin(a):.1f}" '
                 f'stroke="#222" stroke-width="3" stroke-linecap="round"/>' for a in [i * math.pi / 4 for i in range(8)])
    return sp + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#454b52" stroke="#111" stroke-width="2.5"/><circle cx="{cx-2}" cy="{cy-2}" r="2" fill="#fff" opacity=".6"/>'


# ---------------- ships ----------------
def minesweeper(k, c, d):
    arms = ""
    for s in (-1, 1):
        arms += (f'<line x1="40" y1="{64+s*8}" x2="12" y2="{64+s*34}" stroke="{d}" stroke-width="3"/>'
                 f'<circle cx="12" cy="{64+s*34}" r="6" fill="#f2a33a" stroke="{d}" stroke-width="3"/>')
    return (arms + ship_base(k, d, 34, 100, 24, 24) + bridge(66, 64, 18, 14, d) + funnel(52, 64, 5, 6, d)
            + turret(84, 64, 6, 1, 10, d))


def minelayer(k, c, d):
    mines = "".join(small_mine(x, y) for x, y in ((38, 54), (38, 74), (56, 54), (56, 74)))
    rail = f'<rect x="28" y="48" width="42" height="32" rx="3" fill="none" stroke="{STEEL}" stroke-width="2.5" stroke-dasharray="5 3"/>'
    return (ship_base(k, d, 24, 106, 32, 26) + rail + mines + funnel(74, 64, 6, 7, d)
            + bridge(88, 64, 16, 16, d) + turret(100, 64, 5, 1, 8, d))


def destroyer(k, c, d):
    tt = f'<rect x="36" y="56" width="14" height="16" rx="2" fill="url(#s)" stroke="{d}" stroke-width="2.5"/><line x1="43" y1="58" x2="43" y2="70" stroke="{d}" stroke-width="2"/>'
    return (ship_base(k, d, 10, 120, 22, 36) + turret(30, 64, 7, 1, 13, d, -1) + tt + funnel(58, 64, 6, 7, d)
            + bridge(70, 64, 14, 14, d) + turret(86, 64, 7, 2, 14, d) + turret(102, 64, 6, 2, 12, d))


def cruiser(k, c, d):
    return (ship_base(k, d, 6, 122, 30, 34) + turret(22, 64, 9, 3, 15, d, -1) + funnel(42, 64, 6, 8, d)
            + funnel(54, 64, 6, 8, d) + bridge(68, 64, 18, 18, d) + turret(86, 64, 9, 3, 16, d)
            + turret(102, 64, 8, 3, 15, d))


def battleship(k, c, d):
    side = "".join(f'<circle cx="{x}" cy="{y}" r="4.5" fill="url(#s)" stroke="{d}" stroke-width="2"/>' for x, y in ((48, 49), (48, 79), (64, 48), (64, 80)))
    return (ship_base(k, d, 2, 126, 42, 36) + turret(20, 64, 12, 3, 24, d, -1) + turret(40, 64, 12, 3, 24, d, -1)
            + funnel(58, 64, 8, 10, d) + side + bridge(74, 64, 22, 22, d) + turret(98, 64, 12, 3, 24, d)
            + f'<circle cx="74" cy="64" r="4" fill="{d}"/>')


def submarine(k, c, d):
    body = "M10 64 Q10 52 30 52 H96 Q120 52 120 64 Q120 76 96 76 H30 Q10 76 10 64Z"
    planes = "".join(f'<path d="M86 {64+s*12} L96 {64+s*22} L100 {64+s*22} L96 {64+s*12}Z" fill="{d}"/>'
                     f'<path d="M24 {64+s*12} L16 {64+s*20} L12 {64+s*20} L18 {64+s*12}Z" fill="{d}"/>' for s in (-1, 1))
    return (f'<path d="{body}" transform="translate(3 5)" fill="#000" opacity=".28"/>' + planes
            + f'<path d="{body}" fill="url(#h{k})" stroke="{d}" stroke-width="4"/>'
            + f'<line x1="26" y1="64" x2="108" y2="64" stroke="#fff" stroke-opacity=".3" stroke-width="2"/>'
            + f'<rect x="52" y="56" width="26" height="16" rx="7" fill="url(#s)" stroke="{d}" stroke-width="3"/>'
            + f'<circle cx="60" cy="64" r="3" fill="{d}"/><circle cx="8" cy="64" r="5" fill="{STEEL}" stroke="{d}" stroke-width="2"/>')


# ---------------- land / missile units ----------------
def soldier(cx, cy, c, d):
    return (f'<g transform="translate({cx} {cy}) scale(1.35)">'
            f'<line x1="-4" y1="7" x2="24" y2="7" stroke="#1b1e22" stroke-width="4" stroke-linecap="round"/>'
            f'<line x1="-4" y1="7" x2="24" y2="7" stroke="#9aa3ad" stroke-width="1.3" stroke-linecap="round"/>'
            f'<rect x="-12" y="-6" width="8" height="12" rx="2" fill="#4a4f3a" stroke="#1b1e22" stroke-width="2"/>'
            f'<ellipse cx="0" cy="0" rx="6" ry="12" fill="#6b7358" stroke="#1b1e22" stroke-width="2.5"/>'
            f'<rect x="-3" y="-12" width="6" height="4" rx="1" fill="{c}" stroke="{d}" stroke-width="1.5"/>'
            f'<rect x="-3" y="8" width="6" height="4" rx="1" fill="{c}" stroke="{d}" stroke-width="1.5"/>'
            f'<circle cx="2" cy="0" r="6.5" fill="{c}" stroke="{d}" stroke-width="2.5"/>'
            f'<circle cx="0" cy="-2" r="2" fill="#fff" opacity=".55"/></g>')


def infantry(k, c, d):
    ring = f'<ellipse cx="64" cy="66" rx="50" ry="46" fill="#000" opacity=".18"/>'
    return ring + soldier(84, 64, c, d) + soldier(46, 36, c, d) + soldier(46, 94, c, d)


def tank(k, c, d):
    tread = "".join(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+16}" stroke="#777" stroke-width="2"/>' for y0 in (34, 78) for x in range(26, 112, 6))
    return (f'<rect x="20" y="36" width="92" height="64" rx="8" fill="#000" opacity=".25"/>'
            f'<rect x="18" y="32" width="92" height="18" rx="8" fill="#2a2e33" stroke="#111" stroke-width="2"/>'
            f'<rect x="18" y="78" width="92" height="18" rx="8" fill="#2a2e33" stroke="#111" stroke-width="2"/>' + tread +
            f'<rect x="24" y="44" width="80" height="40" rx="7" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<rect x="28" y="49" width="22" height="30" rx="3" fill="none" stroke="{d}" stroke-opacity=".5" stroke-width="2" stroke-dasharray="3 3"/>'
            f'<rect x="84" y="58" width="42" height="9" rx="2" fill="url(#s)" stroke="{d}" stroke-width="2.5"/>'
            f'<rect x="118" y="55" width="9" height="15" rx="2" fill="{STEEL_D}" stroke="{d}" stroke-width="2"/>'
            f'<path d="M44 50 H78 L86 58 V70 L78 78 H44 L38 70 V58 Z" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<circle cx="56" cy="58" r="5.5" fill="url(#s)" stroke="{d}" stroke-width="2"/><circle cx="52" cy="72" r="2.5" fill="{d}"/>')


def artillery(k, c, d):
    trails = "".join(f'<line x1="44" y1="{64+s*6}" x2="8" y2="{64+s*30}" stroke="{d}" stroke-width="7" stroke-linecap="round"/>'
                     f'<line x1="44" y1="{64+s*6}" x2="8" y2="{64+s*30}" stroke="{c}" stroke-width="3" stroke-linecap="round"/>' for s in (-1, 1))
    wheels = "".join(f'<rect x="38" y="{y}" width="26" height="12" rx="5" fill="#2a2e33" stroke="#111" stroke-width="2.5"/>' for y in (30, 86))
    return (trails + wheels + f'<rect x="38" y="44" width="38" height="40" rx="6" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<rect x="76" y="40" width="9" height="48" rx="3" fill="url(#s)" stroke="{d}" stroke-width="3"/>'
            f'<rect x="85" y="60" width="38" height="8" rx="2" fill="url(#s)" stroke="{d}" stroke-width="2.5"/>'
            f'<rect x="116" y="56" width="10" height="16" rx="2" fill="{STEEL_D}" stroke="{d}" stroke-width="2"/>'
            f'<circle cx="56" cy="64" r="7" fill="url(#s)" stroke="{d}" stroke-width="2.5"/>')


def coastal_gun(k, c, d):
    bags = "".join(f'<ellipse cx="{64+50*math.cos(a):.1f}" cy="{64+50*math.sin(a):.1f}" rx="9" ry="5" '
                   f'transform="rotate({math.degrees(a)+90:.0f} {64+50*math.cos(a):.1f} {64+50*math.sin(a):.1f})" fill="#b9a37a" stroke="#6e5f3f" stroke-width="2"/>'
                   for a in [i * math.pi / 9 for i in range(18)])
    return (bags + f'<circle cx="64" cy="64" r="40" fill="#9a9a94" stroke="#4a4a46" stroke-width="4"/>'
            f'<circle cx="64" cy="64" r="34" fill="none" stroke="#c9c9c3" stroke-width="2"/>'
            f'<rect x="64" y="57" width="58" height="14" rx="3" fill="url(#s)" stroke="{d}" stroke-width="3"/>'
            f'<rect x="114" y="54" width="10" height="20" rx="2" fill="{STEEL_D}" stroke="{d}" stroke-width="2"/>'
            f'<circle cx="60" cy="64" r="24" fill="url(#h{k})" stroke="{d}" stroke-width="4"/>'
            f'<circle cx="52" cy="56" r="6" fill="#fff" opacity=".4"/><circle cx="60" cy="64" r="5" fill="{d}"/>')


def missile_body(x0, x1, y, r, c, d, fins=True):
    """Horizontal missile pointing east: white body, team-colour bands and nose."""
    nose = x1 - r * 3.2
    s = (f'<path d="M{x0} {y-r} H{nose} Q{x1-r*.6} {y-r} {x1} {y} Q{x1-r*.6} {y+r} {nose} {y+r} H{x0} Z" fill="#eef1f4" stroke="{d}" stroke-width="3"/>'
         f'<path d="M{nose-4} {y-r} H{nose+3} V{y+r} H{nose-4}Z" fill="{c}"/>'
         f'<path d="M{nose+3} {y-r} Q{x1-r*.6} {y-r} {x1} {y} Q{x1-r*.6} {y+r} {nose+3} {y+r}Z" fill="{c}" stroke="{d}" stroke-width="3"/>'
         f'<rect x="{x0+(nose-x0)*.35:.1f}" y="{y-r}" width="5" height="{2*r}" fill="{c}"/>'
         f'<line x1="{x0}" y1="{y}" x2="{nose}" y2="{y}" stroke="{d}" stroke-opacity=".25" stroke-width="2"/>')
    if fins:
        for sg in (-1, 1):
            s = (f'<path d="M{x0+14} {y+sg*r} L{x0-4} {y+sg*(r+12)} L{x0} {y+sg*(r+12)} L{x0+6} {y+sg*r}Z" fill="{d}"/>') + s
    return s


def missile_launcher(k, c, d):
    wheels = "".join(f'<rect x="{x-7}" y="{y}" width="14" height="9" rx="3" fill="#2a2e33" stroke="#111" stroke-width="2"/>' for x in (46, 66, 86, 106) for y in (36, 83))
    return (f'<rect x="30" y="40" width="88" height="50" rx="6" fill="#000" opacity=".25" transform="translate(3 4)"/>' + wheels +
            f'<rect x="30" y="42" width="90" height="44" rx="5" fill="#59614b" stroke="#232820" stroke-width="3"/>'
            f'<rect x="6" y="44" width="26" height="40" rx="6" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<rect x="8" y="50" width="6" height="28" rx="2" fill="#12202c" opacity=".8"/>'
            + missile_body(36, 124, 64, 8, c, d))


def missile_silo(k, c, d):
    return (f'<rect x="8" y="8" width="112" height="112" rx="12" fill="url(#s)" stroke="{d}" stroke-width="4"/>'
            + "".join(f'<path d="M{x} 12 l10 0 l-14 14 l-10 0z" fill="#f2c230" opacity=".9"/>' for x in (22, 46, 70, 94))
            + f'<circle cx="64" cy="66" r="40" fill="#14171b" stroke="{c}" stroke-width="6"/>'
            f'<circle cx="64" cy="66" r="31" fill="#2b3038"/>'
            f'<path d="M64 38 A28 28 0 0 0 36 66 H64Z" fill="url(#h{k})" stroke="{d}" stroke-width="3" transform="translate(-6 -6)"/>'
            f'<path d="M64 94 A28 28 0 0 0 92 66 H64Z" fill="url(#h{k})" stroke="{d}" stroke-width="3" transform="translate(6 6)"/>'
            f'<circle cx="64" cy="66" r="11" fill="#eef1f4" stroke="{d}" stroke-width="3"/><circle cx="64" cy="66" r="5" fill="{c}"/>')


UNITS = {"minesweeper": minesweeper, "minelayer": minelayer, "destroyer": destroyer, "cruiser": cruiser,
         "battleship": battleship, "submarine": submarine, "infantry": infantry, "tank": tank,
         "artillery": artillery, "coastal_gun": coastal_gun, "missile_launcher": missile_launcher,
         "missile_silo": missile_silo}


# ---------------- air units (top-down, facing east) ----------------
def poly(pts, k, d, sw=3.5):
    return f'<polygon points="{pts}" fill="url(#h{k})" stroke="{d}" stroke-width="{sw}" stroke-linejoin="round"/>'


def mirror(pts):
    return " ".join(f"{x},{128 - float(y):g}" for x, y in (p.split(",") for p in pts.split()))


def fighter(k, c, d):
    body = "M6 64 Q8 58 24 57 H92 Q116 60 124 64 Q116 68 92 71 H24 Q8 70 6 64Z"
    wing, tail = "50,60 34,16 58,16 88,59", "14,61 6,42 20,42 32,60"
    return (f'<path d="{body}" transform="translate(4 7)" fill="#000" opacity=".25"/>'
            + poly(wing, k, d) + poly(mirror(wing), k, d) + poly(tail, k, d) + poly(mirror(tail), k, d)
            + f'<path d="{body}" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<ellipse cx="92" cy="64" rx="11" ry="4" fill="#bfe3f7" stroke="{d}" stroke-width="2"/>'
            f'<rect x="3" y="60" width="9" height="8" fill="#222" stroke="{d}" stroke-width="2"/>')


def bomber(k, c, d):
    body = "M4 64 Q6 54 22 53 H100 Q122 56 126 64 Q122 72 100 75 H22 Q6 74 4 64Z"
    wing, tail = "54,57 70,6 90,6 78,57", "10,60 4,36 22,36 30,58"
    eng = "".join(f'<rect x="60" y="{y}" width="24" height="9" rx="4" fill="#3a4046" stroke="{d}" stroke-width="2"/>' for y in (18, 38, 71, 91))
    return (f'<path d="{body}" transform="translate(4 7)" fill="#000" opacity=".25"/>'
            + poly(wing, k, d) + poly(mirror(wing), k, d) + poly(tail, k, d) + poly(mirror(tail), k, d) + eng
            + f'<path d="{body}" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<ellipse cx="108" cy="64" rx="9" ry="4" fill="#bfe3f7" stroke="{d}" stroke-width="2"/>'
            f'<rect x="56" y="58" width="24" height="12" rx="2" fill="none" stroke="{d}" stroke-opacity=".5" stroke-width="2" stroke-dasharray="3 3"/>')


def rotor(cx, cy, r, d, a0=25):
    bl = "".join(f'<line x1="{cx - r*math.cos(math.radians(a)):.1f}" y1="{cy - r*math.sin(math.radians(a)):.1f}" x2="{cx + r*math.cos(math.radians(a)):.1f}" y2="{cy + r*math.sin(math.radians(a)):.1f}" stroke="#1b1e22" stroke-width="4" stroke-linecap="round" opacity=".85"/>' for a in (a0, a0 + 90))
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" opacity=".14"/><circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{d}" stroke-opacity=".4" stroke-width="2"/>'
            + bl + f'<circle cx="{cx}" cy="{cy}" r="5" fill="#3a4046" stroke="{d}" stroke-width="2"/>')


def attack_helicopter(k, c, d):
    pods = "".join(f'<rect x="54" y="{y}" width="24" height="8" rx="3" fill="#2a2e33" stroke="#111" stroke-width="2"/>' for y in (28, 92))
    return (f'<rect x="4" y="61" width="46" height="6" fill="{d}"/><circle cx="8" cy="64" r="8" fill="none" stroke="{d}" stroke-width="2" stroke-dasharray="3 3"/>'
            f'<ellipse cx="68" cy="70" rx="40" ry="13" fill="#000" opacity=".22"/>'
            f'<rect x="58" y="34" width="14" height="60" rx="3" fill="url(#s)" stroke="{d}" stroke-width="3"/>' + pods +
            f'<ellipse cx="66" cy="64" rx="40" ry="13" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<ellipse cx="98" cy="64" rx="11" ry="8" fill="#bfe3f7" stroke="{d}" stroke-width="2.5"/>' + rotor(64, 64, 52, d))


def transport_helicopter(k, c, d, cross=False):
    mark = ('<rect x="52" y="54" width="22" height="20" fill="#fff" stroke="#c0392b" stroke-width="2"/>'
            '<rect x="60" y="56" width="6" height="16" fill="#c0392b"/><rect x="54" y="61" width="18" height="6" fill="#c0392b"/>') if cross else ""
    return (f'<rect x="22" y="56" width="92" height="28" rx="12" fill="#000" opacity=".22"/>'
            f'<rect x="18" y="50" width="94" height="28" rx="12" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<path d="M6 60 H20 V68 H6Z" fill="{d}"/><ellipse cx="102" cy="64" rx="8" ry="9" fill="#bfe3f7" stroke="{d}" stroke-width="2.5"/>'
            + mark + rotor(36, 64, 32, d, 15) + rotor(88, 64, 30, d, 60))


def uav(k, c, d):
    body = "M6 64 Q10 60 30 60 H90 Q118 62 124 64 Q118 66 90 68 H30 Q10 68 6 64Z"
    wing = "46,60 52,10 68,10 72,60"
    return (poly(wing, k, d) + poly(mirror(wing), k, d)
            + f'<line x1="18" y1="62" x2="6" y2="42" stroke="{d}" stroke-width="5" stroke-linecap="round"/><line x1="18" y1="66" x2="6" y2="86" stroke="{d}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="{body}" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/><line x1="4" y1="52" x2="4" y2="76" stroke="{d}" stroke-width="3" stroke-dasharray="3 3"/>'
            f'<circle cx="104" cy="64" r="4.5" fill="#9fd0f0" stroke="{d}" stroke-width="2"/>')


# ---------------- support units ----------------
def wheels_row(xs, d):
    return "".join(f'<rect x="{x-7}" y="{y}" width="14" height="9" rx="3" fill="#2a2e33" stroke="#111" stroke-width="2"/>' for x in xs for y in (36, 83))


def medic(k, c, d):
    return (f'<rect x="12" y="44" width="106" height="46" rx="6" fill="#000" opacity=".22"/>' + wheels_row((28, 48, 96), d) +
            f'<rect x="10" y="40" width="76" height="48" rx="5" fill="#f4f6f8" stroke="{d}" stroke-width="3.5"/>'
            f'<rect x="84" y="42" width="32" height="44" rx="8" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<rect x="104" y="48" width="7" height="32" rx="2" fill="#12202c" opacity=".8"/>'
            f'<rect x="36" y="54" width="26" height="12" fill="#c0392b"/><rect x="43" y="47" width="12" height="26" fill="#c0392b"/>'
            f'<rect x="14" y="43" width="68" height="4" fill="{c}"/>')


def supply_truck(k, c, d):
    crates = "".join(f'<rect x="{x}" y="50" width="20" height="26" fill="#b9853f" stroke="#5c3d12" stroke-width="2.5"/><path d="M{x} 50 L{x+20} 76 M{x+20} 50 L{x} 76" stroke="#5c3d12" stroke-width="1.8"/>' for x in (16, 38, 60))
    return (f'<rect x="12" y="44" width="106" height="46" rx="6" fill="#000" opacity=".22"/>' + wheels_row((28, 48, 96), d) +
            f'<rect x="10" y="40" width="76" height="48" rx="4" fill="#59614b" stroke="#232820" stroke-width="3.5"/>' + crates +
            f'<rect x="10" y="40" width="76" height="6" fill="{c}"/>'
            f'<rect x="84" y="42" width="32" height="44" rx="8" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>'
            f'<rect x="104" y="48" width="7" height="32" rx="2" fill="#12202c" opacity=".8"/>')


def anti_air(k, c, d):
    tread = "".join(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+14}" stroke="#777" stroke-width="2"/>' for y0 in (32, 82) for x in range(24, 108, 6))
    tubes = "".join(f'<rect x="56" y="{y}" width="52" height="8" rx="2" fill="url(#s)" stroke="{d}" stroke-width="2.5"/><polygon points="108,{y} 118,{y+4} 108,{y+8}" fill="#c0392b" stroke="{d}" stroke-width="1.5"/>' for y in (42, 78))
    return (f'<rect x="18" y="30" width="94" height="68" rx="8" fill="#000" opacity=".22"/>'
            f'<rect x="16" y="30" width="94" height="16" rx="8" fill="#2a2e33" stroke="#111" stroke-width="2"/><rect x="16" y="82" width="94" height="16" rx="8" fill="#2a2e33" stroke="#111" stroke-width="2"/>' + tread +
            f'<rect x="22" y="44" width="82" height="40" rx="7" fill="url(#h{k})" stroke="{d}" stroke-width="3.5"/>' + tubes +
            f'<circle cx="44" cy="64" r="13" fill="url(#s)" stroke="{d}" stroke-width="3"/><path d="M34 64 H54 M44 54 V74" stroke="{d}" stroke-width="2"/><circle cx="44" cy="64" r="3" fill="{d}"/>')


def supply_ship(k, c, d):
    crates = "".join(f'<rect x="{x}" y="{y}" width="14" height="14" fill="{col}" stroke="#222" stroke-width="2"/>' for x, y, col in ((22, 50, "#b9853f"), (38, 50, "#6b7358"), (22, 66, "#6b7358"), (38, 66, "#b9853f"), (54, 58, "#b9853f")))
    crane = f'<circle cx="78" cy="64" r="6" fill="url(#s)" stroke="{d}" stroke-width="3"/><line x1="78" y1="64" x2="100" y2="44" stroke="#f2c230" stroke-width="5" stroke-linecap="round"/><line x1="78" y1="64" x2="100" y2="44" stroke="{d}" stroke-width="1.5"/>'
    return ship_base(k, d, 6, 118, 40, 28) + crates + crane + bridge(98, 64, 14, 14, d) + funnel(88, 64, 4, 5, d)


UNITS.update({"fighter": fighter, "bomber": bomber, "attack_helicopter": attack_helicopter,
              "transport_helicopter": transport_helicopter,
              "medevac_helicopter": lambda k, c, d: transport_helicopter(k, c, d, cross=True),
              "uav": uav, "medic": medic, "supply_truck": supply_truck, "anti_air": anti_air,
              "supply_ship": supply_ship})


# ---------------- terrain ----------------
def R(seed):
    return random.Random(seed)


def tile(inner, defs=""):
    return svg(inner, defs)


def waves(col, ys, op=.45, amp=9, w=3.5):
    return "".join(f'<path d="M-4 {y} q16 -{amp} 32 0 t32 0 t32 0 t32 0 t32 0" fill="none" stroke="{col}" stroke-width="{w}" opacity="{op}" stroke-linecap="round"/>' for y in ys)


def grad(id_, a, b, vertical=True):
    xy = 'x1="0" y1="0" x2="0" y2="1"' if vertical else 'x1="0" y1="0" x2="1" y2="1"'
    return f'<linearGradient id="{id_}" {xy}><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>'


def bg(id_):
    return f'<rect width="128" height="128" fill="url(#{id_})"/>'


def t_deep_sea():
    return tile(bg("g") + waves("#9fd0ff", (22, 56, 92, 120), .22, 10, 4) + waves("#04203f", (38, 74, 108), .3, 8, 4)
                + "".join(f'<circle cx="{r.randint(6,122)}" cy="{r.randint(6,122)}" r="{r.randint(1,3)}" fill="#fff" opacity=".18"/>' for r in [R(1)] for _ in range(14)),
                grad("g", "#0b2f5c", "#1b5c9e"))


def t_shallow():
    r = R(2)
    sand = "".join(f'<ellipse cx="{r.randint(10,118)}" cy="{r.randint(10,118)}" rx="{r.randint(14,28)}" ry="{r.randint(8,16)}" fill="#a8e6df" opacity=".4"/>' for _ in range(7))
    return tile(bg("g") + sand + waves("#ffffff", (30, 78, 112), .5, 7, 3), grad("g", "#46a9d6", "#6fcbe2"))


def t_coast():
    r = R(3)
    sand = "".join(f'<circle cx="{r.randint(4,124)}" cy="{r.randint(60,124)}" r="{r.random()*2+1:.1f}" fill="#b49a5a" opacity=".6"/>' for _ in range(40))
    return tile(bg("g") + '<path d="M0 0 H128 V50 q-16 14 -32 0 t-32 0 t-32 0 t-32 0 Z" fill="#3f9fd2"/>'
                '<path d="M0 50 q16 14 32 0 t32 0 t32 0 t32 0" fill="none" stroke="#fff" stroke-width="6" opacity=".85" stroke-linecap="round"/>'
                '<path d="M0 62 q16 14 32 0 t32 0 t32 0 t32 0" fill="none" stroke="#9a8450" stroke-width="3" opacity=".4"/>' + sand
                + waves("#fff", (22,), .4, 7, 3), grad("g", "#eadba5", "#d3bf84"))


def t_plains():
    r = R(4)
    fields = "".join(f'<rect x="{x}" y="{y}" width="60" height="58" fill="{col}" opacity=".5" transform="skewY(-4)"/>' for x, y, col in ((0, 6, "#8fbf5a"), (64, 12, "#a8cf6c"), (0, 66, "#a3cb68"), (64, 70, "#88b756")))
    tufts = "".join(f'<path d="M{x} {y} q-2 -9 -5 -11 M{x} {y} q1 -10 0 -13 M{x} {y} q3 -8 6 -10" stroke="#4f7d2c" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
                    for x, y in ((r.randint(8, 120), r.randint(14, 124)) for _ in range(26)))
    return tile(bg("g") + fields + tufts, grad("g", "#9dca66", "#7fae4c"))


def t_forest():
    r = R(5)
    pts = sorted(((r.randint(6, 122), r.randint(6, 122), r.randint(10, 15)) for _ in range(26)), key=lambda p: p[1])
    can = "".join(f'<circle cx="{x+2}" cy="{y+3}" r="{rad}" fill="#000" opacity=".25"/><circle cx="{x}" cy="{y}" r="{rad}" fill="#2d6430" stroke="#173b1a" stroke-width="2"/>'
                  f'<circle cx="{x-rad*.3:.1f}" cy="{y-rad*.3:.1f}" r="{rad*.55:.1f}" fill="#4a8f47"/><circle cx="{x-rad*.4:.1f}" cy="{y-rad*.4:.1f}" r="{rad*.2:.1f}" fill="#8fd08a" opacity=".7"/>' for x, y, rad in pts)
    return tile(bg("g") + can, grad("g", "#2a5a2d", "#1e4422"))


def t_hills():
    def cluster(cx, cy):
        return "".join(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{col}" stroke="#6b7640" stroke-width="2.5"/>' for rx, ry, col in ((44, 32, "#aab670"), (32, 23, "#b8c47e"), (20, 14, "#c7d28f"), (8, 6, "#d6dfa3")))
    return tile(bg("g") + cluster(40, 48) + cluster(92, 92) + '<ellipse cx="96" cy="30" rx="22" ry="16" fill="#aab670" stroke="#6b7640" stroke-width="2.5" opacity=".9"/>', grad("g", "#a1ad66", "#8e9a55"))


def peak(cx, cy, r):
    return (f'<polygon points="{cx},{cy-r} {cx-r},{cy+.8*r} {cx+.12*r},{cy+.8*r}" fill="#c9c3b6" stroke="#3d3a34" stroke-width="3" stroke-linejoin="round"/>'
            f'<polygon points="{cx},{cy-r} {cx+.12*r},{cy+.8*r} {cx+r},{cy+.8*r}" fill="#6f6a60" stroke="#3d3a34" stroke-width="3" stroke-linejoin="round"/>'
            f'<polygon points="{cx},{cy-r} {cx-.28*r},{cy-.45*r} {cx-.1*r},{cy-.52*r} {cx+.05*r},{cy-.3*r} {cx+.27*r},{cy-.46*r}" fill="#fff" opacity=".92"/>')


def t_mountain():
    r = R(6)
    rock = "".join(f'<circle cx="{r.randint(4,124)}" cy="{r.randint(4,124)}" r="{r.randint(1,3)}" fill="#5a564e" opacity=".5"/>' for _ in range(30))
    return tile(bg("g") + rock + peak(34, 76, 38) + peak(88, 78, 34) + peak(62, 50, 36), grad("g", "#9b958a", "#7c776c"))


def t_port():
    cont = "".join(f'<rect x="{12+i*20}" y="{y}" width="17" height="11" fill="{col}" stroke="#222" stroke-width="2"/>' for y, cols in ((84, ("#c0392b", "#2f6fb5", "#e0a526", "#3d8b4f", "#c0392b", "#2f6fb5")), (98, ("#2f6fb5", "#e0a526", "#c0392b", "#3d8b4f", "#e0a526", "#c0392b"))) for i, col in enumerate(cols))
    return tile(bg("g") + waves("#fff", (14, 40), .4, 7, 3)
                + '<rect x="0" y="56" width="128" height="72" fill="#bdb9ad"/><rect x="0" y="52" width="128" height="6" fill="#8b877b"/>'
                '<rect x="18" y="28" width="16" height="34" fill="#8a6a45" stroke="#3d2a14" stroke-width="3"/><rect x="82" y="28" width="16" height="34" fill="#8a6a45" stroke="#3d2a14" stroke-width="3"/>'
                + cont + '<rect x="4" y="68" width="120" height="6" fill="#f2c230" stroke="#7a5c0a" stroke-width="2"/>'
                '<rect x="10" y="64" width="5" height="14" fill="#f2c230" stroke="#7a5c0a" stroke-width="1.5"/><rect x="113" y="64" width="5" height="14" fill="#f2c230" stroke="#7a5c0a" stroke-width="1.5"/>'
                '<circle cx="26" cy="32" r="3" fill="#222"/><circle cx="90" cy="32" r="3" fill="#222"/>', grad("g", "#2f86bf", "#4aa3d6"))


def t_city():
    r = R(7)
    blocks = ""
    for i in range(3):
        for j in range(3):
            x, y = 8 + i * 40, 8 + j * 40
            col = r.choice(["#a7aab0", "#8d949e", "#b5b2aa", "#9aa0a8"])
            blocks += (f'<rect x="{x+2}" y="{y+3}" width="32" height="32" fill="#000" opacity=".25"/><rect x="{x}" y="{y}" width="32" height="32" fill="{col}" stroke="#454a52" stroke-width="2.5"/>'
                       f'<rect x="{x+5}" y="{y+5}" width="{r.randint(10,16)}" height="{r.randint(10,16)}" fill="{mix(col, "#ffffff", .35)}" stroke="#454a52" stroke-width="1.5"/>'
                       f'<rect x="{x+20}" y="{y+19}" width="8" height="8" fill="#6d737b"/>')
    trees = "".join(f'<circle cx="{x}" cy="{y}" r="3.5" fill="#3d7a42"/>' for x, y in ((44, 44), (84, 44), (44, 84), (4, 44), (84, 4)))
    return tile('<rect width="128" height="128" fill="#5d6065"/><line x1="0" y1="40" x2="128" y2="40" stroke="#f2e08a" stroke-width="1.5" stroke-dasharray="6 5"/>' + blocks + trees)


def t_tunnel():
    sleepers = "".join(f'<line x1="{52-(y-84)*.0}" y1="{y}" x2="{76}" y2="{y}" stroke="#4a3a28" stroke-width="3"/>' for y in range(92, 128, 8))
    return tile(bg("g") + peak(26, 40, 30) + peak(104, 44, 30)
                + '<path d="M18 128 V92 Q18 38 64 38 Q110 38 110 92 V128 Z" fill="#6f6a60" stroke="#3d3a34" stroke-width="4"/>'
                '<path d="M32 128 V94 Q32 54 64 54 Q96 54 96 94 V128 Z" fill="#b7b2a6" stroke="#3d3a34" stroke-width="4"/>'
                '<path d="M42 128 V96 Q42 66 64 66 Q86 66 86 96 V128 Z" fill="url(#tn)" stroke="#111" stroke-width="3"/>'
                '<line x1="54" y1="96" x2="48" y2="128" stroke="#8a8f96" stroke-width="3"/><line x1="74" y1="96" x2="80" y2="128" stroke="#8a8f96" stroke-width="3"/>'
                '<line x1="52" y1="108" x2="76" y2="108" stroke="#5a4630" stroke-width="3"/><line x1="50" y1="118" x2="78" y2="118" stroke="#5a4630" stroke-width="3"/>'
                '<rect x="54" y="42" width="20" height="9" fill="#f2c230" stroke="#3d3a34" stroke-width="2"/>',
                grad("g", "#8a8478", "#6f6a60") + '<radialGradient id="tn" cx=".5" cy=".7" r=".7"><stop offset="0" stop-color="#2a2e33"/><stop offset="1" stop-color="#000"/></radialGradient>')


def t_flooded():
    r = R(8)
    ripples = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{rx//3}" fill="none" stroke="#e6f2ee" stroke-width="2.5" opacity=".5"/>' for x, y, rx in ((r.randint(16, 112), r.randint(16, 112), r.randint(8, 16)) for _ in range(9)))
    tops = "".join(f'<circle cx="{x}" cy="{y}" r="9" fill="#2d6430" stroke="#173b1a" stroke-width="2"/><circle cx="{x-2}" cy="{y-2}" r="5" fill="#4a8f47"/><ellipse cx="{x}" cy="{y+10}" rx="12" ry="4" fill="none" stroke="#e6f2ee" stroke-width="2" opacity=".6"/>' for x, y in ((28, 34), (92, 90), (100, 28)))
    house = ('<rect x="30" y="84" width="22" height="18" fill="#b0614a" stroke="#4a2418" stroke-width="3"/><polygon points="28,84 41,72 54,84" fill="#8a3f2e" stroke="#4a2418" stroke-width="3"/>'
             '<ellipse cx="41" cy="104" rx="18" ry="4" fill="none" stroke="#e6f2ee" stroke-width="2" opacity=".6"/>')
    posts = "".join(f'<rect x="{x}" y="64" width="4" height="9" fill="#6b4a2a"/>' for x in (60, 70, 80))
    return tile(bg("g") + '<path d="M0 0 H128 V128 H0Z" fill="#6f8f7e" opacity=".55"/>' + ripples + tops + house + posts
                + '<path d="M-4 118 q16 -8 32 0 t32 0 t32 0 t32 0" fill="none" stroke="#fff" stroke-width="3" opacity=".4"/>', grad("g", "#79917a", "#5f7c6c"))


def t_flood_plain():
    r = R(9)
    cracks = "".join(f'<path d="M{x} {y} l{r.randint(-14,14)} {r.randint(6,14)} l{r.randint(-10,10)} {r.randint(4,10)}" stroke="#6b5636" stroke-width="2" fill="none" opacity=".7"/>' for x, y in ((r.randint(8, 120), r.randint(8, 100)) for _ in range(12)))
    reeds = "".join(f'<path d="M{x} {y} v-16 M{x+4} {y} v-12 M{x-4} {y} v-11" stroke="#6b8f3a" stroke-width="2.5" stroke-linecap="round"/>' for x, y in ((24, 112), (100, 110), (62, 120), (112, 70)))
    gauge = ''.join(f'<rect x="20" y="{34+i*10}" width="9" height="10" fill="{"#c0392b" if i%2 else "#fff"}" stroke="#222" stroke-width="1.5"/>' for i in range(6))
    warn = '<polygon points="94,26 112,58 76,58" fill="#f2c230" stroke="#3d2a00" stroke-width="3.5" stroke-linejoin="round"/><line x1="94" y1="36" x2="94" y2="48" stroke="#3d2a00" stroke-width="4" stroke-linecap="round"/><circle cx="94" cy="53" r="2.4" fill="#3d2a00"/>'
    return tile(bg("g") + cracks + reeds + '<rect x="4" y="4" width="120" height="120" rx="6" fill="none" stroke="#2f86bf" stroke-width="4" stroke-dasharray="10 7"/>'
                + '<path d="M26 92 q8 -6 16 0 t16 0 t16 0" fill="none" stroke="#4aa3d6" stroke-width="3" opacity=".6"/>' + gauge + warn, grad("g", "#b7a27a", "#9a8660"))


def coral(x, y, col, r):
    arms = "".join(f'<path d="M{x} {y} l{r*math.cos(a):.1f} {r*math.sin(a):.1f} m{-r*.35*math.cos(a)+r*.5*math.cos(a+.7):.1f} {-r*.35*math.sin(a)+r*.5*math.sin(a+.7):.1f}" stroke="{col}" stroke-width="4" stroke-linecap="round" fill="none"/>'
                   for a in [i * math.pi / 3 + .3 for i in range(6)])
    return arms + f'<circle cx="{x}" cy="{y}" r="5" fill="{col}" stroke="#7a2a3a" stroke-width="1.5"/>'


def t_coral():
    r = R(10)
    cols = ["#f06a7a", "#f2a33a", "#c06ad9", "#ff8fa3"]
    parts = "".join(coral(r.randint(14, 114), r.randint(14, 114), r.choice(cols), r.randint(10, 16)) for _ in range(10))
    brain = "".join(f'<circle cx="{x}" cy="{y}" r="{rad}" fill="#e88a6a" stroke="#8a3f2a" stroke-width="2.5"/><circle cx="{x}" cy="{y}" r="{rad*.55:.1f}" fill="none" stroke="#b5573a" stroke-width="2" stroke-dasharray="3 2"/>' for x, y, rad in ((30, 100, 13), (96, 38, 11), (70, 84, 9)))
    return tile(bg("g") + waves("#ffffff", (24, 74, 116), .4, 7, 3) + brain + parts, grad("g", "#34b9c4", "#5fd3d0"))


def t_sulphur():
    r = R(11)
    crystals = "".join(f'<polygon points="{x},{y-9} {x+8},{y-2} {x+5},{y+8} {x-6},{y+7} {x-9},{y-3}" fill="#f2e23a" stroke="#a8960a" stroke-width="2"/><polygon points="{x},{y-9} {x+8},{y-2} {x},{y+1} {x-9},{y-3}" fill="#fff7a8" opacity=".8"/>' for x, y in ((r.randint(16, 112), r.randint(16, 112)) for _ in range(8)))
    fumes = "".join(f'<circle cx="{x}" cy="{y}" r="{rad}" fill="#e6e08a" opacity=".28"/>' for x, y, rad in ((50, 54, 22), (62, 42, 16), (78, 58, 18), (68, 70, 14)))
    vent = '<circle cx="62" cy="62" r="11" fill="#3a3a1f" stroke="#1a1a0c" stroke-width="3"/><circle cx="62" cy="62" r="5" fill="#111"/>'
    bub = "".join(f'<circle cx="{x}" cy="{y}" r="{rad}" fill="none" stroke="#fffbd0" stroke-width="2" opacity=".8"/>' for x, y, rad in ((70, 44, 4), (56, 38, 3), (80, 54, 3), (48, 70, 4), (74, 78, 3)))
    skull = '<g transform="translate(92 96)" fill="#3a3a1f"><circle r="9"/><rect x="-5" y="6" width="10" height="6" rx="1"/><circle cx="-3.5" cy="-1" r="2.4" fill="#e6e08a"/><circle cx="3.5" cy="-1" r="2.4" fill="#e6e08a"/></g>'
    return tile(bg("g") + waves("#fffbd0", (20, 104, 118), .3, 7, 3) + crystals + fumes + vent + bub + skull, grad("g", "#9da33a", "#b7ba4a"))


def arrow_path(x, y, ln, col, w=5):
    return (f'<path d="M{x} {y} q{ln*.25} -10 {ln*.5} 0 t{ln*.5} 0" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round"/>'
            f'<polygon points="{x+ln} {y} {x+ln-10} {y-8} {x+ln-10} {y+8}" fill="{col}"/>')


def t_current():
    swirl = "".join(f'<circle cx="64" cy="64" r="{rad}" fill="none" stroke="#bfe6ff" stroke-width="3" opacity="{op}" stroke-dasharray="{da}"/>' for rad, op, da in ((12, .9, "30 12"), (22, .7, "40 14"), (32, .5, "50 16")))
    return tile(bg("g") + arrow_path(6, 22, 90, "#7cc4f5") + arrow_path(30, 104, 90, "#7cc4f5") + arrow_path(10, 64, 30, "#4aa3d6", 4) + arrow_path(88, 64, 30, "#4aa3d6", 4)
                + swirl + '<polygon points="76,60 90,64 76,68" fill="#bfe6ff" opacity=".9"/>', grad("g", "#0d3466", "#154f8c"))


def t_tank_trap():
    r = R(12)

    def hedgehog(x, y):
        return "".join(f'<line x1="{x-11*math.cos(a):.1f}" y1="{y-11*math.sin(a):.1f}" x2="{x+11*math.cos(a):.1f}" y2="{y+11*math.sin(a):.1f}" stroke="#2a2e33" stroke-width="6" stroke-linecap="round"/>'
                       f'<line x1="{x-11*math.cos(a):.1f}" y1="{y-11*math.sin(a):.1f}" x2="{x+11*math.cos(a):.1f}" y2="{y+11*math.sin(a):.1f}" stroke="#8d949e" stroke-width="2.5" stroke-linecap="round"/>' for a in (0.2, 1.25, 2.3))
    wire = '<path d="M4 64 q8 -10 16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0" fill="none" stroke="#555" stroke-width="2.5"/>'
    return tile(bg("g") + wire + "".join(hedgehog(x, y) for x, y in ((24, 28), (64, 26), (104, 30), (40, 100), (90, 98), (64, 64))), grad("g", "#a4b878", "#8aa05f"))


TERRAIN = {"deep_sea": t_deep_sea, "shallow_water": t_shallow, "coast": t_coast, "plains": t_plains, "forest": t_forest,
           "hills": t_hills, "mountain": t_mountain, "port": t_port, "city": t_city, "tunnel": t_tunnel,
           "flooded_zone": t_flooded, "flood_plain": t_flood_plain, "coral_reef": t_coral, "sulphur_zone": t_sulphur,
           "high_current": t_current, "tank_trap": t_tank_trap}


# ---- terrain added from the reference terrain study: river, bridge, road, camp, ruins, boulders; plus trench, airfield
def land_bg(rng):
    return grad("g", "#9dca66", "#7fae4c")


def t_trench():
    path = "M-6 34 L32 52 L20 84 L66 96 L92 70 L134 82"
    return tile(bg("g")
                + f'<path d="{path}" fill="none" stroke="#b9a37a" stroke-width="32" stroke-linejoin="round" stroke-dasharray="6 5" opacity=".9"/>'
                + f'<path d="{path}" fill="none" stroke="#2c2014" stroke-width="22" stroke-linejoin="round" stroke-linecap="round"/>'
                + f'<path d="{path}" fill="none" stroke="#5a4630" stroke-width="15" stroke-linejoin="round" stroke-linecap="round"/>'
                + f'<path d="{path}" fill="none" stroke="#8a6a45" stroke-width="6" stroke-linejoin="round" stroke-dasharray="4 3"/>'
                '<rect x="86" y="22" width="22" height="16" rx="3" fill="#7a6a4a" stroke="#3a2c1c" stroke-width="3"/>'
                '<circle cx="30" cy="110" r="5" fill="#b9a37a" stroke="#6e5f3f" stroke-width="2"/><circle cx="42" cy="114" r="5" fill="#b9a37a" stroke="#6e5f3f" stroke-width="2"/>', land_bg(0))


def t_river():
    p = "M70 -6 C30 30 100 50 60 84 S84 116 66 134"
    foam = f'<path d="{p}" fill="none" stroke="#fff" stroke-width="3" stroke-dasharray="10 9" opacity=".8" stroke-linecap="round"/>'
    trees = "".join(f'<circle cx="{x}" cy="{y}" r="8" fill="#2d6430" stroke="#173b1a" stroke-width="2"/><circle cx="{x-2}" cy="{y-2}" r="4" fill="#4a8f47"/>' for x, y in ((14, 30), (110, 22), (16, 100), (112, 108)))
    return tile(bg("g") + f'<path d="{p}" fill="none" stroke="#5f8f3a" stroke-width="46" stroke-linecap="round"/>'
                f'<path d="{p}" fill="none" stroke="#2f86bf" stroke-width="34" stroke-linecap="round"/>'
                f'<path d="{p}" fill="none" stroke="#6fcbe2" stroke-width="22" stroke-linecap="round"/>' + foam + trees, land_bg(0))


def t_bridge():
    planks = "".join(f'<line x1="{x}" y1="50" x2="{x}" y2="78" stroke="#3d3a34" stroke-width="1.5" opacity=".6"/>' for x in range(4, 128, 10))
    return tile(bg("g") + '<rect x="40" y="-4" width="48" height="136" fill="#5f8f3a"/><rect x="46" y="-4" width="36" height="136" fill="#2f86bf"/><rect x="52" y="-4" width="24" height="136" fill="#6fcbe2" opacity=".8"/>'
                '<path d="M64 0 V128" stroke="#fff" stroke-width="3" stroke-dasharray="10 9" opacity=".7"/>'
                '<rect x="-4" y="50" width="136" height="28" fill="#a19a8c" stroke="#3d3a34" stroke-width="4"/>' + planks +
                '<line x1="-4" y1="53" x2="132" y2="53" stroke="#4a463f" stroke-width="5"/><line x1="-4" y1="75" x2="132" y2="75" stroke="#4a463f" stroke-width="5"/>'
                '<rect x="38" y="46" width="52" height="36" fill="none" stroke="#3d3a34" stroke-width="3" opacity=".5"/>', land_bg(0))


def t_road():
    p = "M-6 98 C34 68 72 108 134 42"
    return tile(bg("g") + f'<path d="{p}" fill="none" stroke="#8d6f3e" stroke-width="30" stroke-linecap="round"/><path d="{p}" fill="none" stroke="#d9bb82" stroke-width="23" stroke-linecap="round"/>'
                f'<path d="{p}" fill="none" stroke="#f1e1b5" stroke-width="3" stroke-dasharray="9 8"/>'
                '<path d="M20 30 q-2 -9 -5 -11 M20 30 q1 -10 0 -13 M20 30 q3 -8 6 -10 M104 100 q-2 -9 -5 -11 M104 100 q1 -10 0 -13" stroke="#4f7d2c" stroke-width="2.5" fill="none" stroke-linecap="round"/>', land_bg(0))


def tent(x, y, rot, a="#d9c9a3", b="#b09a6a"):
    return (f'<g transform="translate({x} {y}) rotate({rot})"><rect x="-17" y="-13" width="34" height="26" fill="#000" opacity=".25" transform="translate(3 4)"/>'
            f'<rect x="-17" y="-13" width="34" height="13" fill="{a}" stroke="#4a3a22" stroke-width="2.5"/><rect x="-17" y="0" width="34" height="13" fill="{b}" stroke="#4a3a22" stroke-width="2.5"/>'
            f'<line x1="-17" y1="0" x2="17" y2="0" stroke="#4a3a22" stroke-width="2"/></g>')


def t_camp():
    fire = ('<circle cx="80" cy="92" r="11" fill="none" stroke="#6b6b6b" stroke-width="5" stroke-dasharray="5 3"/>'
            '<path d="M80 80 q8 8 2 14 q-3 4 -2 6 q-10 -4 -6 -12 q2 -4 6 -8Z" fill="#f28c1f"/><path d="M80 88 q4 5 0 9 q-5 -3 0 -9Z" fill="#ffe27a"/>')
    crates = "".join(f'<rect x="{x}" y="{y}" width="12" height="12" fill="#b9853f" stroke="#5c3d12" stroke-width="2"/>' for x, y in ((100, 66), (100, 80), (112, 74)))
    flag = '<line x1="22" y1="26" x2="22" y2="52" stroke="#3a3a3a" stroke-width="3"/><path d="M24 26 H46 L40 33 L46 40 H24Z" fill="#c0c0c0" stroke="#555" stroke-width="2"/>'
    return tile(bg("g") + '<rect x="6" y="6" width="116" height="116" rx="8" fill="none" stroke="#6b4a2a" stroke-width="3" stroke-dasharray="3 6" opacity=".8"/>'
                + tent(38, 76, -6) + tent(64, 50, 4) + tent(104, 38, 10) + fire + crates + flag, land_bg(0))


def t_ruins():
    towers = "".join(f'<rect x="{x}" y="{y}" width="20" height="20" fill="#7d7a70" stroke="#3d3a34" stroke-width="3"/><rect x="{x+5}" y="{y+5}" width="10" height="10" fill="#4a4842"/>' for x, y in ((14, 20), (94, 20), (14, 88), (94, 88)))
    walls = '<rect x="24" y="30" width="80" height="68" fill="#b6b09f" stroke="#8a867b" stroke-width="12" stroke-dasharray="30 10 16 14"/>'
    rubble = "".join(f'<polygon points="{x},{y-4} {x+5},{y} {x+2},{y+5} {x-4},{y+3}" fill="#8f8b80" stroke="#4a4842" stroke-width="1.5"/>' for x, y in ((50, 64), (70, 58), (60, 80), (86, 70), (40, 50)))
    moss = "".join(f'<circle cx="{x}" cy="{y}" r="4" fill="#4f8f3f" opacity=".85"/>' for x, y in ((34, 24), (104, 40), (60, 28), (20, 62), (98, 100)))
    return tile(bg("g") + walls + towers + rubble + moss + '<rect x="52" y="48" width="24" height="24" fill="#8a867b" stroke="#3d3a34" stroke-width="3" stroke-dasharray="14 6"/>', grad("g", "#a1ad66", "#8e9a55"))


def t_airfield():
    dash = '<line x1="8" y1="65" x2="120" y2="65" stroke="#fff" stroke-width="3" stroke-dasharray="12 9"/>'
    thr = "".join(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+10}" stroke="#fff" stroke-width="3"/>' for x in (8, 12, 116, 120) for y in (56,))
    hangar = ('<rect x="72" y="90" width="48" height="30" fill="#8d96a3" stroke="#3b4350" stroke-width="3"/>'
              + "".join(f'<line x1="{x}" y1="90" x2="{x}" y2="120" stroke="#6d7581" stroke-width="2"/>' for x in range(80, 120, 8)))
    sock = '<line x1="22" y1="26" x2="22" y2="42" stroke="#555" stroke-width="3"/><path d="M22 26 L46 30 L46 38 L22 42Z" fill="#f28c1f" stroke="#7a3d00" stroke-width="2"/>'
    return tile(bg("g") + '<rect x="-4" y="52" width="136" height="26" fill="#4b4f55" stroke="#2a2d31" stroke-width="3"/>' + dash + thr
                + '<rect x="12" y="88" width="46" height="32" fill="#5c6067" stroke="#2a2d31" stroke-width="3"/><path d="M58 88 V78" stroke="#4b4f55" stroke-width="10"/><circle cx="35" cy="104" r="10" fill="none" stroke="#f2c230" stroke-width="3"/>'
                + hangar + sock, land_bg(0))


def pent(x, y, r, rot):
    pts = " ".join(f"{x + r*math.cos(math.radians(rot + i*72)):.1f},{y + r*math.sin(math.radians(rot + i*72)):.1f}" for i in range(5))
    hi = " ".join(f"{x + r*.55*math.cos(math.radians(rot + i*72)) - 3:.1f},{y + r*.55*math.sin(math.radians(rot + i*72)) - 3:.1f}" for i in range(5))
    return f'<polygon points="{pts}" fill="#6f7f77" stroke="#33403a" stroke-width="3.5" stroke-linejoin="round"/><polygon points="{hi}" fill="#8a9b92" opacity=".6"/>'


def t_boulders():
    return tile(bg("g") + "".join(pent(x, y, r, rot) for x, y, r, rot in ((34, 38, 22, 10), (92, 50, 18, 40), (58, 92, 20, 22), (108, 100, 14, 5), (16, 98, 12, 30))), land_bg(0))


def t_barracks():
    roofs = "".join(f'<rect x="{x}" y="{y}" width="40" height="24" fill="#8a7b5c" stroke="#3d3320" stroke-width="3"/><line x1="{x}" y1="{y+12}" x2="{x+40}" y2="{y+12}" stroke="#3d3320" stroke-width="2"/>'
                    for x, y in ((14, 22), (14, 54), (62, 38)))
    flag = '<line x1="104" y1="18" x2="104" y2="60" stroke="#3a3a3a" stroke-width="3"/><path d="M106 18 H124 L118 25 L124 32 H106Z" fill="#c0c0c0" stroke="#555" stroke-width="2"/>'
    fence = '<rect x="6" y="10" width="116" height="108" rx="6" fill="none" stroke="#6b4a2a" stroke-width="3" stroke-dasharray="4 6"/>'
    return tile(bg("g") + fence + roofs + '<rect x="62" y="82" width="52" height="28" fill="#6e6a5a" stroke="#2a2a22" stroke-width="3"/>' + flag
                + '<circle cx="36" cy="100" r="6" fill="#4a4f3a" stroke="#1b1e22" stroke-width="2"/><circle cx="48" cy="104" r="5" fill="#4a4f3a" stroke="#1b1e22" stroke-width="2"/>', land_bg(0))


def t_training_camp():
    targets = "".join(f'<circle cx="{x}" cy="{y}" r="{r_}" fill="#f4f0e0" stroke="#c0392b" stroke-width="3"/><circle cx="{x}" cy="{y}" r="{r_*.5}" fill="#c0392b"/>' for x, y, r_ in ((30, 30, 14), (30, 64, 14), (30, 98, 14)))
    course = ('<path d="M54 96 H116" stroke="#6b4a2a" stroke-width="6"/><path d="M60 80 h14 v-12 h14 v12 h14 v-12 h14" fill="none" stroke="#6b4a2a" stroke-width="5"/>'
              '<rect x="60" y="30" width="52" height="26" fill="#5a6350" stroke="#232820" stroke-width="3"/><line x1="64" y1="43" x2="108" y2="43" stroke="#232820" stroke-width="2" stroke-dasharray="3 3"/>')
    return tile(bg("g") + '<rect x="6" y="6" width="116" height="116" rx="8" fill="#b9a37a" opacity=".35"/>' + targets + course
                + '<path d="M116 108 L100 118 L100 98Z" fill="#f2c230" stroke="#7a5c0a" stroke-width="2"/>', land_bg(0))


def t_barricade():
    sandbags = "".join(f'<ellipse cx="{x}" cy="{y}" rx="13" ry="7" fill="#c9b17a" stroke="#6e5f3f" stroke-width="2.5"/>' for x, y in
                       ((28, 52), (54, 52), (80, 52), (106, 52), (41, 64), (67, 64), (93, 64), (28, 76), (54, 76), (80, 76), (106, 76)))
    blocks = "".join(f'<rect x="{x}" y="38" width="12" height="52" fill="#8d96a3" stroke="#3b4350" stroke-width="3"/>' for x in (6, 110))
    wire = '<path d="M4 98 q8 -10 16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0" fill="none" stroke="#444" stroke-width="2.5"/>'
    return tile(bg("g") + '<rect x="-4" y="46" width="136" height="36" fill="#d9bb82" opacity=".55"/>' + sandbags + blocks + wire
                + '<path d="M18 22 L110 108 M110 22 L18 108" stroke="#2a2e33" stroke-width="5" opacity=".6"/>', land_bg(0))


TERRAIN.update({"barracks": t_barracks, "training_camp": t_training_camp, "barricade": t_barricade, "trench": t_trench, "river": t_river, "bridge": t_bridge, "road": t_road, "camp": t_camp,
                "ruins": t_ruins, "airfield": t_airfield, "boulders": t_boulders})


# ---------------- effects ----------------
def spikes(n, r1, r2, cx=64, cy=64):
    pts = []
    for i in range(n * 2):
        rad, a = (r1 if i % 2 == 0 else r2), math.pi * i / n
        pts.append(f"{cx + rad*math.cos(a):.1f},{cy + rad*math.sin(a):.1f}")
    return " ".join(pts)


RAYS = '<path d="M64 12 V34 M64 94 V116 M12 64 H34 M94 64 H116 M26 26 L42 42 M86 86 L102 102 M102 26 L86 42 M42 86 L26 102"/>'

EFFECTS = {
    "mine": svg(f'<g stroke="#222" stroke-width="8" stroke-linecap="round">{RAYS}</g><circle cx="64" cy="64" r="30" fill="url(#m)" stroke="#111" stroke-width="5"/><circle cx="53" cy="53" r="7" fill="#fff" opacity=".6"/>',
                '<radialGradient id="m" cx=".35" cy=".35" r=".8"><stop offset="0" stop-color="#7a828b"/><stop offset="1" stop-color="#23272c"/></radialGradient>'),
    "mine_revealed": svg(f'<g stroke="#8b0000" stroke-width="8" stroke-linecap="round">{RAYS}</g><circle cx="64" cy="64" r="30" fill="#c53030" stroke="#5c1a14" stroke-width="5"/><path d="M52 52 L76 76 M76 52 L52 76" stroke="#fff" stroke-width="7" stroke-linecap="round"/>'),
    "explosion": svg(f'<polygon points="{spikes(10, 60, 28)}" fill="#f6a21d" stroke="#b03a0a" stroke-width="4" stroke-linejoin="round"/><polygon points="{spikes(8, 38, 16)}" fill="#ffe27a"/><circle cx="64" cy="64" r="10" fill="#fff"/>'),
    "crater": svg('<circle cx="64" cy="64" r="52" fill="#5a4630" opacity=".55"/><circle cx="64" cy="64" r="42" fill="url(#c)" stroke="#2c2014" stroke-width="4"/>'
                  '<g fill="#3a2c1c"><circle cx="18" cy="40" r="4"/><circle cx="108" cy="80" r="5"/><circle cx="96" cy="22" r="3"/><circle cx="30" cy="104" r="4"/></g>',
                  '<radialGradient id="c" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#1a130b"/><stop offset="1" stop-color="#4a3a26"/></radialGradient>'),
    "ballistic_missile": svg('<path d="M4 64 L40 52 L40 76Z" fill="url(#f)"/><path d="M14 64 L38 57 L38 71Z" fill="#fff3b0"/>'
                             + missile_body(40, 122, 64, 9, "#d33", "#4a1010"), '<linearGradient id="f" x1="1" x2="0"><stop offset="0" stop-color="#ff9a1f"/><stop offset="1" stop-color="#ff3b1f" stop-opacity="0"/></linearGradient>'),
    "selected_ring": svg('<circle cx="64" cy="64" r="58" fill="none" stroke="#ffd23f" stroke-width="8" stroke-dasharray="18 10"/>'),
    "move_highlight": svg('<rect x="6" y="6" width="116" height="116" rx="10" fill="#4cd964" opacity=".35" stroke="#2a9d3f" stroke-width="5"/>'),
    "attack_highlight": svg('<rect x="6" y="6" width="116" height="116" rx="10" fill="#ff3b30" opacity=".35" stroke="#b01e16" stroke-width="5"/><circle cx="64" cy="64" r="22" fill="none" stroke="#b01e16" stroke-width="6"/><path d="M64 28 V100 M28 64 H100" stroke="#b01e16" stroke-width="6"/>'),
    "fog_overlay": svg('<rect width="128" height="128" fill="#0b1220" opacity=".62"/>'),
    "flood_warning": svg('<path d="M10 92 q13 -12 26 0 t26 0 t26 0 t26 0 V118 H10Z" fill="#2f86bf" stroke="#12466b" stroke-width="3"/>'
                         '<polygon points="64,12 100,74 28,74" fill="#f2c230" stroke="#3d2a00" stroke-width="5" stroke-linejoin="round"/>'
                         '<line x1="64" y1="30" x2="64" y2="54" stroke="#3d2a00" stroke-width="7" stroke-linecap="round"/><circle cx="64" cy="64" r="4.5" fill="#3d2a00"/>'),
}
def _arc_wave():
    return ('<path d="M44 36 Q30 52 44 68 M32 28 Q10 52 32 76 M84 36 Q98 52 84 68 M96 28 Q118 52 96 76" fill="none" stroke="#ffd23f" stroke-width="6" stroke-linecap="round"/>'
            '<path d="M64 44 L52 108 H76 Z" fill="#8d96a3" stroke="#2a2e33" stroke-width="4" stroke-linejoin="round"/><line x1="64" y1="44" x2="64" y2="108" stroke="#2a2e33" stroke-width="3"/>'
            '<circle cx="64" cy="40" r="7" fill="#ff3b30" stroke="#2a2e33" stroke-width="3"/>')


EFFECTS.update({
    "gas_cloud": svg("".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}" opacity=".42"/>' for x, y, r, col in (
        (44, 52, 30, "#c5d94a"), (80, 48, 28, "#d8e35a"), (64, 80, 32, "#a9c02e"), (30, 86, 22, "#b5c93a"), (98, 86, 24, "#c5d94a"), (62, 58, 22, "#8ea62a")))
        + '<g fill="none" stroke="#5f7a14" stroke-width="3" opacity=".7"><path d="M26 40 q10 -8 20 0"/><path d="M84 96 q10 -8 20 0"/><path d="M60 24 q10 -6 18 2"/></g>'),
    "gas_mask": svg('<path d="M18 58 Q18 14 64 14 Q110 14 110 58 Q110 98 82 112 H46 Q18 98 18 58Z" fill="#5a6350" stroke="#232820" stroke-width="5"/>'
                    '<path d="M18 50 Q64 38 110 50" fill="none" stroke="#2d3328" stroke-width="7"/><path d="M28 16 Q64 4 100 16" fill="none" stroke="#2d3328" stroke-width="6"/>'
                    '<circle cx="46" cy="58" r="15" fill="#10151a" stroke="#232820" stroke-width="5"/><circle cx="82" cy="58" r="15" fill="#10151a" stroke="#232820" stroke-width="5"/>'
                    '<circle cx="41" cy="52" r="5" fill="#9fd0f0" opacity=".85"/><circle cx="77" cy="52" r="5" fill="#9fd0f0" opacity=".85"/>'
                    '<rect x="50" y="92" width="28" height="30" rx="7" fill="#3a4036" stroke="#232820" stroke-width="5"/><g stroke="#232820" stroke-width="3"><line x1="56" y1="102" x2="72" y2="102"/><line x1="56" y1="108" x2="72" y2="108"/><line x1="56" y1="114" x2="72" y2="114"/></g>'
                    '<circle cx="64" cy="82" r="7" fill="#232820"/>'),
    "medic_cross": svg('<circle cx="64" cy="64" r="56" fill="#fff" stroke="#c0392b" stroke-width="7"/><rect x="52" y="24" width="24" height="80" rx="3" fill="#c0392b"/><rect x="24" y="52" width="80" height="24" rx="3" fill="#c0392b"/>'),
    "supply_crate": svg('<rect x="14" y="36" width="100" height="72" rx="4" fill="#b9853f" stroke="#5c3d12" stroke-width="6"/><path d="M14 36 L114 108 M114 36 L14 108" stroke="#5c3d12" stroke-width="4"/>'
                        '<rect x="14" y="62" width="100" height="14" fill="#f2c230" stroke="#5c3d12" stroke-width="3"/><g fill="#8a6a2a" stroke="#3d2a00" stroke-width="2"><rect x="38" y="14" width="12" height="22" rx="5"/><rect x="58" y="10" width="12" height="26" rx="5"/><rect x="78" y="14" width="12" height="22" rx="5"/></g>'),
    "alert_timer": svg('<rect x="54" y="8" width="20" height="12" rx="3" fill="#3a3a3a"/><line x1="64" y1="18" x2="64" y2="28" stroke="#3a3a3a" stroke-width="7"/><line x1="100" y1="34" x2="108" y2="26" stroke="#3a3a3a" stroke-width="8" stroke-linecap="round"/>'
                       '<circle cx="64" cy="74" r="46" fill="#fff" stroke="#222" stroke-width="7"/><path d="M64 74 L64 36 A38 38 0 0 1 102 74Z" fill="#ff3b30" opacity=".9"/>'
                       '<g stroke="#222" stroke-width="4" stroke-linecap="round"><line x1="64" y1="34" x2="64" y2="42"/><line x1="104" y1="74" x2="96" y2="74"/><line x1="64" y1="114" x2="64" y2="106"/><line x1="24" y1="74" x2="32" y2="74"/></g>'
                       '<line x1="64" y1="74" x2="86" y2="52" stroke="#222" stroke-width="6" stroke-linecap="round"/><circle cx="64" cy="74" r="6" fill="#222"/>'),
    "radio_wave": svg(_arc_wave()),
})

for _t, (_c, _d) in TEAMS.items():
    EFFECTS[f"hq_flag_{_t}"] = svg(
        f'<line x1="34" y1="14" x2="34" y2="116" stroke="#3a3a3a" stroke-width="7" stroke-linecap="round"/>'
        f'<path d="M38 18 H112 L96 42 L112 66 H38 Z" fill="{_c}" stroke="{_d}" stroke-width="5" stroke-linejoin="round"/>'
        f'<path d="M62 30 l5 11 12 1 -9 8 3 12 -11 -6 -11 6 3 -12 -9 -8 12 -1z" fill="{mix(_c, "#ffffff", .6)}"/>')


# ---------------- engineers and spy (top-down, facing east) ----------------
def diver(k, c, d):
    suit = mix(d, "#000000", .15)
    fins = poly("34,60 12,48 12,57 30,64", k, d, 3) + poly("34,68 12,80 12,71 30,64", k, d, 3)
    bubbles = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="#fff" stroke-width="2" opacity=".8"/>' for x, y, r in ((112, 46, 4), (118, 58, 3), (108, 36, 3)))
    return (f'<circle cx="64" cy="64" r="46" fill="#fff" opacity=".12"/><circle cx="64" cy="64" r="46" fill="none" stroke="#fff" stroke-width="3" stroke-dasharray="6 6" opacity=".55"/>' + fins +
            f'<line x1="76" y1="54" x2="110" y2="58" stroke="{suit}" stroke-width="7" stroke-linecap="round"/><line x1="76" y1="74" x2="110" y2="70" stroke="{suit}" stroke-width="7" stroke-linecap="round"/>'
            f'<ellipse cx="62" cy="64" rx="30" ry="13" fill="{suit}" stroke="{d}" stroke-width="3"/><rect x="40" y="56" width="26" height="16" rx="6" fill="#c9ced4" stroke="{d}" stroke-width="3"/>'
            f'<circle cx="88" cy="64" r="10" fill="url(#h{k})" stroke="{d}" stroke-width="3"/><ellipse cx="94" cy="64" rx="5" ry="7" fill="#9fd0f0" stroke="{d}" stroke-width="2"/>' + bubbles)


def digger(k, c, d):
    return (f'<ellipse cx="94" cy="94" rx="20" ry="11" fill="#6b4f2d" stroke="#3a2c1c" stroke-width="3"/><circle cx="82" cy="90" r="4" fill="#8a7050"/><circle cx="104" cy="98" r="3" fill="#8a7050"/>'
            + soldier(46, 60, c, d) +
            f'<line x1="62" y1="74" x2="108" y2="38" stroke="#8a6a45" stroke-width="6" stroke-linecap="round"/><line x1="62" y1="74" x2="108" y2="38" stroke="#4a3a22" stroke-width="1.5"/>'
            f'<path d="M104 28 L122 34 L116 52 L100 44 Z" fill="url(#s)" stroke="{d}" stroke-width="3" stroke-linejoin="round"/>')


def builder(k, c, d):
    planks = "".join(f'<rect x="64" y="{y}" width="52" height="9" rx="2" fill="#b9853f" stroke="#5c3d12" stroke-width="2.5"/><line x1="{x}" y1="{y}" x2="{x}" y2="{y+9}" stroke="#5c3d12" stroke-width="1.5"/>'
                     for y, x in ((84, 80), (96, 96), (72, 88)))
    return (planks + f'<g transform="translate(40 52) scale(1.45)"><rect x="-11" y="-6" width="8" height="12" rx="2" fill="#4a4f3a" stroke="#1b1e22" stroke-width="2"/>'
            f'<ellipse rx="6" ry="12" fill="{c}" stroke="{d}" stroke-width="2.5"/><circle cx="2" cy="0" r="7" fill="#f2c230" stroke="#7a5c0a" stroke-width="2.5"/>'
            f'<ellipse cx="3" cy="0" rx="4" ry="6" fill="#f7da6b"/></g>'
            f'<line x1="78" y1="46" x2="100" y2="30" stroke="#8a6a45" stroke-width="5" stroke-linecap="round"/><rect x="94" y="22" width="16" height="10" rx="2" fill="url(#s)" stroke="{d}" stroke-width="2.5" transform="rotate(-35 102 27)"/>')


def miner(k, c, d):
    return (soldier(44, 64, c, d) + small_mine(92, 64, 11) + f'<line x1="60" y1="70" x2="82" y2="66" stroke="#1b1e22" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M110 40 V58" stroke="#c0392b" stroke-width="3"/><path d="M110 40 L122 45 L110 50Z" fill="#c0392b"/>')


def spy(k, c, d):
    return (f'<ellipse cx="64" cy="64" rx="38" ry="32" fill="none" stroke="{c}" stroke-width="3" stroke-dasharray="4 5" opacity=".7"/>'
            f'<g transform="translate(60 64) scale(1.7)"><ellipse rx="6.5" ry="13" fill="#3a3f46" stroke="#111" stroke-width="2.2"/>'
            f'<rect x="-2" y="-14" width="6" height="4" rx="1" fill="{c}" stroke="{d}" stroke-width="1.5"/><circle cx="1" cy="0" r="5.5" fill="#2a2e33" stroke="#111" stroke-width="2"/>'
            f'<ellipse cx="1" cy="0" rx="8" ry="9" fill="none" stroke="#111" stroke-width="2"/><circle cx="3" cy="-1.5" r="1.2" fill="#fff"/><circle cx="3" cy="1.5" r="1.2" fill="#fff"/>'
            f'<line x1="3" y1="7" x2="14" y2="9" stroke="#111" stroke-width="2.5" stroke-linecap="round"/></g>')


UNITS.update({"diver": diver, "digger": digger, "builder": builder, "miner": miner, "spy": spy})


def rebel(k, c, d):
    # irregular militants: mismatched civilian clothes, an orange sash, loose scattered formation (not the team uniform)
    sash = "#e8851f"
    return ('<ellipse cx="64" cy="66" rx="50" ry="46" fill="#000" opacity=".12"/>' + soldier(84, 64, sash, "#5a3208") + soldier(44, 38, "#8a8f6a", "#3b3f2a") + soldier(50, 92, sash, "#5a3208")
            + '<path d="M20 64 L108 64" stroke="#e8851f" stroke-width="3" stroke-dasharray="5 7" opacity=".7"/>')


def commando(k, c, d):
    # regular special forces: one dark, hooded figure with a team-colour ring (a regular army, not a militia)
    return (f'<circle cx="64" cy="64" r="44" fill="none" stroke="{c}" stroke-width="5" stroke-dasharray="3 7"/>' + soldier(66, 64, "#23272c", d)
            + f'<rect x="30" y="58" width="16" height="12" rx="3" fill="#2f353c" stroke="{d}" stroke-width="2.5"/>')


def vip(k, c, d):
    # a principal: a civilian in a pale suit with a gold sash, shielded by a dashed ring
    return (f'<circle cx="64" cy="64" r="44" fill="#fff" opacity=".12"/><circle cx="64" cy="64" r="44" fill="none" stroke="#f2c230" stroke-width="5" stroke-dasharray="3 6"/>'
            + soldier(70, 64, "#eceff3", "#6b7280") + soldier(44, 78, "#f4d9e2", "#8a5a6c")
            + '<path d="M54 40 L92 88" stroke="#f2c230" stroke-width="5" opacity=".8"/>')


UNITS.update({"rebel": rebel, "commando": commando, "vip": vip})


def t_factory():
    stacks = "".join(f'<rect x="{x}" y="{y}" width="12" height="{h}" fill="#7d838c" stroke="#2a2e33" stroke-width="3"/><ellipse cx="{x+6}" cy="{y}" rx="9" ry="5" fill="#cfd4da" opacity=".7"/>' for x, y, h in ((22, 14, 36), (42, 20, 30), (62, 14, 36)))
    hall = '<rect x="12" y="52" width="104" height="52" fill="#8f9aa6" stroke="#2a2e33" stroke-width="4"/>' + "".join(f'<path d="M{x} 52 l16 -14 v14" fill="#6e7a87" stroke="#2a2e33" stroke-width="3"/>' for x in (16, 48, 80)) + '<rect x="52" y="80" width="24" height="24" fill="#3a4350" stroke="#1b1e22" stroke-width="3"/>'
    gear = '<circle cx="102" cy="30" r="14" fill="#f2c230" stroke="#7a5c0a" stroke-width="3"/><circle cx="102" cy="30" r="5" fill="#7a5c0a"/>'
    return tile(bg("g") + '<rect x="4" y="4" width="120" height="120" rx="6" fill="#b9c0c8" opacity=".25"/>' + stacks + hall + gear, land_bg(0))


TERRAIN["factory"] = t_factory


def wedge(cx, cy, a0, a1, r0, r1):
    p = lambda a, r: (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p(a0, r1), p(a1, r1), p(a1, r0), p(a0, r0)
    return f'<path d="M{x0:.1f} {y0:.1f} A{r1} {r1} 0 0 1 {x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f} A{r0} {r0} 0 0 0 {x3:.1f} {y3:.1f}Z" fill="#111"/>'


EFFECTS.update({
    "rumor": svg('<path d="M14 18 H114 Q122 18 122 26 V82 Q122 90 114 90 H62 L36 114 V90 H14 Q6 90 6 82 V26 Q6 18 14 18Z" fill="#e8edf2" stroke="#3a4756" stroke-width="6" stroke-linejoin="round"/>'
                 '<text x="64" y="76" font-size="62" text-anchor="middle" fill="#2f6fb5" stroke="#10294a" stroke-width="2" font-weight="700" font-family="sans-serif">?</text>'),
    "nuke_clue": svg('<circle cx="64" cy="64" r="54" fill="#f2c230" opacity=".12"/><circle cx="64" cy="64" r="54" fill="none" stroke="#f2c230" stroke-width="6" stroke-dasharray="14 9"/>'
                     '<text x="64" y="88" font-size="70" text-anchor="middle" fill="#f2c230" stroke="#3d2a00" stroke-width="3" font-weight="700" font-family="sans-serif">?</text>'),
    "nuke_site": svg('<circle cx="64" cy="64" r="56" fill="#f2c230" stroke="#3d2a00" stroke-width="6"/><circle cx="64" cy="64" r="9" fill="#111"/>'
                     + wedge(64, 64, -150, -90, 16, 40) + wedge(64, 64, -30, 30, 16, 40) + wedge(64, 64, 90, 150, 16, 40)
                     + '<circle cx="64" cy="64" r="52" fill="none" stroke="#111" stroke-width="3" stroke-dasharray="3 5"/>'),
})


# ---------------- tactical map symbols (original, not tied to any alliance) ----------------
# Friendly = blue rectangle, hostile = red diamond; the glyph inside shows the unit type.
def _ticks(n):
    return "".join(f'<path d="M{x} 4 V-14"/>' for x in ([0], [-8, 8], [-12, 0, 12])[n - 1])


_HULL = '<path d="M-22 4 H22 L14 16 H-14 Z"/>'
GLYPHS = {
    "infantry": '<path d="M-24 -16 L24 16 M-24 16 L24 -16"/>',
    "tank": '<ellipse rx="22" ry="12"/>',
    "artillery": '<circle r="6" fill="#111"/>',
    "coastal_gun": '<circle r="6" fill="#111"/><path d="M-18 16 H18"/>',
    "missile_launcher": '<path d="M0 20 V-20 M-10 -10 L0 -20 L10 -10"/>',
    "missile_silo": '<circle r="19"/><path d="M0 12 V-12 M-7 -5 L0 -12 L7 -5"/>',
    "anti_air": '<path d="M-22 14 Q0 -30 22 14"/>',
    "medic": '<path d="M0 -18 V18 M-18 0 H18" stroke="#c0392b" stroke-width="8"/>',
    "supply_truck": '<rect x="-20" y="-13" width="40" height="26"/><path d="M-20 0 H20"/>',
    "minesweeper": _HULL + '<circle cy="-8" r="7"/>',
    "minelayer": _HULL + '<circle cy="-8" r="5" fill="#111"/>',
    "destroyer": _HULL + _ticks(1),
    "cruiser": _HULL + _ticks(2),
    "battleship": _HULL + _ticks(3),
    "submarine": '<ellipse rx="22" ry="9"/><path d="M-6 -9 V-18 H6 V-9"/>',
    "supply_ship": _HULL + '<rect x="-8" y="-14" width="16" height="14"/>',
    "diver": '<path d="M-20 6 Q-10 -6 0 6 T20 6"/><circle cy="-10" r="5"/>',
    "digger": '<path d="M-14 16 L10 -12"/><path d="M4 -20 L20 -8 L12 0Z"/>',
    "builder": '<path d="M-20 16 H20 M-14 16 V-6 H14 V16 M-18 -6 H18"/>',
    "miner": '<circle r="9"/><path d="M0 -18 V-12 M0 12 V18 M-18 0 H-12 M12 0 H18"/>',
    "spy": '<ellipse rx="20" ry="10"/><circle r="5" fill="#111"/>',
    "rebel": '<path d="M-20 -14 L-6 14 M-6 -14 L8 14 M6 -14 L20 14" stroke-dasharray="1 9"/><circle cx="0" cy="-2" r="4" fill="#111"/>',
    "vip": '<path d="M0 -18 L5 -5 L19 -5 L8 4 L12 18 L0 10 L-12 18 L-8 4 L-19 -5 L-5 -5Z"/>',
    "commando": '<path d="M-22 14 L0 -18 L22 14Z"/><circle r="4" fill="#111"/>',
    "fighter": '<path d="M-18 14 L0 -16 L18 14"/>',
    "bomber": '<path d="M-18 10 L0 -18 L18 10 M-18 20 H18"/>',
    "attack_helicopter": '<circle r="16"/><path d="M-24 0 H24"/>',
    "transport_helicopter": '<circle cx="-11" r="10"/><circle cx="11" r="10"/>',
    "medevac_helicopter": '<circle cx="-11" r="10"/><circle cx="11" r="10"/><path d="M0 -6 V6 M-6 0 H6" stroke="#c0392b" stroke-width="5"/>',
    "uav": '<path d="M-14 8 L0 -12 L14 8Z"/><path d="M0 8 V22" stroke-dasharray="4 4"/>',
}


def tactical(unit_type, team):
    glyph = GLYPHS[unit_type]
    if team == "blue":
        frame = '<rect x="14" y="30" width="100" height="68" fill="#80c0ff" stroke="#111" stroke-width="5"/>'
        sc = 1.0
    else:
        frame = '<polygon points="64,6 122,64 64,122 6,64" fill="#ff8a80" stroke="#111" stroke-width="5"/>'
        sc = .78
    return svg(frame + f'<g transform="translate(64 64) scale({sc})" fill="none" stroke="#111" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">{glyph}</g>')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    written = []

    def put(name, text):
        (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
        written.append(name)

    for team, (c, d) in TEAMS.items():
        for name, fn in UNITS.items():
            PENDING.clear()
            body = fn(team, c, d)
            put(f"{name}_{team}", svg(body + "".join(PENDING), team_defs(team, c, d)))
    for name, fn in TERRAIN.items():
        put(name, fn().replace('id="g"', f'id="g_{name}"').replace("url(#g)", f"url(#g_{name})"))
    for name, text in EFFECTS.items():
        put(name, text)
    for team in TEAMS:
        for name in UNITS:
            put(f"sym_{name}_{team}", tactical(name, team))

    cells = "".join(
        f'<figure><div style="width:120px;height:120px;background:#5a6575">'
        + (OUT / f"{n}.svg").read_text(encoding="utf-8").replace('width="128" height="128"', 'width="120" height="120"', 1)
        + f"</div><figcaption>{n}</figcaption></figure>" for n in written)
    (OUT / "preview.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Icon preview</title>"
        "<style>body{font:12px sans-serif;background:#222;color:#ddd;display:flex;flex-wrap:wrap;gap:10px;padding:12px}"
        "figure{margin:0;text-align:center;width:130px}</style>" + cells, encoding="utf-8")
    print(f"Wrote {len(written)} icons to {OUT}")


if __name__ == "__main__":
    main()
