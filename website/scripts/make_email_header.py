"""Builds website/static/img/email/header.gif: brand sky, drifting clouds, Nimbus bobbing and blinking, the wordmark.

Email clients drop CSS animation and SVG, so the motion is a GIF. Every layer moves a whole number of its own repeat
periods per loop, so the loop is seamless.

    python scripts/make_email_header.py raw.gif path/to/Baloo2.ttf 64
    gifsicle -O3 --lossy=30 raw.gif -o static/img/email/header.gif

Baloo 2 is the site font (SIL Open Font License): https://github.com/google/fonts/tree/main/ofl/baloo2
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(sys.argv[1])
FONT = sys.argv[2]
COLORS = int(sys.argv[3]) if len(sys.argv) > 3 else 96
W, H = 560, 150
S = 3  # supersampling
FRAMES, MS = 70, 90
BLUE, PURPLE, STROKE, INK, BLUSH = (28, 167, 236), (124, 92, 255), (13, 127, 191), (31, 41, 55), (255, 180, 168)


def sky():
    img = Image.new("RGB", (W * S, H * S))
    d = ImageDraw.Draw(img)
    for x in range(W * S):
        t = x / (W * S - 1)
        d.line([(x, 0), (x, H * S)], fill=tuple(round(a + (b - a) * t) for a, b in zip(BLUE, PURPLE)))
    return img


def puff(d, cx, cy, r, fill=255):
    """One fluffy cloud: a row of overlapping circles on a flat base."""
    for dx, dy, k in ((-1.1, 0.25, 0.62), (-0.45, -0.2, 0.85), (0.35, -0.35, 1.0), (1.1, 0.15, 0.7)):
        rr = r * k
        x, y = cx + dx * r, cy + dy * r
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)
    d.rounded_rectangle([cx - 1.6 * r, cy, cx + 1.7 * r, cy + 0.75 * r], radius=0.37 * r, fill=fill)


def layer_mask(shapes, period, shift):
    """A mask of clouds repeating every `period` px, moved `shift` px to the right."""
    m = Image.new("L", (W * S, H * S), 0)
    d = ImageDraw.Draw(m)
    for rep in range(-1, W // period + 2):
        for x, y, r in shapes:
            puff(d, (x + rep * period + shift) * S, y * S, r * S)
    return m


BACK = [(40, 24, 12), (112, 16, 8)]  # period 140: small, faint, high in the sky
BANK = [(20, 150, 34), (95, 142, 26), (165, 154, 38), (240, 146, 28)]  # period 280: the cloud bank along the bottom


def nimbus(blink, scale):
    """Nimbus from static/img/nimbus.svg, redrawn: three arcs closed by a flat base, blue outline, face."""
    k = scale * S
    size = (int(170 * k), int(130 * k))
    shape = Image.new("L", size, 0)
    d = ImageDraw.Draw(shape)
    for cx, cy, r in ((39, 72, 26), (73, 54, 34), (112, 69, 30.1)):
        d.ellipse([(cx - r + 5) * k, (cy - r + 5) * k, (cx + r + 5) * k, (cy + r + 5) * k], fill=255)
    d.polygon([(p[0] * k, p[1] * k) for p in ((43, 103), (45, 51), (109, 45), (125, 103))], fill=255)
    d.rectangle([0, 103 * k, size[0], size[1]], fill=0)  # flat base
    outline = shape.filter(ImageFilter.MaxFilter(2 * round(2.5 * k) + 1))
    img = Image.new("RGBA", size, STROKE + (0,))
    img.putalpha(outline)
    body = Image.new("RGBA", size, (255, 255, 255, 255))
    inner = shape.filter(ImageFilter.MinFilter(2 * round(2.5 * k) + 1))
    img.paste(body, (0, 0), inner)
    f = ImageDraw.Draw(img)
    o = 5 * k
    for ex in (64, 96):
        if blink:
            f.line([(ex - 5) * k + o, 66 * k + o, (ex + 5) * k + o, 66 * k + o], fill=INK, width=round(3 * k))
        else:
            f.ellipse([(ex - 5) * k + o, 61 * k + o, (ex + 5) * k + o, 71 * k + o], fill=INK)
    for bx in (54, 106):
        f.ellipse([(bx - 6) * k + o, 74 * k + o, (bx + 6) * k + o, 86 * k + o], fill=BLUSH)
    f.arc([70 * k + o, 68 * k + o, 90 * k + o, 83 * k + o], 20, 160, fill=INK, width=round(4 * k))
    return img


def font(px, weight):
    f = ImageFont.truetype(FONT, px * S)
    f.set_variation_by_name(weight)
    return f


def frame(i, base, title_font, tag_font):
    img = base.copy()
    white = Image.new("RGB", img.size, (255, 255, 255))
    t = i / FRAMES
    back = layer_mask(BACK, 140, (2 * i) % 140 - 140)  # 2 px a frame: one period per loop
    img.paste(white, (0, 0), back.point(lambda v: v * 0.3))
    # Nimbus and wordmark sit above the faint clouds, below the bank
    bob = math.sin(2 * math.pi * t) * 3.5
    blink = i % 70 in (40, 41)
    n = nimbus(blink, 0.62)
    shadow = Image.new("RGBA", n.size, (11, 59, 92, 0))
    shadow.putalpha(n.getchannel("A").point(lambda v: v * 0.25).filter(ImageFilter.GaussianBlur(4 * S)))
    pos = (int(22 * S), int((22 + bob) * S))
    img.paste(shadow, (pos[0] + 2 * S, pos[1] + 5 * S), shadow)
    img.paste(n, pos, n)
    d = ImageDraw.Draw(img)
    tx = 142 * S
    for dx, dy, col in ((0, 2 * S, (11, 59, 92)), (0, 0, (255, 255, 255))):
        d.text((tx + dx, 30 * S + dy), "Cloud for Kids", font=title_font, fill=col)
    for dy, col in ((S, (11, 59, 92)), (0, (240, 248, 255))):
        d.text((tx + 2, 78 * S + dy), "Learn the cloud, one step at a time", font=tag_font, fill=col)
    bank = layer_mask(BANK, 280, (4 * i) % 280 - 280)
    d2 = ImageDraw.Draw(bank)
    d2.rectangle([0, 147 * S, W * S, H * S], fill=255)  # merges into the white card below
    img.paste(white, (0, 0), bank)
    return img.resize((W, H), Image.LANCZOS)


def main():
    base = sky()
    title_font, tag_font = font(36, b"ExtraBold"), font(15, b"SemiBold")
    frames = [frame(i, base, title_font, tag_font) for i in range(FRAMES)]
    sample = Image.new("RGB", (W, H * 4))
    for k, i in enumerate((0, 17, 35, 52)):
        sample.paste(frames[i], (0, H * k))
    palette = sample.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=MS, loop=0, optimize=True, disposal=1)
    frames[0].save(OUT.with_name("header-still.png"), optimize=True)
    print(OUT, OUT.stat().st_size // 1024, "KB")


main()
