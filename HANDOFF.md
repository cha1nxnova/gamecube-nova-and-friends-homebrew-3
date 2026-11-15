# HANDOFF.md - read this first (for future Claude agents / humans)

## Project
**Pawtation**: rotates the user's legally acquired GameCube disc images across GC2SD SD cards (5 now, expandable) and hosts two
cat/dog chat pets. The user also owns a working Action Replay disc. Tone: cozy, cat/dog/furry-adjacent jokes + GameCube references.
Original characters only (Mochi = cat, Biscuit = dog). Never add copyrighted art or ROM/ISO downloads; the user supplies their own legal dumps.

## Decisions on record
- **2026-11-15, Swiss:** the owner chose a private themed fork with agent help (Path B). Terms in
  `docs/FORK_GUIDE.md` section 1. Never send anything upstream.
- **2026-11-15, cast:** the mascots are the owner's own characters Nova (serval) and Iggy (fennec fox); Duskie
  (golden jackal) is a recurring guest; Mochi and Biscuit are cameos. Canon: `docs/CHARACTERS.md`.
- **2026-11-15, look:** pink-forward theme driven by the mascots (`docs/DESIGN_SYSTEM.md`); characters appear as
  vector sticker sprites and low-poly renders, deliberately unlike the owner's other projects.
- **2026-11-15, After Dark:** an opt-in 18+ tier behind a one-time date-of-birth check. The repository ships
  innuendo-level banter only; nothing sexually explicit is authored here. `packs/` is the owner's own space.
- **2026-11-15, home:** this project is meant to live in its own private repository. Until that exists it sits
  in a `pawtation/` folder on a branch of the owner's Rounds repository; it shares nothing with Rounds.

## User priorities
- Top 5: Paper Mario TTYD, Animal Crossing (replaced Katamari Damacy, a PS2 game, at the user's request), Soulcalibur II, Mario Kart Double Dash, Chibi-Robo.
- Easy rotation, desktop app, timer, expandable to more cards, easy for future agents to modify.
- Wanted: Swiss fork + themed menus (NOT done, see Status).

## Start here (next agent)
1. `python scripts/doctor.py` - checks Python, tkinter, config, mounts, and whether the fork toolchain exists.
2. Read `docs/FORK_GUIDE.md` (**read the maintainer-policy section before touching Swiss source**).
3. Pick work from `agent_tasks/` (ready-made prompts, sized for cheaper models; `agent_tasks/SUPERVISOR.md` explains dispatch + review).
4. Run `python -m unittest discover -s tests` before and after every change.

## Layout
| Path | Role |
|---|---|
| `pawtation/core.py` | config/state, library scan (multi-disc aware), catalog match, `plan_rotation`, `sync_card` (progress, cancel, verify, manifest safety), card detection, boot card |
| `pawtation/discimage.py` | disc header reader for ISO/GCM/CISO/GCZ/RVZ containers (`READERS` table) |
| `pawtation/pets.py` | `PetBrain`: chat intents, jokes, fortunes, activities, quips, suggest, rank, rate, save report, wrapped |
| `pawtation/saves.py` | `.gci`/`.gcs` reader (header + comment text) + `PROGRESS_PARSERS` hook |
| `pawtation/patching.py` | BPS/IPS appliers, xdelta3 wrapper (`FORMATS` table) |
| `pawtation/plugins.py` | loads `plugins/*.py`; hooks for chat, planner score, events, commands, progress parsers |
| `pawtation/cli.py` / `gui.py` | CLI / tkinter app. Both only call the modules above |
| `data/catalog.json` | 651 games (79 hand-tagged seed + Wikipedia list; `scripts/build_catalog.py` regenerates, `scripts/import_ids.py` merges IDs) |
| `data/pets.json` | all pet content (jokes, fortunes, quips, ASCII art, activities) |
| `mods/`, `plugins/` | the user's per-game card files and plugins (`docs/MODDING.md`) |
| `config.json` (user, git-ignored) / `config.example.json` | settings; `state.json` = ratings, history, timer, pet stats. `PAWTATION_HOME` moves both |
| `docs/` | `MODDING.md` (start here to extend), `FORK_GUIDE.md` (Swiss), `RESEARCH_NOTES.md` (cited facts), `CATALOG_SOURCES.md`, `GUI_CHECKLIST.md` |
| `agent_tasks/` | prompts for sub-agents + supervisor playbook |
| `tests/` | `test_core` (original), `test_features` (sync safety, containers, patching, saves, chat, plugins, CLI end-to-end), `test_catalog`, `test_pets_content`, `test_gui` (skips without tkinter + display) |

## Rules of the road
1. Standard library only unless the user approves a dependency.
2. **Never delete files on an SD card that are not listed in the card's `.pawtation.json`.** Dry-run is the default for sync.
3. State/config schemas are additive: use `setdefault` so old files keep loading.
4. Keep UI-free logic in `core`; GUI/CLI stay thin.
5. Only write catalog `code4` values you can verify; leave them off otherwise (name matching still works).
6. Pet content is data: prefer editing `pets.json` over code. Placeholders: `{game} {card} {days}`.
7. Be honest in pet "progress" lines: do not claim story progress without a real parser.
8. The card manifest is untrusted input (it lives on removable media): every path from it goes through `core.card_path`.
9. Never overwrite a file on a card that the manifest does not list, even at a path Pawtation would use.
10. Only `.iso`/`.gcm` go onto cards (`core.LAUNCHABLE_EXTS`); Swiss refuses compressed containers.
11. Tests must set `PAWTATION_HOME` or pass their own cfg; never read or write the real `config.json`/`state.json`.

## How to...
- **Add a game:** append to `data/catalog.json` -> `{"key":"slug","title":"...","year":0,"developer":"","genres":[],"tags":[],"code4":"XXXX","aliases":[]}`.
  Tags drive pet quips (`furry`, `cozy`, `racing`, `horror`, `party`...). Add new tags to `pets.json -> tag_quips`.
- **Bulk-import titles:** write a small importer that reads a user-supplied `ID = Title` text file (e.g. a GameTDB export; format not verified) and merges into the catalog by `code4`.
- **Add an SD card:** add a key to `config.json -> cards` (`label`, `capacity_gb`, `mount`).
- **Change favorites:** edit `config.json -> pinned` (catalog keys).
- **Add a pet activity:** add to `pets.json -> activities` (needs `verb`, `needs`, `affection`, `energy`, lines per pet). GUI auto-adds a button.
- **Add a progress parser:** `saves.PROGRESS_PARSERS["G8ME"] = fn(raw_gci_bytes) -> str`, then surface it in `PetBrain.reply`.
- **Change rotation logic:** `core.game_score` and `plan_rotation`; add a test.

## Status (2026-11-15, second pass)
DONE + tested (automated, temp dirs): scan incl. multi-disc and CISO/GCZ/RVZ header reading, catalog matching (651 titles), planner,
safe sync (progress, cancel, verify, wrong-card guard, hostile-manifest guard, atomic copies), card auto-detect, mods overlay,
quips export, BPS/IPS patching, `.gci`/`.gcs` comment reading, pets chat, plugins, CLI end-to-end.
DONE, run under a virtual X display on Linux only: `gui.py` (see `docs/GUI_CHECKLIST.md`). Not run on Windows/macOS.
FIXED from the first pass: Soulcalibur II disc code was `GS2E` (that is Summoner); it is `GRSE`. Disc 2 of multi-disc games was
silently dropped. Compressed images were copied to cards although Swiss cannot start them. Chat regexes fired on substrings
("hi" in "this", "treat" in "treatment"). `state_of_collection` lines never displayed.
NOT DONE: Swiss fork/theme (user decision pending, see `docs/FORK_GUIDE.md` section 1); per-game progress parsers (TTYD layout is
documented but unverified against a real save); tags/genres for the 572 imported catalog titles; `.sav` save wrapper;
OS notifications; anything on real hardware.
UNVERIFIED on real hardware: multi-disc file naming (`disc1.iso`/`disc2.iso`, chosen from reading Swiss's pairing rule), the Swiss
cheat file path/format, whether memory-card emulation is usable with a GC2SD.

## Ideas backlog
Pet mini-game (fetch/guess-the-game), per-card themes, play-time tracking, OS reminder when rotation is due, TTYD progress
plugin once a sample save exists, tag the imported catalog titles, "convert to ISO" helper that drives Dolphin's command-line tool.
