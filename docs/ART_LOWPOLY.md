# Low-poly renders ("papercraft" 3D)

Dev-time only: the app never imports `art/lowpoly`; it reads the PNGs in `assets/renders/` through
`assets/renders/manifest.json` (docs/SPEC_V2.md section 5). Everything here is pure Python standard
library: no numpy, no Pillow.

```
python3 art/lowpoly/build.py                      render everything into assets/renders/
python3 art/lowpoly/build.py --only iggy          one model module (or one job: --only iggy_spin)
python3 art/lowpoly/build.py --list               what would be rendered
python3 art/lowpoly/build.py --out DIR --sheet DIR   render elsewhere, plus a contact sheet per job
python3 -m unittest tests.test_lowpoly
```

`--only` renders just the selected jobs and **merges** their entries into the existing manifest
(other entries are kept; leftover frames of a re-rendered animation are removed). `--frames N`
changes the frame count written to the manifest, so use it with `--out` for quick looks.

## Package layout

| File | What it is |
|---|---|
| `art/lowpoly/mesh.py` | `Mesh` (one colour per triangle) and primitives: `icosphere`, `ellipsoid`, `box`, `cylinder`, `cone_between`, `loft` + `ring` / `facet_angles`, `tube`, `prism`, `polygon`, `star4`, `decal`; 2D outlines `ngon`, `rect`, `stroke`, `clip_halfplane`, `mirror2d`; transforms `translate`, `scale`, `rot_x/y/z`, `compose`. |
| `art/lowpoly/render.py` | `Camera` (perspective `fov` or `ortho`), `Lighting` / `house_lighting()`, `Shadow`, `Outline` / `house_outline()`, `Scene`, `render(scene, w, h, ss=3) -> Image`, `contact_sheet`. Back-face culling, z-buffer, supersampling with a box filter, one-pixel silhouette edge, soft ground shadow. |
| `art/lowpoly/png.py` | RGBA 8-bit PNG writer/reader (zlib + struct). |
| `art/lowpoly/pipeline.py` | `Job`, model discovery, multiprocessing across frames, manifest writing. |
| `art/lowpoly/models/*.py` | One module per model; each lists `JOBS`. Discovered automatically. |

Conventions: right-handed, y up, the model faces +z, +x is the viewer's right. Angles in degrees.
`compose(a, b, c)` applies `a` first. `Scene.shadow` is one `Shadow` or a list of them (group shots).

## Models and outputs

| Module | Jobs | Triangles (bust) |
|---|---|---|
| `nova.py` | `nova_bust` 512, `nova_icon` 256, `nova_spin` 24 x 192, `sync_loop` 24 x 256x192 | 1183 (1263 with sparkles) |
| `iggy.py` | `iggy_bust` 512, `iggy_icon` 256, `iggy_spin` 24 x 192 | 1639 |
| `duskie.py` | `duskie_bust` 512, `duskie_icon` 256, `duskie_spin` 24 x 192, `trio_busts` 1200x520 | 1165 (trio scene 4083) |
| `props.py` | `disc_spin`, `sd_card`, `star` | small |

All three busts share the camera setups (turntable: `target=(0, 0.13, 0), pitch=7, distance=17,
fov=17.9`), the lighting, and the ground line `BASE_Y = -2.25`, so they are to scale with each other
in every render: Iggy smallest (head scaled 0.86 about the neck), Duskie in between, Nova tallest
(ears). `trio_busts` puts them side by side at the same distance: Iggy left, Nova centre, Duskie right.

## How to model a character (the pattern all three busts follow)

1. **Head:** `loft` of about six `ring`s from chin to crown, built with
   `facet_angles([16, 52, 80, ...])` so a flat facet faces the camera and one wide flat facet sits
   under each eye. Colour per facet with `color(k, i)` (ring band `k`, segment `i`): for example a
   pale chin is `k == 0 and i in FRONT`.
2. **Muzzle:** a `cone_between` pointing forward, `warp`ed flatter, then `paint` by a region rule
   (`n[1] < 0.15` -> pale underside). Nose: a 20-triangle `icosphere` at the tip.
3. **Eyes:** raycast the head along the eye direction, take that facet's normal, and project
   `decal`s along it (white, iris, highlight, pupil, an `UNLIT` glint, a lid `stroke`).
   `clip_halfplane` makes lids. Projecting along the facet normal avoids distortion.
4. **Small markings:** more `decal`s (forehead dots, brow dots, freckles, saddle dashes). Use
   `layer=2+` for a patch on a patch. A decal raises `ValueError` if a point misses its target:
   that is how misplaced marks are caught; move them or wrap a scatter in `try/except`.
5. **Ears:** a `loft` of crescent rings (cup centre, pale edge, rim, two back points...) closed to
   a tip; colour by ring level and segment (pale cup, coloured backs and tips). Rotate out, tilt,
   seat on the head, and `mirrored("x")` for the other side.
6. **Fur tufts:** 3-sided `cone_between` spikes (fringe, cheek ruffs, chest ruff). 3 sides read as
   chunky paper folds; 4+ sides with `squash` looked like hedgehog spikes.
7. **Torso:** a `loft` of rings (tee), a darker band at the collar, sleeves as `cone_between`
   with a short fur arm stub. Prints are `decal`/`stroke` patches on the torso.
8. **Assembly:** `parts()` returns `(head, body)`; `build(turn, nod, tilt)` poses the head about
   `NECK_PIVOT`. Both are cached; treat results as read-only.
9. **Look at it** from 0, 35-45, 90, 145, 180 and 270 degrees (`--out DIR --sheet DIR` or a small
   script calling `render.render`) and iterate.

Specifics: Iggy's glasses are real geometry (a thick 12-sided annulus per lens via `_rim`, standing
`LENS_PROUD` off the face, a `tube` bridge and temple arms); the lens is two clipped sheen bands
plus a glint, so the eye stays visible (the renderer has no transparency). Duskie's tee is painted
fur above a low back neckline so the saddle shows on the nape and upper back.

## Lighting (`house_lighting()`)

Warm white key from the upper left front, soft cool fill from the right, a little warm bounce from
below, a hot-pink `#ff4fa3` rim from behind right (plus a faint pink edge glow on faces nearly
edge-on), and a small sheen so very dark fur stays readable. `house_outline()` darkens each face's
own colour by 30% for a one-pixel silhouette edge. Backgrounds are transparent.

## Measured render times

4-core container, Python 3.13, `ss=3`, full `build.py` (117 files): **5.6 s wall, 16 s CPU**.
Per job (CPU seconds, summed over frames): iggy_spin 3.0, duskie_spin 3.5, nova_spin 3.9,
sync_loop 4.9, each 512 px bust about 0.9-1.1, trio_busts (1200x520) 2.4.
