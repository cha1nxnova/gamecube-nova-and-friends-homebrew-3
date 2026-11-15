#!/usr/bin/env python3
"""Generate the art for the private, unofficial "Pawtation" theme of Swiss.

Original art only, made from this project's own assets and the "Cosmic" theme colours
(data/theme.json). Nothing here comes from Swiss.

Outputs (swiss_fork/art/out/):
  pawlogo.png      96x32  greyscale (L) mask: "Pawtation" wordmark + paw. Converted as I4
                   (white = opaque) and tinted hot pink in code. Replaces the 96x32 title logo.
  pawbackdrop.png  640x480 RGB, opaque: quiet star field in the Cosmic palette. Converted as
                   CMPR, drawn untinted (white vertex colour) at 640x480.
  pawmascot.png    256x64 RGBA strip: 4 idle frames of Nova's sticker sprite, 64x64 each,
                   transparent pixels black. Converted as RGB5A3 with nearest filtering and
                   drawn on Swiss's straight-alpha path, so no premultiplication is needed.
  preview.png      the three images on one sheet (for humans; not used by the build).

Usage: python3 swiss_fork/art/make_art.py [--font PATH] [--out DIR]
Requires Pillow. Deterministic: fixed random seed, fixed inputs. The font is the first one
found from FONT_CANDIDATES (or --font); its path is printed so a rebuild can match it.
"""
import argparse
import json
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SPRITES = os.path.join(ROOT, "assets", "sprites", "nova", "96")
RENDERS = os.path.join(ROOT, "assets", "renders")
THEME = os.path.join(ROOT, "data", "theme.json")

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

IDLE_FRAMES = (0, 2, 4, 6)   # of idle_00..07; 4 frames, played at about 4 fps
MASCOT_SIZE = 64
SEED = 2119


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cosmic():
    with open(THEME, encoding="utf-8") as f:
        t = json.load(f)["themes"]["dark"]
    return {k: hexrgb(t[k]) for k in ("bg", "surface", "stage", "ink", "primary", "stage_glow",
                                      "line_soft", "accent")}


def find_font(explicit):
    for p in ([explicit] if explicit else []) + FONT_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    sys.exit("make_art: no bold TrueType font found; pass --font PATH")


def paw(draw, cx, cy, r, fill):
    """A simple paw print: one main pad and four toes, centred on (cx, cy), radius scale r."""
    draw.ellipse((cx - r * 0.95, cy - r * 0.15, cx + r * 0.95, cy + r * 1.05), fill=fill)
    for dx, dy, s in ((-1.05, -0.55, 0.38), (-0.38, -1.05, 0.40), (0.38, -1.05, 0.40), (1.05, -0.55, 0.38)):
        x, y, rr = cx + dx * r, cy + dy * r, s * r
        draw.ellipse((x - rr, y - rr * 1.15, x + rr, y + rr * 1.15), fill=fill)


def make_logo(font_path):
    S = 8                                  # supersampling factor
    W, H = 96, 32
    big = Image.new("L", (W * S, H * S), 0)
    d = ImageDraw.Draw(big)
    paw(d, 12 * S, 17 * S, 7.2 * S, 255)
    text = "Pawtation"
    size = 40 * S
    while True:                            # largest size that fits x 24..95
        font = ImageFont.truetype(font_path, size)
        l, t, r, b = d.textbbox((0, 0), text, font=font)
        if r - l <= 71 * S and b - t <= 18 * S:
            break
        size -= S // 2
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    x = 24 * S + (71 * S - (r - l)) // 2 - l
    y = (H * S - (b - t)) // 2 - t + S
    d.text((x, y), text, font=font, fill=255)
    return big.resize((W, H), Image.LANCZOS)


def make_backdrop(c):
    W, H = 640, 480
    rnd = random.Random(SEED)
    img = Image.new("RGB", (W, H))
    px = img.load()
    top, bottom = c["stage"], c["surface"]
    for yy in range(H):
        f = yy / (H - 1)
        row = tuple(round(top[i] + (bottom[i] - top[i]) * f) for i in range(3))
        for xx in range(W):
            px[xx, yy] = row
    # soft plum glow low in the frame, and a fainter one top right
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((60, 300, 580, 640), fill=150)
    gd.ellipse((420, -120, 760, 160), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    img = Image.composite(Image.new("RGB", (W, H), c["stage_glow"]), img, glow)
    # ordered dither at RGB565 step sizes, so the CMPR/565 conversion bands less
    bayer = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    px = img.load()
    for yy in range(H):
        for xx in range(W):
            t = (bayer[yy & 3][xx & 3] + 0.5) / 16 - 0.5
            r, g, b = px[xx, yy]
            px[xx, yy] = (min(255, max(0, round(r + t * 8))), min(255, max(0, round(g + t * 4))),
                          min(255, max(0, round(b + t * 8))))
    # small stars: 1-2 px dots, mostly dim off-white, a few pink or blue
    d = ImageDraw.Draw(img)
    for _ in range(170):
        x, y = rnd.randrange(W), rnd.randrange(H)
        k = rnd.random()
        col = c["ink"] if k < 0.8 else (c["primary"] if k < 0.92 else c["accent"])
        a = rnd.uniform(0.25, 0.7)
        base = img.getpixel((x, y))
        mix = tuple(round(base[i] + (col[i] - base[i]) * a) for i in range(3))
        if rnd.random() < 0.15:
            d.rectangle((x, y, x + 1, y + 1), fill=mix)
        else:
            d.point((x, y), fill=mix)
    # a few larger sparkles from the project's own star render, kept faint
    star = Image.open(os.path.join(RENDERS, "star.png")).convert("RGBA")
    for _ in range(9):
        s = rnd.choice((10, 12, 14, 16))
        st = star.resize((s, s), Image.LANCZOS)
        alpha = st.getchannel("A").point(lambda v: v * 45 // 100)
        tint = Image.new("RGB", (s, s), c["ink"] if rnd.random() < 0.6 else c["primary"])
        img.paste(tint, (rnd.randrange(8, W - 24), rnd.randrange(8, H - 24)), alpha)
    return img


def make_mascot():
    frames = []
    for i in IDLE_FRAMES:
        f = Image.open(os.path.join(SPRITES, "idle_%02d.png" % i)).convert("RGBA")
        f = f.resize((MASCOT_SIZE, MASCOT_SIZE), Image.LANCZOS)
        frames.append(f)
    strip = Image.new("RGBA", (MASCOT_SIZE * len(frames), MASCOT_SIZE), (0, 0, 0, 0))
    for n, f in enumerate(frames):
        strip.paste(f, (n * MASCOT_SIZE, 0))
    # fully transparent pixels must be black (GX/RGB5A3 convention used by Swiss's art)
    px = strip.load()
    for y in range(strip.height):
        for x in range(strip.width):
            if px[x, y][3] == 0:
                px[x, y] = (0, 0, 0, 0)
    return strip


def preview(logo, backdrop, mascot, c):
    sheet = backdrop.copy().convert("RGBA")
    tinted = Image.new("RGBA", logo.size, c["primary"] + (255,))
    tinted.putalpha(logo)
    sheet.alpha_composite(mascot.crop((0, 0, MASCOT_SIZE, MASCOT_SIZE)), (20, 17))
    sheet.alpha_composite(tinted, (90, 22))
    sheet.alpha_composite(mascot, (40, 200))
    return sheet


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--font")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    c = cosmic()
    font = find_font(args.font)
    logo, backdrop, mascot = make_logo(font), make_backdrop(c), make_mascot()
    logo.save(os.path.join(args.out, "pawlogo.png"), optimize=False)
    backdrop.save(os.path.join(args.out, "pawbackdrop.png"), optimize=False)
    mascot.save(os.path.join(args.out, "pawmascot.png"), optimize=False)
    preview(logo, backdrop, mascot, c).save(os.path.join(args.out, "preview.png"))
    print("font:", font)
    for n in ("pawlogo.png", "pawbackdrop.png", "pawmascot.png"):
        im = Image.open(os.path.join(args.out, n))
        print("%-16s %dx%d %s" % (n, im.width, im.height, im.mode))


if __name__ == "__main__":
    main()
