# Art pipeline (2D sprites)

Dev-time only. The app never imports `art/`; it reads committed PNGs through `pawtation/sprites.py`.

## How it works

```
art/rigs/<id>.py  --draw(pose)-->  SVG (512 x 512 viewBox)  --rasteriser-->  assets/sprites/<id>/<size>/<anim>_<nn>.png
                                                                     |
                                       art/build.py regenerates  assets/sprites/manifest.json
```

1. `art/build.py` imports every `art/rigs/*.py` (files starting with `_` are helpers) and checks its API with
   `lib2d.validate_rig`.
2. For each frame of each animation it calls `draw(pose)` and rasterises at 96 and 192 px, plus one 512 px
   `portrait_00.png` (skipped when the rig says `PORTRAIT = False`).
3. PNGs are losslessly recompressed when Pillow is installed (optional).
4. PNGs of frames the rig no longer has are deleted.
5. The manifest is always rebuilt from all rigs plus whatever character folders exist on disk, so
   `--only nova` never drops anyone. Output is deterministic: sorted keys, no timestamps. Rebuilding twice
   with the same rasteriser gave identical bytes (checked for `props`).

Commands:

```
python3 art/build.py                  # everything
python3 art/build.py --only nova iggy # some characters
python3 art/build.py --contact        # art/out/contact_<id>.png (all frames, light/dark, for eyeballing)
python3 art/build.py --check          # no rendering: is assets/ up to date? (exit 1 if not)
python3 art/build.py --list           # rigs, animations, frame counts
python3 art/build.py --renders        # also the low-poly renders (art/lowpoly)
```

## The rig API

A rig module defines:

| name | meaning |
| --- | --- |
| `CHAR_ID` | lowercase id, must equal the file name and the id in `data/cast.json` |
| `HEIGHT` | relative height, 0.2 to 1.0 (Nova 1.0); feet are always on the common baseline |
| `ANIMS` | `{name: anim(frames, fps, loop)}`; frames are pose dicts |
| `draw(pose) -> str` | one complete SVG document |
| `PORTRAIT` (optional) | pose for the 512 px still; `False` = none; default = first idle frame |
| `CAMEO = True` (optional) | cameo requirements; default comes from `role` in `cast.json` |
| `REQUIRED = {...}` (optional) | own animation requirements (`{}` = none; used by `props`) |

Required animations (SPEC_V2 section 5): main characters `idle` 4-8, `blink` 2-3, `talk` 2-4, `happy` 4-6,
`sleep` 2-4, `wave` 4-6, `look_left` 1, `look_right` 1, `special` 4-8. Cameos: `idle` 2-8 and `talk` 2-4.

Minimal rig:

```python
from lib2d import anim, circle, outlined, sticker, pose, tween, BASELINE, CX

CHAR_ID = "blobby"
HEIGHT = 0.4
INK = "#2b2d42"
BODY = "#8fd3a8"

def draw(p):
    squash = p.get("squash", 0.0)
    body = circle(CX, BASELINE - 60 + squash, 60, fill=BODY)
    return sticker(outlined(body, ink=INK, width=4), ink=INK)

ANIMS = {
    "idle": anim(tween(pose(squash=0), pose(squash=6), 4), fps=6, loop=True),
    "talk": anim([pose(squash=0), pose(squash=8)], fps=8, loop=True),
}
```

`sticker()` adds the die-cut look (shadow, pink edge, white border, ink contour). Helpers: `outlined`,
`detail` (paint that is ignored by the border), `clip`, `sparkle`, `heart`, `zzz`, `mix`, `blob`, `smooth`,
`tween`, `cycle`. See `art/rigs/nova.py` for the reference rig and `art/lib2d/*.py` docstrings.

## Add a character

1. Add the character to `data/cast.json` (cameos: `"role": "cameo"`) and canon in `docs/CHARACTERS.md`.
2. Write `art/rigs/<id>.py` (copy a rig as a starting point). Keep the colours in constants at the top.
3. `python3 art/build.py --only <id> --contact`, then look at `art/out/contact_<id>.png`.
4. `python3 -m unittest tests.test_sprites`.

## Add an animation

Add a key to `ANIMS`, rebuild with `--only <id>`. Names are lowercase letters, digits, underscores. A new
animation shows up in the manifest automatically; the loader serves it via `sprites.frames(id, name, size)`.

## Change a colour

Edit the colour constant in the rig (for example `GOLD` in `duskie.py`), then `python3 art/build.py --only
duskie`. Keep palettes in step with `docs/CHARACTERS.md`; species, palette and markings are canon.

## Replace art by hand or through a pack

* By hand: put your PNGs in `assets/sprites/<id>/<size>/<anim>_<nn>.png` (square, RGBA, 96 and 192, frames
  numbered from 00 without gaps), create an empty file `assets/sprites/<id>/HANDMADE` and optionally
  `assets/sprites/<id>/anims.json` such as `{"idle": {"fps": 6, "loop": true}}`. `build.py` then never renders
  into or deletes from that folder and builds the manifest entry from the PNGs it finds.
* Through a pack: `packs/<name>/sprites/<id>/<size>/<anim>_<nn>.png`. The caller passes the allowed pack
  directories: `sprites.frames(id, anim, size, pack_dirs=[...])`. Per frame, the first pack that has the file
  wins over the built-in one; After Dark packs are only passed when unlocked. Pack files may replace frames
  but cannot add animations the manifest does not list.

## Loader API (`pawtation/sprites.py`)

`load_manifest()`, `has(char)`, `characters()`, `available_sizes()`, `anim_info(char, anim)` ->
`{"fps", "loop", "count"}` or None, `frames(char, anim, size, pack_dirs=())` -> `[Path]`, `render(name)` ->
Path or None, `render_frames(name)` -> `([Path], fps)`. All take an optional `root=` (and the module-level
`ASSETS` can be patched). Nothing raises: missing or corrupt manifests and missing files give empty results.
`characters()` leaves out the `props` pseudo-character (`frames("props", "heart", 96)` works; props:
sparkle, heart, zzz, grilled_cheese, tea_mug, disc, sd_card, memory_card).

## Rasteriser requirements and fallbacks

Tried in this order: headless Chromium through Node + Playwright (`npm i -g playwright && npx playwright
install chromium`; one browser session for the whole job list), then `rsvg-convert`, `inkscape`, ImageMagick
(`magick` or `convert`, needs an SVG delegate). `--rasteriser NAME` forces one. Nothing found: a clear error;
the committed PNGs still work. Different rasterisers antialias differently, so a rebuild with another tool
changes bytes (not the art): stick to Chromium for committed output. The drop shadow is the only blur and
needs a rasteriser that supports SVG filters (Chromium, rsvg, Inkscape do). Pillow is optional (recompression).

## Measured (this machine, Chromium + Pillow)

* Full rebuild (`python3 art/build.py`, 4 rigs, 289 PNGs): about 18 s. `--only props`: under 3 s.
* Size on disk: nova 2.0 MB, iggy 2.4 MB, duskie 1.8 MB, props 0.13 MB (about 6.3 MB total).
* Tests: `python3 -m unittest tests.test_sprites` about 0.3 s; it needs no rasteriser.
