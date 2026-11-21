"""Build tool (not shipped): make packaging/pawtation.ico from Nova's own portrait. Needs Pillow.
Usage: python packaging/make_icon.py"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "assets" / "sprites" / "nova" / "512" / "portrait_00.png"
img = Image.open(src).convert("RGBA")
box = img.getbbox()                                   # trim the empty border so she fills the icon
if box:
    img = img.crop(box)
side = max(img.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
out = ROOT / "packaging" / "pawtation.ico"
square.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"wrote {out}")
