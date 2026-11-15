# Pawtation v2 spec: cast, meetups, After Dark, art and theme contracts

Written by the supervising agent on 2026-11-15 so that several workers can build in parallel without
colliding. If you change a contract here, change this file in the same edit. `docs/CHARACTERS.md` is the
character canon; this file is the plumbing.

## 0. Ground rules (unchanged from HANDOFF.md, plus)

- Runtime is Python 3.9+ standard library only. Art build tools under `art/` may use extra dev-time tools
  (headless Chromium via Playwright, Pillow) because their **outputs are committed**; the app must run
  with nothing but the committed files, and must still start if every image is missing (text fallback).
- All shipped content is SFW unless it lives in the After Dark tier (section 4).
- No character addresses the player with pet names. No guilt, streaks, decay or nagging beyond one
  rotation reminder per app session.
- Never commit the owner's reference images, real names, or a birth date.
- Tests never touch the real `config.json` / `state.json` (pass a cfg/state, or patch `core.CONFIG_PATH`).

## 1. Cast (`data/cast.json`, `pawtation/cast.py`)

```json
{"version": 1,
 "characters": {
   "nova":    {"name": "Nova",    "species": "serval",        "pronouns": "he/him",  "role": "main",
               "aliases": ["nova", "serval", "cat", "kitty"], "color": "#2b2d42", "accent": "#f52fd2"},
   "iggy":    {"name": "Iggy",    "species": "fennec fox",    "pronouns": "any/all", "role": "main",
               "aliases": ["iggy", "fennec", "fox", "pup", "puppy"], "color": "#d2b48c", "accent": "#7582b5"},
   "duskie":  {"name": "Duskie",  "species": "golden jackal", "pronouns": "he/him",  "role": "guest",
               "aliases": ["duskie", "dusk", "jackal"], "color": "#ffd37c", "accent": "#79bff0"},
   "mochi":   {"name": "Mochi",   "species": "cat", "pronouns": "she/her", "role": "cameo", "aliases": ["mochi"]},
   "biscuit": {"name": "Biscuit", "species": "dog", "pronouns": "he/him",  "role": "cameo", "aliases": ["biscuit"]}},
 "presence": {
   "groups": {"nova+iggy": 58, "nova": 9, "iggy": 9, "duskie+iggy+nova": 10,
              "duskie+nova": 5, "duskie+iggy": 5, "cameo": 4},
   "min_minutes": 20, "max_minutes": 90}}
```

- Roles: `main` (the mascots), `guest` (rarer than mains, commoner than cameos), `cameo` (rare walk-ons that
  appear alongside whoever is home, never alone).
- A **group key** is the participant ids sorted alphabetically and joined with `+` (`"duskie+iggy+nova"`).
- **Presence** = who is "home" right now. Stored in `state["scene"] = {"who": [...ids], "until": ts,
  "manual": bool}`. When it expires, `cast.step(state, now, rng)` draws a new group by the weights above
  and returns the arrivals/departures so the UI can play hello/goodbye lines. At least one main is always
  home. `cast.present(state, now)` never mutates.
- **Meetups are also user-driven:** `cast.gather(state, ids, minutes=None, now=None)` sets the group by hand
  (any non-empty subset of the non-cameo cast: any one, any pair, or all three). Manual groups last
  `max_minutes` unless told otherwise, then presence goes back to random.
- Adding a character = one entry in `cast.json`, lines in `pets.json`, optional scenes and sprites. Nothing
  in code may hard-code a character id; code may only rely on roles.

## 2. Lines (`data/pets.json`) and scenes (`data/scenes.json`)

`pets.json` keeps its v1 shape, re-keyed by cast id:

- Per-character buckets: `greeting`, `idle`, `rotation_due`, `rotated`, `synced` (`{card}`), `ranked` (`{game}`),
  `study_break`, plus new `arrive` and `leave` (said when that character comes home / heads out) and `absent`
  (said *about* a character who is not home; `{name}` placeholder).
  Each bucket is `{"nova": [...], "iggy": [...], "duskie": [...], "mochi": [...], "biscuit": [...]}`; a missing
  character or bucket falls back gracefully (mains must have every bucket).
- `jokes`, `fortunes`: `[["Nova", "text"], ...]` (display name first, as in v1).
- `game_quips[key][id]`, `tag_quips[tag][id]` (`{game}`), `activities[name] = {verb, needs, affection, energy,
  "<id>": [...]}`; `characters[id]` = `{name, species, vibe, art, art_happy, art_sleep}` (ASCII art for the CLI:
  6 lines max, 22 columns max, same line count per mood).
- `state_of_collection` unchanged.

`scenes.json` holds multi-character exchanges (the "meetups"):

```json
{"version": 1, "scenes": [
  {"id": "cheese-drawer", "who": ["iggy", "nova"], "when": "any", "rating": "all", "weight": 1,
   "lines": [["nova", "I can hear the cheese drawer from here."],
             ["iggy", "It hasn't moved."],
             ["nova", "It could."]]}]}
```

- `who`: the exact participant set, sorted. Scenes exist for solo sets too (a character alone, thinking
  aloud, often about whoever is out).
- `when`: `any` | `arrive` | `leave` | `rotated` | `synced` | `due` | `night` (22:00-05:00 local) | `morning` |
  `game:<catalog key>` | `tag:<tag>`. The engine picks among scenes whose `who` equals the present set and
  whose `when` matches the moment; `any` scenes are the fallback pool.
- `lines`: 2 to 6 entries of `[speaker id, text]`; speaker must be in `who`, or `"*"` for a one-line stage
  direction. Text max 140 characters, plain text, placeholders `{game}` `{card}` only where `when` supplies them.
- `rating`: `"all"` or `"afterdark"` (section 4). `weight`: relative odds, default 1.
- Engine API: `cast.pick_scene(who, when, *, unlocked, rng, context=None) -> scene | None`,
  `cast.play(scene, context) -> list[str]` (formatted `"Name: text"` lines, `*` lines as `(text)`).

## 3. Engine behaviour (`pawtation/pets.py`, CLI)

- `PetBrain` becomes cast-driven. `duo(bucket, **fmt)` returns one line from **each character who is home**
  (cameos included only for `greeting`/`arrive`). `say(id, bucket, **fmt)` unchanged.
- Chat: a message is answered by the character it names (aliases above) if they are home; if they are not,
  someone who *is* home answers with an `absent` line. With no name, a home character is chosen at random
  (mains weighted over guest). New intents: "who's home / who is here", "invite <name>" / "call <name> over",
  "<name> go out" / "send <name> out", "everyone" / "get everyone together", "hang out" / "scene" (plays a scene
  for the present set), "after dark" (explains how to unlock; never unlocks from chat alone).
- State: `state["pets"][id] = {"affection", "energy"}` for every non-cameo character (v1 `mochi`/`biscuit`
  entries are left alone). `state["afterdark"]`, `state["scene"]` as specified.
- CLI: `chat` shows who is home and plays an arrival scene when presence changes; new commands
  `cast` (who is home; `--gather nova duskie`, `--everyone`, `--random`), `scene` (play one now),
  `afterdark` (status / unlock / `--lock`).
- Events from core (`rotated`, `synced`, `due`) play a matching scene when one exists, else the per-character lines.

## 4. After Dark (opt-in 18+ tier)  (`pawtation/afterdark.py`)

- Off by default. Unlocking asks for a date of birth **once**, checks age >= 18 against today's date, and
  stores only `state["afterdark"] = {"unlocked": true, "confirmed_on": "YYYY-MM-DD"}`. The birth date is never
  stored or logged. Once unlocked it never asks again (until `afterdark --lock` or the state file is removed).
  Under 18 or an invalid date: stays locked, says so plainly, no retry limit games.
- API: `afterdark.is_unlocked(state) -> bool`, `afterdark.unlock(state, birthdate: datetime.date,
  today=None) -> (ok: bool, message: str)`, `afterdark.lock(state)`, `afterdark.parse_date(text) -> date | None`
  (accepts `YYYY-MM-DD`, `MM/DD/YYYY`, `DD.MM.YYYY`).
- Content: `data/afterdark/pets.json` and `data/afterdark/scenes.json` (same schemas, every scene
  `"rating": "afterdark"`) plus any user pack under `packs/<name>/` (`pack.json` = `{"name", "rating"}`, optional
  `pets.json`, `scenes.json`, `sprites/`). Packs rated `afterdark` and the built-in After Dark files are loaded
  **only** when unlocked; `all`-rated packs always load. Loading merges lists (appends), never replaces.
- What ships in the built-in After Dark files: flirty, cheeky, innuendo-level banter between the three adults
  (think late-night sitcom). **Nothing sexually explicit is authored in this repository**, in text or art. The
  `packs/` folder is the owner's own space.
- When locked, After Dark content must be impossible to reach: not in chat, scenes, quips export, the GUI, or
  `/pawtation/quips.txt` on a card (card quips are always `all`-rated, even when unlocked).

## 5. Art contracts

```
art/                      dev-time sources (never imported by the app)
  lib2d/                  SVG rig helpers + rasteriser driver        (owner: 2D art)
  rigs/<id>.py            one parametric rig per character           (owner: 2D art)
  lowpoly/                pure-Python flat-shaded renderer + models  (owner: 3D art)
  build.py                python art/build.py [--only nova] [--renders] -> writes assets/
assets/
  sprites/manifest.json   see below
  sprites/<id>/<size>/<anim>_<nn>.png      RGBA, square, transparent background
  renders/<name>.png      low-poly stills / frame strips; renders/manifest.json
```

`assets/sprites/manifest.json`:

```json
{"version": 1, "sizes": [96, 192],
 "characters": {"nova": {"anims": {
     "idle":  {"fps": 6, "loop": true,  "frames": ["nova/{size}/idle_00.png", "..."]},
     "blink": {"fps": 12, "loop": false, "frames": ["..."]},
     "talk":  {"fps": 8, "loop": true,  "frames": ["..."]}}}}}
```

- Required animations for main and guest characters: `idle` (4-8 frames: breathing, an ear or tail move),
  `blink` (2-3), `talk` (2-4 mouth shapes), `happy` (4-6: bounce, eyes closed smile), `sleep` (2-4, with zzz),
  `wave` (4-6), `look_left`, `look_right` (1 frame each: eyes glance sideways), `special` (4-8; Nova: bite of
  grilled cheese with a cheese pull; Iggy: pushes glasses up / films with the camcorder; Duskie: big tail wag).
  Cameos need only `idle` (2) and `talk` (2).
- Sprites are front-facing, feet on a common baseline at 92% of the canvas height, centred, drawn so relative
  heights are right when two sprites of the same size sit side by side (Nova tallest, Iggy about 3/4, Duskie
  between). Frame paths use the literal `{size}` token.
- Runtime loader `pawtation/sprites.py` (stdlib, no tkinter import at module level):
  `load_manifest() -> dict`, `frames(char, anim, size) -> list[Path]`, `has(char) -> bool`,
  `available_sizes() -> list[int]`. Missing manifest or files -> empty results, never an exception.
- Low-poly renders: `assets/renders/manifest.json` = `{"version": 1, "renders": {"nova_bust": {"file":
  "nova_bust.png", "size": [512, 512]}, "nova_spin": {"frames": ["nova_spin_00.png", ...], "fps": 12,
  "size": [192, 192]}}}`.

## 6. Theme contract (`data/theme.json`, `pawtation/theme.py`)

- Pink-forward. `theme.json` = `{"version": 1, "default": "light", "themes": {"light": {...}, "dark": {...}},
  "type": {...}, "space": [...], "radius": {...}, "motion": {...}}`. Every theme defines the same semantic
  colour roles (at least): `bg`, `surface`, `surface_alt`, `stage`, `ink`, `ink_muted`, `line`, `primary`,
  `primary_ink` (text on primary), `primary_soft`, `accent`, `accent_ink`, `accent_soft`, `success`, `warning`,
  `danger`, `focus`, `selection`, `selection_ink`, `nova`, `iggy`, `duskie`.
- `pawtation/theme.py` (stdlib): `load(name=None) -> dict` (falls back to a built-in copy if the file is
  missing or broken), `names() -> list[str]`, `contrast(hex_a, hex_b) -> float` (WCAG ratio),
  `mix(hex_a, hex_b, t) -> str`. The GUI must take every colour from here; no hex literals in `gui.py`.
- Body text and controls meet WCAG AA (4.5:1 text, 3:1 large text and UI boundaries) in both themes; a test
  enforces it for the role pairs the GUI actually uses.

## 7. Who owns what in the first build wave

| Area | Files |
|---|---|
| Engine | `pawtation/cast.py`, `pawtation/afterdark.py`, `pawtation/pets.py`, `pawtation/cli.py`, `pawtation/core.py` (state defaults only), `data/cast.json`, `tests/test_cast.py`, `tests/test_afterdark.py`, fixes to existing tests |
| Content | `data/pets.json`, `data/scenes.json`, `data/afterdark/*`, `tests/test_pets_content.py`, `tests/test_scenes_content.py` |
| 2D art | `art/lib2d/`, `art/rigs/`, `art/build.py`, `assets/sprites/`, `pawtation/sprites.py`, `tests/test_sprites.py`, `docs/ART_PIPELINE.md` |
| 3D art | `art/lowpoly/`, `assets/renders/`, `tests/test_lowpoly.py`, `docs/ART_LOWPOLY.md` |
| Theme | `data/theme.json`, `pawtation/theme.py`, `tests/test_theme.py`, `docs/DESIGN_SYSTEM.md` |
| Later (second wave) | `pawtation/gui.py`, `tests/test_gui.py`, Swiss fork, printable labels |

## 8. Wave 3 addenda (2026-11-15)

- **Background cast.** `docs/CHARACTERS.md` "Background cast" defines ten cameo ids: `pickle`, `vesper`, `tuft`,
  `hazel`, `sprout`, `stilts`, `flurry`, `refills`, `mochi`, `biscuit`. Each gets a `cast.json` entry with
  `"role": "cameo"`, `name`, `species`, `pronouns`, `aliases`, `color`, `accent`, and optionally
  `"hours": [start, end]` (local 24-hour clock, end exclusive, may wrap past midnight: Vesper `[20, 6]`, Sprout
  `[7, 20]`). A cameo outside its hours is never drawn for a walk-on.
- **Presence weights:** `nova+iggy` 54, `nova` 9, `iggy` 9, `duskie+iggy+nova` 10, `duskie+nova` 5, `duskie+iggy` 5,
  `cameo` 8. `cameo` = the usual Nova + Iggy pair plus one random eligible cameo; a cameo visit lasts 5 to 15
  minutes, then the cameo leaves and the others stay.
- **Scenes and cameos.** A scene whose `who` has no cameo id matches when `who` equals the present *non-cameo*
  set (so a walk-on never silences the mains). A scene whose `who` includes a cameo matches when every id in
  `who` is present (subset match), and is preferred while that cameo is visiting. Cameos need per-character
  lines only for `greeting`, `idle`, `arrive`, `leave` (3 or more each) and may appear in jokes.
- **Cameo sprites:** sizes 96 and 192 only; required `idle` (2 to 4 frames) and `talk` (2 frames); optional
  `blink` and one `special`. Heights as listed in the bible, on the common baseline.
- **Sprite overrides from packs:** `sprites.frames(char, anim, size, pack_dirs=())` prefers
  `<pack>/sprites/<char>/<size>/<anim>_<nn>.png` from the given pack directories (the caller decides which packs
  are allowed; After Dark packs only when unlocked).
- **GUI settings** (in `config.json`, all optional): `gui_theme` (`light` | `dark`), `gui_reduce_motion` (bool; env
  `PAWTATION_REDUCE_MOTION=1` also works), `gui_sprite_size` (96 | 192 | `auto`).
- **After Dark stays as specified in section 4:** the repository ships innuendo-level banter only. No explicit
  text or art is authored here, by anyone, for any tier.
- **Swiss fork** lives in `swiss_fork/`: `README.md`, `patches/*.patch` (a `git format-patch` series over the
  pinned upstream tag), `art/` (generator script + its outputs), `apply.sh`. No upstream source files and no
  built binaries are committed.
