# HANDOFF.md - read this first (for future Claude agents / humans)

## Project
**Pawtation** (version 2): rotates the owner's own legally acquired GameCube disc images across GC2SD SD cards (5 now,
expandable), with a desktop app and a CLI starring the owner's characters **Nova** (serval) and **Iggy** (fennec fox),
with **Duskie** (golden jackal) as a regular guest and ten rare cameo neighbours. The owner also has a working Action
Replay disc and runs stock Swiss (`docs/SWISS.md`). Never add copyrighted art or ROM/ISO downloads; the
owner supplies their own dumps.

Read next: `docs/SPEC_V2.md` (contracts between modules), `docs/CHARACTERS.md` (character canon).

## Decisions on record
- **2026-11-20, Swiss:** the owner chose **stock Swiss** and had the private themed fork (chosen 2026-11-15) removed,
  respecting the Swiss maintainers' request that AI tools not be used on their code. Rules: `docs/SWISS.md`.
  Hardware: Action Replay disc + GC2SD adapters with microSD cards. User guide: `docs/GAMECUBE_GUIDE.md`.
- **2026-11-15, cast:** the mascots are the owner's own characters Nova (serval) and Iggy (fennec fox); Duskie
  (golden jackal) is a recurring guest; Mochi and Biscuit are cameos. Canon: `docs/CHARACTERS.md`.
- **2026-11-15, look:** pink-forward theme driven by the mascots (`docs/DESIGN_SYSTEM.md`); characters appear as
  vector sticker sprites and low-poly renders, deliberately unlike the owner's other projects.
- **2026-11-15, After Dark:** an opt-in 18+ tier behind a one-time date-of-birth check. The repository ships
  innuendo-level banter only; nothing sexually explicit is authored here. `packs/` is the owner's own space.
- **2026-11-15, home:** this project lives in its own private repository
  (`gamecube-nova-and-friends-homebrew-3`). It started life in a folder of the owner's Rounds repository by
  mistake and shares nothing with Rounds.
- **2026-11-15, background cast:** eight new cameo neighbours (Pickle, Vesper, Tuft, Hazel, Sprout, Stilts, Flurry,
  The Refills) join Mochi and Biscuit. Original designs; see `docs/CHARACTERS.md` "Background cast".

## User priorities
- Top 5: Paper Mario TTYD, Animal Crossing (replaced Katamari Damacy, a PS2 game, at the user's request), Soulcalibur II, Mario Kart Double Dash, Chibi-Robo.
- Easy rotation, desktop app, timer, expandable to more cards, easy for future agents to modify.
- The characters front and centre (in the desktop app; Swiss stays stock).
- Get it launching on the real GameCube (`docs/GAMECUBE_GUIDE.md`).

## Start here (next agent)
1. `python scripts/doctor.py` (or `python -m pawtation doctor`): Python, tkinter, config, library, cards, cast,
   sprites, renders, theme file, After Dark locked/unlocked.
2. Read `docs/SPEC_V2.md` and `docs/CHARACTERS.md`. Before anything Swiss-related, read `docs/SWISS.md`.
3. Run `python -m unittest discover -s tests` before and after every change; GUI tests need tkinter and a display:
   `xvfb-run -a python3.12 -m unittest discover -s tests`.
4. `agent_tasks/README.md`: the version-1 task prompts are done and removed; it keeps the supervisor rules for
   delegating work (one task per helper with a file list, tests clean up their temp folders, report format).

## Layout
| Path | Role |
|---|---|
| `pawtation/core.py` | config/state, library scan (multi-disc aware), catalog match, `plan_rotation`, `sync_card` (progress, cancel, verify, manifest safety), card detection, boot card |
| `pawtation/cast.py` | the cast (`data/cast.json`), presence (who is home, meetups, cameo walk-ons with hours), scenes (`pick_scene`, `play`), content tiers and packs |
| `pawtation/afterdark.py` | the 18+ gate: `parse_date`, `unlock`, `lock`, `is_unlocked`. Stores only `{"unlocked", "confirmed_on"}` |
| `pawtation/hidden.py` | see docs/SPEC_V2.md section 9 |
| `pawtation/pets.py` | `PetBrain`: cast-driven chat intents, lines, scenes, jokes, fortunes, activities, card quips, suggest, rank, rate, save report, wrapped |
| `pawtation/sprites.py` | read-only loader for `assets/sprites` and `assets/renders` (manifests, frames, pack overrides); never raises |
| `pawtation/theme.py` | theme tokens from `data/theme.json` (built-in fallback), contrast checks, motion settings |
| `pawtation/gui.py` / `cli.py` | tkinter app / CLI. Both only call the modules above |
| `pawtation/discimage.py`, `saves.py`, `patching.py`, `plugins.py` | disc headers, `.gci`/`.gcs` reader, BPS/IPS/xdelta, `plugins/*.py` loader |
| `data/cast.json` | every character: name, species, pronouns, role, aliases, colours, optional cameo hours; presence weights |
| `data/pets.json`, `data/scenes.json` | all-ages lines and multi-character scenes |
| `data/afterdark/` | After Dark lines and scenes, read only while unlocked |
| `data/theme.json` | Blush (light) and Cosmic (dark) themes, type, spacing, radius, motion |
| `data/catalog.json` | 651 games (79 hand-tagged seed + Wikipedia list; `scripts/build_catalog.py` regenerates, `scripts/import_ids.py` merges IDs) |
| `assets/sprites/`, `assets/renders/` | committed outputs of the art pipeline (PNGs + `manifest.json`) |
| `art/` | dev-time art sources: `lib2d/` + `rigs/` (2D stickers, `art/build.py`), `lowpoly/` (3D renders). Never imported by the app. `art/out/` is scratch (git-ignored) |
| `packs/` | the owner's own content packs (git-ignored except `README.md`) |
| `mods/`, `plugins/` | per-game card files and plugins (`docs/MODDING.md`) |
| `config.json` (user, git-ignored) / `config.example.json` | settings; `state.json` = ratings, history, timer, character stats, presence, After Dark flag. `PAWTATION_HOME` moves both |
| `docs/` | `SPEC_V2.md`, `CHARACTERS.md`, `MODDING.md` (start here to extend), `DESIGN_SYSTEM.md`, `ART_PIPELINE.md`, `ART_LOWPOLY.md`, `GUI_CHECKLIST.md`, `SWISS.md`, `GAMECUBE_GUIDE.md`, `RESEARCH_NOTES.md`, `CATALOG_SOURCES.md` |
| `tests/` | `test_core`, `test_features` (sync safety, containers, patching, saves, chat, plugins, CLI end-to-end), `test_catalog`, `test_cast` (cast, presence, scenes, packs, After Dark lockdown), `test_afterdark` (After Dark through the real CLI), `test_pets_content`, `test_scenes_content`, `test_sprites`, `test_lowpoly`, `test_theme`, `test_release` (doctor, small regressions), `test_gui` (skips without tkinter + display) |

## Rules of the road
1. Standard library only at runtime (`pawtation/`, `scripts/`, `plugins/`), Python 3.9 compatible. Art tools may
   use dev-time extras (headless Chromium, Pillow) because their outputs are committed.
2. **Never delete files on an SD card that are not listed in the card's `.pawtation.json`.** Dry-run is the default for sync.
3. State/config schemas are additive: use `setdefault` so old files keep loading.
4. Keep UI-free logic in `core` / `cast` / `pets`; GUI and CLI stay thin.
5. Only write catalog `code4` values you can verify; leave them off otherwise (name matching still works).
6. Character content is data: prefer editing `pets.json` / `scenes.json` over code. Placeholders: `{game} {card} {days} {name}`.
7. Be honest in character "progress" lines: do not claim story progress without a real parser.
8. The card manifest is untrusted input (it lives on removable media): every path from it goes through `core.card_path`.
9. Never overwrite a file on a card that the manifest does not list, even at a path Pawtation would use.
10. Only `.iso`/`.gcm` go onto cards (`core.LAUNCHABLE_EXTS`); Swiss refuses compressed containers.
11. Tests must set `PAWTATION_HOME` or patch `core.CONFIG_PATH` / `STATE_PATH`; never read or write the real `config.json`/`state.json`.
12. **Cast ids are never hard-coded** in code. Code relies on roles (`cast.mains()`, `regulars()`, `cameos()`);
    adding a character is data plus art (`docs/MODDING.md`).
13. **After Dark:** off by default; only a date of birth checked once unlocks it, and the date is never stored,
    logged or echoed. While locked, After Dark files and packs are not even read. Card quips
    (`/pawtation/quips.txt`) are always all-ages. Chat can explain After Dark but never unlock it. Nothing sexually
    explicit is authored in this repository, for any tier. Unknown or missing pack ratings fail closed (After Dark).
14. **Art outputs are committed.** Change a rig or model, rebuild (`python3 art/build.py`, `python3 art/lowpoly/build.py`),
    commit the regenerated PNGs and manifests. The app must still start with every image missing (text fallback).
15. Characters: never change a species, palette or marking; no character addresses the player with pet names.
16. Swiss: stock releases only; no AI work on Swiss source and nothing sent upstream (`docs/SWISS.md`).

## How to...
- **Add a game:** append to `data/catalog.json` -> `{"key":"slug","title":"...","year":0,"developer":"","genres":[],"tags":[],"code4":"XXXX","aliases":[]}`.
  Tags drive quips (`furry`, `cozy`, `racing`, `horror`, `party`...). Add new tags to `pets.json -> tag_quips`.
- **Add a character, scene or pack:** `docs/MODDING.md` sections 4 and 5.
- **Add an SD card:** add a key to `config.json -> cards` (`label`, `capacity_gb` = the decimal size printed on the
  card, `mount`). The planner uses 95% of it until a sync measures the card (`state.json -> card_bytes`).
- **Change favorites:** edit `config.json -> pinned` (catalog keys).
- **Add an activity:** add to `pets.json -> activities` (`verb`, `needs`, `affection`, `energy`, lines per character). The GUI adds a button.
- **Add a progress parser:** `saves.PROGRESS_PARSERS["G8ME"] = fn(raw_gci_bytes) -> str`, then surface it in `PetBrain.reply`.
- **Change rotation logic:** `core.game_score` and `plan_rotation`; add a test.
- **Rebuild art:** `docs/ART_PIPELINE.md` (2D) and `docs/ART_LOWPOLY.md` (3D).

## Status (2026-11-15, version 2, end of wave 3)
**Done and tested (automated, temp dirs):** everything from version 1 (scan incl. multi-disc and CISO/GCZ/RVZ headers,
651-title catalog matching, planner, safe sync with progress/cancel/verify/wrong-card and hostile-manifest guards,
card auto-detect, mods overlay, quips export, BPS/IPS patching, `.gci`/`.gcs` reading, plugins, CLI end-to-end); the
cast engine (13 characters, presence weights, meetups, cameo walk-ons of 5-15 minutes with Vesper/Sprout hours,
scene matching); After Dark (gate, lockdown of every chat/scene/quip/CLI path, relock, card quips all-ages); real
dialogue for every character and scenes for every group; sprite sets for all 13 characters (mains/guest at 96, 192
and a 512 portrait; cameos at 96 and 192) plus props; low-poly Nova, Iggy, Duskie, the trio and the sync/disc renders;
the theme tokens with contrast checks; `scripts/doctor.py`; tidy `sync --go` output (the percentage line is cleared
before each "copy ..." line; dry-run output unchanged); game and tag scenes are reached while a cameo visits.
Test matrix at the end of wave 3: 342 tests; Python 3.13 and 3.11 without a display pass with 32 GUI tests skipped;
Python 3.12 under Xvfb passes all of them (run twice, no flakes). Test hygiene: every test removes the temp folders
it creates (`mktmp` helpers with `addCleanup`, `tearDownModule` in `test_gui`) and fake disc images are sparse; a full
Xvfb run leaves `/tmp` unchanged.
**Done, but only run under a virtual X display on Linux:** the version-2 desktop app (`gui.py`: stage, animations,
themes, meetup chips, After Dark gate). Stage sizing: up to three non-cameo characters use the 192 px stickers
whenever the stage is tall enough for the bubble and wide enough that no name tag overlaps or leaves the stage (a
visiting cameo stays at 96 px beside them); the compact 96 px stage only when they do not fit or four or more are
home. The Game column takes spare table width. See `docs/GUI_CHECKLIST.md`. The desktop app has only ever run under
Xvfb on Linux: not run on Windows or macOS, not seen on a real monitor at real DPI.
**Removed 2026-11-20:** the Swiss theme fork (`swiss_fork/`, `docs/BUILD_LOG.md`, `docs/SWISS_THEME_MAP.md`); it stays in git history only.
**Not done:** per-game progress parsers
(TTYD layout documented, unverified against a real save); tags/genres for the 572 imported catalog titles; `.sav` save
wrapper; OS notifications; printable card labels.
**Unverified on real hardware (nothing has run on real hardware yet):** anything on a real GameCube, GC2SD or SD card; multi-disc file naming
(`disc1.iso`/`disc2.iso`); the Swiss cheat file path/format; memory-card emulation with a GC2SD; which Action Replay file starts Swiss on the owner's disc (`autoexec.dol` or `SDLOADER.BIN`).

## Ideas backlog
Character mini-game (fetch/guess-the-game), per-card themes, play-time tracking, OS reminder when rotation is due, TTYD
progress plugin once a sample save exists, tag the imported catalog titles, "convert to ISO" helper that drives
Dolphin's command-line tool, printable card labels from the low-poly renders.
