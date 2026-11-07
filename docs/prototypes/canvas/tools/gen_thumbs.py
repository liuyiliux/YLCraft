"""Generate local SVG placeholder stills for the canvas prototype.

Why: the prototype shows "photo" cards but used to render flat colour blocks.
These SVGs are abstract photographic compositions (gradient + light + geometry
+ silhouette + vignette) so cards read as frames, not as empty boxes.

Rules:
- No network, no third-party images, deterministic (fixed seed per file).
- Run from anywhere: python docs/prototypes/canvas/tools/gen_thumbs.py
- Output: docs/prototypes/canvas/assets/thumbs/{story,promo,char}-NN.svg
"""

import os
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "thumbs"
W, H = 360, 480

PALETTES = {
    "amber":  dict(c1="#6a4522", c2="#33200f", c3="#120c08", glow="#ffd39a", dark="#0c0806"),
    "blue":   dict(c1="#2b4055", c2="#16222e", c3="#0a1016", glow="#a9cbe8", dark="#070d12"),
    "violet": dict(c1="#4a334f", c2="#241a2c", c3="#100b14", glow="#efc3dc", dark="#0a0710"),
    "green":  dict(c1="#33452f", c2="#1a2719", c3="#0b110b", glow="#d7e6a8", dark="#060b06"),
    "wood":   dict(c1="#523529", c2="#291a14", c3="#120c09", glow="#f0bb82", dark="#0b0706"),
    "slate":  dict(c1="#314247", c2="#1a262a", c3="#0a1113", glow="#b6dcd4", dark="#060c0e"),
    "steel":  dict(c1="#2c3d47", c2="#18232b", c3="#090f13", glow="#c9e2ee", dark="#070d11"),
    "night":  dict(c1="#222c46", c2="#131a2b", c3="#080b14", glow="#ffd58a", dark="#060810"),
    "studio": dict(c1="#403934", c2="#231f1d", c3="#100e0d", glow="#e8d4bb", dark="#0b0908"),
}

# story: 12 frames of "autumn at the Summer Palace, Xiaolin, raking backlight"
STORY = [
    dict(pal="amber",  light=(0.70, 0.30), cols=5, gap=1, figs=[(0.55, 0.46, 1.00, "back")]),
    dict(pal="wood",   light=(0.28, 0.24), cols=0, gap=0, bokeh=1, figs=[(0.50, 0.36, 2.40, "front")]),
    dict(pal="violet", light=(0.80, 0.36), cols=2, gap=0, bokeh=1, figs=[(0.46, 0.44, 1.65, "threequarter")]),
    dict(pal="slate",  light=(0.62, 0.22), cols=3, steps=1, figs=[(0.52, 0.58, 0.62, "back")]),
    dict(pal="amber",  light=(0.34, 0.30), cols=0, win=1, figs=[(0.50, 0.48, 1.05, "front")]),
    dict(pal="wood",   light=(0.70, 0.20), cols=0, rail=1, bokeh=1, figs=[]),
    dict(pal="blue",   light=(0.50, 0.32), cols=6, gap=1, figs=[]),
    dict(pal="green",  light=(0.44, 0.18), cols=0, bokeh=1, figs=[(0.48, 0.36, 2.35, "threequarter")]),
    dict(pal="amber",  light=(0.52, 0.34), cols=2, gap=1, floor=1, figs=[(0.52, 0.50, 1.10, "back")]),
    dict(pal="slate",  light=(0.24, 0.62), cols=0, floor=1, steps=1, figs=[]),
    dict(pal="violet", light=(0.66, 0.28), cols=4, gap=0, figs=[(0.40, 0.47, 0.92, "profile"), (0.62, 0.47, 0.92, "front")]),
    dict(pal="amber",  light=(0.50, 0.26), cols=6, gap=1, figs=[(0.50, 0.62, 0.45, "back")]),
]

# promo: architecture / product, no cast at all
PROMO = [
    dict(pal="steel", light=(0.72, 0.22), glass=1, figs=[]),
    dict(pal="slate", light=(0.30, 0.34), glass=1, floor=1, figs=[]),
    dict(pal="blue",  light=(0.50, 0.30), cols=6, gap=1, figs=[]),
    dict(pal="steel", light=(0.62, 0.46), glass=1, diag=1, figs=[]),
    dict(pal="night", light=(0.38, 0.24), glass=1, bokeh=1, figs=[]),
    dict(pal="night", light=(0.60, 0.40), glass=1, bokeh=1, diag=1, figs=[]),
]

# character sheet: six distinct angles, no shot size / duration
CHAR = [
    dict(pal="studio", light=(0.50, 0.28), studio=1, figs=[(0.50, 0.44, 1.75, "front")]),
    dict(pal="studio", light=(0.44, 0.24), studio=1, figs=[(0.50, 0.28, 1.35, "full")]),
    dict(pal="studio", light=(0.58, 0.30), studio=1, figs=[(0.50, 0.44, 1.65, "threequarter")]),
    dict(pal="studio", light=(0.40, 0.26), studio=1, figs=[(0.50, 0.44, 1.55, "profile")]),
    dict(pal="studio", light=(0.54, 0.34), studio=1, figs=[(0.50, 0.44, 1.65, "back")]),
    dict(pal="studio", light=(0.50, 0.40), studio=1, figs=[(0.50, 0.46, 1.55, "top")]),
]


def esc(c):
    return c


def rect(x, y, w, h, fill, opacity=1.0, extra=""):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{fill}" opacity="{opacity:.2f}" {extra}/>')


def circle(cx, cy, r, fill, opacity=1.0):
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" opacity="{opacity:.2f}"/>'


def figure(fx, fy, scale, pose, p, rng):
    """Backlit human silhouette: rounded head, sloped shoulders, tapered waist.

    pose drives the angle so a character sheet does not look like six copies
    of the same icon. scale >= 1.8 is a close-up (body runs off the frame).
    """
    x, y = fx * W, fy * H
    s = scale
    dark, glow = p["dark"], p["glow"]
    close = s >= 1.8

    shoulder = {"profile": 16 * s, "threequarter": 17 * s,
                "top": 24 * s, "full": 24 * s}.get(pose, 20 * s)
    tilt = {"threequarter": 6 * s, "profile": 3 * s}.get(pose, 0.0)
    hx, hy = x, y
    hrx, hry = 11 * s, 13.5 * s
    if pose == "profile":
        hx += 3 * s
    if pose == "top":
        hry *= 0.72

    # head: rounded skull with a soft jaw, not a plain ellipse
    head_d = (f'M {hx-hrx:.1f} {hy:.1f} '
              f'C {hx-hrx:.1f} {hy-hry*1.55:.1f} {hx+hrx:.1f} {hy-hry*1.55:.1f} {hx+hrx:.1f} {hy:.1f} '
              f'C {hx+hrx*.92:.1f} {hy+hry*.78:.1f} {hx-hrx*.92:.1f} {hy+hry*.78:.1f} '
              f'{hx-hrx:.1f} {hy:.1f} Z')
    head = f'<path d="{head_d}" fill="{dark}" opacity=".9"/>'

    sh_y = hy + hry * 0.82
    body_h = (170 if pose == "full" else 150 if close else 96) * s
    waist = shoulder * 0.70
    neck = 5.5 * s
    ls, rs = hx - shoulder - tilt, hx + shoulder - tilt
    bottom = sh_y + body_h
    body = (f'M {hx-neck:.1f} {sh_y:.1f} '
            f'Q {hx-shoulder*.9:.1f} {sh_y-6*s:.1f} {ls:.1f} {sh_y+12*s:.1f} '
            f'Q {ls+4*s:.1f} {sh_y+body_h*.58:.1f} {hx-waist:.1f} {bottom:.1f} '
            f'L {hx+waist:.1f} {bottom:.1f} '
            f'Q {rs-4*s:.1f} {sh_y+body_h*.58:.1f} {rs:.1f} {sh_y+12*s:.1f} '
            f'Q {hx+shoulder*.9:.1f} {sh_y-6*s:.1f} {hx+neck:.1f} {sh_y:.1f} Z')

    # faint inner seams separate arms from torso
    seams = "".join(
        f'<path d="M {side*shoulder*.66+hx:.1f} {sh_y+9*s:.1f} '
        f'Q {side*shoulder*.82+hx:.1f} {sh_y+body_h*.5:.1f} '
        f'{hx+side*waist*.90:.1f} {bottom:.1f}" fill="none" stroke="{glow}" '
        f'stroke-width="{.8*s:.1f}" opacity=".13"/>'
        for side in (-1, 1)
    )

    hair = ""
    if pose in ("front", "threequarter", "full"):
        hair = (f'<path d="M {hx-hrx:.1f} {hy-3*s:.1f} Q {hx:.1f} {hy-hry*1.9:.1f} '
                f'{hx+hrx:.1f} {hy-3*s:.1f} Q {hx:.1f} {hy-hry*.9:.1f} '
                f'{hx-hrx:.1f} {hy-3*s:.1f} Z" fill="{dark}"/>')
    elif pose == "back":
        hair = circle(hx, hy - hry * .85, 7.5 * s, dark, .95)
    elif pose == "profile":
        hair = (f'<path d="M {hx-hrx*.9:.1f} {hy-2*s:.1f} '
                f'Q {hx-hrx*1.35:.1f} {hy-hry*1.25:.1f} {hx+hrx*.7:.1f} {hy-hry*.9:.1f} '
                f'L {hx-hrx*.9:.1f} {hy-2*s:.1f} Z" fill="{dark}"/>')
    elif pose == "top":
        hair = circle(hx, hy - 1 * s, 12.5 * s, dark, .95)

    rim = (f'<path d="{body}" fill="none" stroke="{glow}" '
           f'stroke-width="{1.3*s:.1f}" opacity=".34"/>'
           f'<path d="{head_d}" fill="none" stroke="{glow}" '
           f'stroke-width="{1.1*s:.1f}" opacity=".38"/>')
    return (f'<g><path d="{body}" fill="{dark}" opacity=".87"/>{seams}'
            f'{head}{hair}{rim}</g>')


def columns(n, p, rng):
    out = []
    for i in range(n):
        t = i / max(n - 1, 1)
        # two converging rows: left edge and right edge
        lx = 8 + t * 120
        rx = W - 8 - t * 120
        lw = 10 + t * 16
        op = 0.28 + t * 0.30
        out.append(rect(lx, 40 + t * 26, lw, H - 40, p["dark"], op))
        out.append(rect(rx - lw, 40 + t * 26, lw, H - 40, p["dark"], op))
    out.append(f'<path d="M 0 {H*0.72:.0f} L {W} {H*0.72:.0f}" stroke="{p["dark"]}" '
               f'stroke-width="1" opacity=".30"/>')
    return "".join(out)


def window_grid(p):
    out = []
    for i in range(1, 6):
        out.append(rect(i * 60 - 2, 55, 4, H - 110, p["dark"], .48))
    for j in range(1, 5):
        out.append(rect(20, 55 + j * 78, W - 40, 4, p["dark"], .48))
    out.append(rect(20, 55, W - 40, H - 110, p["glow"], .05))
    return "".join(out)


def glass_grid(p, rng, diag=False):
    out = []
    for i in range(1, 7):
        out.append(rect(i * 52 - 1, 20, 2, H - 40, p["glow"], .16))
    for j in range(1, 9):
        out.append(rect(10, 20 + j * 56, W - 20, 2, p["glow"], .13))
    for _ in range(9):
        out.append(rect(rng.uniform(12, W - 40), rng.uniform(30, H - 60),
                        rng.uniform(18, 46), rng.uniform(30, 70), p["glow"], .07))
    if diag:
        out.append(f'<path d="M 0 {H*0.78:.0f} L {W} {H*0.16:.0f} L {W} {H*0.30:.0f} '
                   f'L 0 {H*0.92:.0f} Z" fill="{p["glow"]}" opacity=".10"/>')
    return "".join(out)


def steps(p):
    out = []
    for i in range(4):
        y = H * 0.62 + i * 34
        out.append(f'<path d="M {20-i*12} {y:.0f} L {W-20+i*12} {y:.0f} '
                   f'L {W-20+i*12} {y+9:.0f} L {20-i*12} {y+9:.0f} Z" '
                   f'fill="{p["dark"]}" opacity=".34"/>')
    return "".join(out)


def rail(p):
    out = [rect(0, H * 0.70, W, 14, p["dark"], .72),
           rect(0, H * 0.86, W, 8, p["dark"], .50)]
    for i in range(7):
        out.append(rect(18 + i * 54, H * 0.70, 7, H * 0.18, p["dark"], .60))
    return "".join(out)


def floor_light(p):
    out = []
    for i in range(3):
        out.append(f'<path d="M {30+i*90} {H} L {110+i*90} {H*0.55:.0f} '
                   f'L {150+i*90} {H*0.55:.0f} L {80+i*90} {H} Z" '
                   f'fill="{p["glow"]}" opacity=".07"/>')
    return "".join(out)


def bokeh(p, rng, n=7):
    return "".join(circle(rng.uniform(20, W - 20), rng.uniform(40, H - 40),
                          rng.uniform(8, 26), p["glow"], rng.uniform(.05, .14))
                   for _ in range(n))


def svg_for(scene, seed, label):
    p = PALETTES[scene["pal"]]
    rng = random.Random(seed)
    lx, ly = scene.get("light", (0.5, 0.3))
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="360" height="480">',
        '<defs>',
        f'<linearGradient id="bg" x1="0" y1="0" x2="0.85" y2="1">'
        f'<stop offset="0" stop-color="{p["c1"]}"/><stop offset="0.52" stop-color="{p["c2"]}"/>'
        f'<stop offset="1" stop-color="{p["c3"]}"/></linearGradient>',
        f'<radialGradient id="lt" cx="{lx:.2f}" cy="{ly:.2f}" r="0.72">'
        f'<stop offset="0" stop-color="{p["glow"]}" stop-opacity=".62"/>'
        f'<stop offset="0.42" stop-color="{p["glow"]}" stop-opacity=".18"/>'
        f'<stop offset="1" stop-color="{p["glow"]}" stop-opacity="0"/></radialGradient>',
        '<radialGradient id="vig" cx="50%" cy="48%" r="72%">'
        '<stop offset="52%" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="100%" stop-color="#000" stop-opacity=".50"/></radialGradient>',
        '<filter id="soft" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="16"/></filter>',
        '</defs>',
        rect(0, 0, W, H, "url(#bg)"),
        rect(0, 0, W, H, "url(#lt)"),
    ]
    if scene.get("gap"):
        parts.append(rect(W * 0.40, H * 0.24, W * 0.20, H * 0.34,
                          p["glow"], .30, 'filter="url(#soft)"'))
        parts.append(rect(W * 0.43, H * 0.26, W * 0.14, H * 0.30, p["glow"], .22))
    if scene.get("cols"):
        parts.append(columns(scene["cols"], p, rng))
    if scene.get("glass"):
        parts.append(glass_grid(p, rng, scene.get("diag", False)))
    if scene.get("win"):
        parts.append(window_grid(p))
    if scene.get("steps"):
        parts.append(steps(p))
    if scene.get("floor"):
        parts.append(floor_light(p))
    if scene.get("bokeh"):
        parts.append(bokeh(p, rng))
    if scene.get("studio"):
        parts.append(circle(W / 2, H * 0.46, 132, p["glow"], .07))
        parts.append(f'<ellipse cx="{W/2:.0f}" cy="{H*0.90:.0f}" rx="120" ry="14" '
                     f'fill="{p["dark"]}" opacity=".28"/>')
    if scene.get("rail"):
        parts.append(rail(p))
    for fig in scene.get("figs", []):
        parts.append(figure(*fig, p, rng))
    parts.append(rect(0, 0, W, H, "url(#vig)"))
    parts.append(f'<title>{label}</title>')
    parts.append('</svg>')
    return "\n".join(parts)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    groups = [
        ("story", STORY, [s for s in [
            "她在长廊尽头回头", "眼圈红了的那一下", "侧身，肩线转过来", "从石阶走到廊下",
            "停在窗棂前", "手指划过木栏杆", "整条长廊的空镜", "抬头，睫毛在抖",
            "转身走进光里", "光影扫过地面", "两人并肩走过长廊", "走远，背影变小"]]),
        ("promo", PROMO, ["外立面全景", "天窗的光", "走廊纵深", "钢结构接缝",
                          "玻璃幕墙", "夜景灯光"]),
        ("char", CHAR, ["正面半身", "正面全身", "3/4 侧", "侧面", "背面", "俯视半身"]),
    ]
    n = 0
    offsets = {"story": 1000, "promo": 2000, "char": 3000}
    for prefix, scenes, labels in groups:
        for i, scene in enumerate(scenes):
            label = labels[i] if i < len(labels) else prefix
            path = OUT / f"{prefix}-{i+1:02d}.svg"
            # fixed seed: str.__hash__ is salted per process, so never use hash() here
            path.write_text(svg_for(scene, seed=offsets[prefix] + i, label=label),
                            encoding="utf-8")
            n += 1
    print(f"wrote {n} svg files to {OUT}")


if __name__ == "__main__":
    main()
