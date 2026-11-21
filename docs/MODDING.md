# Modding guide

Pawtation is built to be bent. There are several ways to change it, from "no code" to "new feature". Facts about
Swiss below come from `docs/RESEARCH_NOTES.md` (source files and line numbers are cited there).

| You want to... | Do this | Code needed |
|---|---|---|
| Ship cheat codes or other small files with a game | `mods/<game-key>/card/...` | none |
| Play a patched version of a game you own | `python -m pawtation patch` | none |
| Change what the characters say | `data/pets.json`, `data/scenes.json` | none |
| Add a character | `data/cast.json` + lines + (optional) a sprite rig | none in `pawtation/` |
| Add your own lines, scenes or sprites without touching the shipped files | a pack in `packs/<name>/` | none |
| Add behaviour (chat commands, planner rules, save readers) | a file in `plugins/` | a few lines of Python |
| Change the app itself | `pawtation/*.py`, see `HANDOFF.md` and `docs/SPEC_V2.md` | yes |

## 1. Per-game files that travel with the game (`mods/`)

    python -m pawtation mods --new "paper mario"      # makes mods/paper-mario-ttyd/card/
    python -m pawtation mods                           # lists what will be staged

Anything under `mods/<game-key>/card/` is copied to the same relative path on the SD card when that game rotates
onto a card, and removed when it rotates off. Rules that keep your cards safe:

- A mod file never replaces a file Pawtation did not put there (your `swiss/settings`, saves and so on). You get a warning instead.
- Mod files cannot write into the games folder or over the card's `.pawtation.json`.
- Everything staged is tracked in the card manifest, so it is cleaned up exactly.

**Swiss cheats.** Swiss reads `swiss/cheats/<6-character disc ID>.txt` (for example `swiss/cheats/G8ME01.txt`); press Y
on the game's screen to pick codes. The file is a cheat name on one line followed by plain `XXXXXXXX XXXXXXXX`
code lines, then a blank line before the next cheat. `python -m pawtation scan` shows each game's disc ID.
So: `mods/paper-mario-ttyd/card/swiss/cheats/G8ME01.txt`. Dolphin's `[Gecko]` codes use the same pair format
(drop the `$` from the name line); encrypted Action Replay codes were not found to be supported.

## 2. Patched games (`patch`)

    python -m pawtation patch "D:\GameCube\Game (USA).iso" cool-mod.bps
    python -m pawtation patch game.iso mod.xdelta --out "D:\GameCube\Game - Cool Mod.iso"

Writes a patched **copy**; your original dump is never modified and nothing is overwritten.

- `.bps` is built in and checks both your source image and the result against checksums inside the patch, so a wrong
  region or revision is caught before anything is written.
- `.ips` is built in (offsets below 16 MB, so it suits small files such as an extracted `main.dol`, not whole discs).
- `.xdelta` / `.vcdiff` need the free `xdelta3` program installed; Pawtation runs it for you.

Put the patched copy in your library folder and rescan. A mod normally keeps the original's disc ID, so Pawtation
sees two copies of one game and uses one: your original wins over a `<name> - patched` (or `<name> copy`) file in the
same folder, and `scan` lists the other under "Duplicate ignored". To rotate the mod as its own
game, give it a catalog entry whose `title` (or an alias) is exactly the file name without the extension, and no
`code4`; a file name that exactly matches such an entry wins over the disc ID. Patch a plain `.iso`; compressed images
must be converted first.

## 3. Catalog and lines (data, no code)

- **Add or fix a game:** append to `data/catalog.json`: `{"key": "my-mod", "title": "My Mod", "year": 2026, "developer": "",
  "genres": [], "tags": ["cozy"], "aliases": ["file name without extension"], "code4": "GXXE"}`. Leave `code4` out unless
  it is a different ID from every other entry. Tags drive game quips.
- **Fill in more disc IDs:** `python scripts/import_ids.py your-id-list.txt` (dry run; `--apply` to write). Format: `GXXE01 = Title` per line.
- **Lines:** `data/pets.json`, keyed by cast id. Per-character buckets (`greeting`, `idle`, `arrive`, `leave`, `absent`
  with `{name}`, `rotation_due`, `rotated`, `synced` with `{card}`, `ranked` with `{game}`, `study_break`), per-game
  lines in `game_quips[key][id]`, per-tag lines in `tag_quips[tag][id]`, `jokes` and `fortunes` as
  `[["Display name", "text"], ...]`. A new activity is one more entry in `activities`; the app grows a button for it.
  `python -m unittest tests.test_pets_content` checks length, placeholders and the house voice rules.

## 4. Add a character, end to end

Code never names a character; everything keys off `data/cast.json` and the role (`main`, `guest`, `cameo`).

1. **Canon first.** Add a row and a paragraph to `docs/CHARACTERS.md` (species, pronouns, palette, must-haves,
   voice, height relative to Nova). Original designs only; never commit someone else's reference art.
2. **`data/cast.json`:** one entry under `characters`:
   `"pip": {"name": "Pip", "species": "otter", "pronouns": "she/her", "role": "cameo", "aliases": ["pip", "otter"],
   "color": "#6b8fa3", "accent": "#f2c14e", "hours": [8, 22]}`. Ids are lowercase letters, digits, `-` and `_`.
   `hours` is optional (local 24-hour clock, end exclusive, may wrap past midnight); a cameo outside its hours is
   never drawn for a walk-on. Mains and guests take part in `presence.groups` (keys are sorted ids joined with `+`;
   `cameo` means "the usual pair plus one eligible cameo").
3. **Lines in `data/pets.json`:** cameos need `greeting`, `idle`, `arrive` and `leave` (3 or more each) and may appear
   in `jokes`. Mains and guests need every bucket listed in section 3. Add a `characters.<id>` entry
   (`name`, `species`, `vibe`, and ASCII `art` / `art_happy` / `art_sleep`, at most 6 lines by 22 columns, the same
   number of lines per mood) for the CLI.
4. **Scenes (optional):** section 5.
5. **Sprites (optional, the app shows text without them):** a rig at `art/rigs/<id>.py` (copy a cameo rig such as
   `art/rigs/tuft.py`; set `CAMEO = True` and `PORTRAIT = False` for a cameo), then
   `python3 art/build.py --only <id> --contact` and look at `art/out/contact_<id>.png`. Cameos need `idle` (2-4 frames)
   and `talk` (2) at 96 and 192 px; mains and guests need the full set in `docs/SPEC_V2.md` section 5. Commit the PNGs
   and `assets/sprites/manifest.json`. Hand-drawn PNGs work too (`docs/ART_PIPELINE.md`, "Replace art by hand").
6. **Check:** `python -m unittest discover -s tests` and `python -m pawtation cast`.

## 5. Scenes (`data/scenes.json`)

```json
{"id": "pip-borrows-a-card", "who": ["iggy", "nova", "pip"], "when": "any", "rating": "all", "weight": 1,
 "lines": [["pip", "Can I borrow card three?"], ["iggy", "No."], ["*", "Pip borrows card three."]]}
```

- `who`: the participants. A scene **without** a cameo plays when `who` equals the non-cameo characters at home
  exactly (so a walk-on never silences the mains). A scene **with** a cameo plays when everyone in `who` is home, and
  is preferred while that cameo is visiting.
- `when`: `any`, `arrive`, `leave`, `rotated`, `synced` (`{card}`), `due`, `night` (22:00-05:00), `morning`,
  `game:<catalog key>` or `tag:<tag>` (both may use `{game}`). Event moments (`arrive`, `leave`, `rotated`, `synced`,
  `due`) never fall back to `any` scenes; the others do. `about` (optional) says who an `arrive`/`leave` scene is about.
- `lines`: 2 to 6 rows of `[speaker id, text]`; the speaker must be in `who`, or `"*"` for a stage direction. Text is
  plain, at most 140 characters, and never calls the player a pet name.
- `rating`: `"all"` or `"afterdark"`; anything else counts as After Dark (fail closed). `weight` is relative odds.
- `python -m unittest tests.test_scenes_content` checks all of the above; `python -m pawtation scene --when night`
  plays one.

## 6. Packs (`packs/<name>/`)

A pack adds content without editing the shipped files. `packs/` is yours: everything in it except its `README.md`
is git-ignored.

    packs/<name>/pack.json      {"name": "My pack", "rating": "all"}      ("all" or "afterdark")
    packs/<name>/pets.json      extra lines, same shape as data/pets.json (lists are appended, never replaced)
    packs/<name>/scenes.json    extra scenes, same shape as data/scenes.json
    packs/<name>/sprites/<id>/<size>/<anim>_<nn>.png    replacement sprite frames (96 and 192, square RGBA)

- **Rating:** a pack loads always only if `pack.json` says exactly `"rating": "all"`. A pack rated `"afterdark"`, or
  with a missing, broken or odd `pack.json`, loads only while After Dark is unlocked on this computer. Inside an
  all-rated pack, scenes rated `afterdark` are also held back until unlocked.
- **Sprite overrides:** per frame, the first allowed pack that has
  `sprites/<id>/<size>/<anim>_<nn>.png` wins over the built-in frame (After Dark packs only while unlocked). A pack
  can replace frames of animations the manifest already lists; it cannot add new animations.
- Packs can add lines and scenes for characters that exist in `data/cast.json`; a new character still needs its
  cast entry (section 4).
- Card quips (`/pawtation/quips.txt`) only ever use all-rated content.

## 7. Plugins (`plugins/*.py`)

Drop a file in `plugins/`; it loads on start. `plugins/cozy_bonus.py` is a working example. A file whose name starts
with `_` is ignored. A plugin that crashes is reported by `python -m pawtation doctor` and skipped.

```python
def register(api):
    api.chat(r"\bboop\b", lambda brain, m, ctx: "Mochi: Boop received.")       # ctx: roms, saves, pet, text, home, named
    api.score(lambda rom, state, now: 5 if "cozy" in rom.tags else 0)          # nudge the rotation planner
    api.on("synced", lambda card_id, report, mount, **kw: print("done", card_id))
    api.on("planned", lambda plan, roms, **kw: None)
    api.command("hello", lambda args: print("hi"), help="say hi")              # python -m pawtation hello
    api.pet_content("idle", "mochi", ["A new line, added at runtime."])
    api.progress_parser("G8ME", read_ttyd)                                     # see below
```

`api.core`, `api.pets`, `api.saves` are the modules themselves if you need more. Inside a chat hook, ask the
`brain` for lines (`brain.say(id, "idle")`, `brain.scene()`): it applies the After Dark lock for you. Plugins are ordinary Python running
as you: only install ones you wrote or have read.

### Progress parsers (reading real story progress from a save)

Out of the box Pawtation shows what a save says about itself: game, size, date, and the two-line description the
game wrote into the save (for Paper Mario TTYD that is the file name and a date string). It never invents progress.

A parser is `fn(raw: bytes) -> str`, where `raw[:0x40]` is the save's header and `raw[0x40:]` its data. None ship,
because none could be checked against a real save. The best documented candidate is Paper Mario TTYD: the
community decompilation describes four 0x4000-byte slots starting at 0x2000 in the save data, with the player's
level, coins and star points inside each slot (offsets in `docs/RESEARCH_NOTES.md`, section C3). Those offsets are
from source headers, not yet confirmed on a real file, so the right way to finish it is: export one of your own
TTYD saves to `.gci`, write the parser in a plugin, and compare what it prints with what the file-select screen
shows. Animal Crossing has documented structures but no single simple progress value; Mario Kart, Chibi-Robo and
Soulcalibur II have no reliable public documentation.

## 8. What goes on a card (so mods land where the loader looks)

    <card>/.pawtation.json                  manifest: what Pawtation wrote (only these are ever deleted)
    <card>/games/<Title>/game.iso           single-disc game
    <card>/games/<Title>/disc1.iso, disc2.iso   multi-disc game (Swiss pairs discs by their headers)
    <card>/swiss/cheats/<ID6>.txt           from your mods/ folder, if any
    <card>/pawtation/quips.txt              plain-text all-ages lines for a future on-console companion

Swiss starts `.iso` and `.gcm` (also `.tgc`, `.fdi`, `.nkit.iso`). It refuses `.gcz` and `.rvz` and does not support
`.ciso`, so Pawtation lists those in your library but keeps them off the cards; convert them to `.iso` with Dolphin or
NKit. Swiss also gives up on a file split into more than 40 fragments, which is why Pawtation copies one file at a
time; if a game ever fails with "too fragmented", back up the card, re-format it, and sync again.

### The card manifest (stable contract for anything that reads a card)
`<card>/.pawtation.json`, written after every finished file:
```json
{"schema": 2, "card_id": "1", "label": "Card 1", "updated": 1794700000,
 "files": {"paper-mario-ttyd": "games/Paper Mario The Thousand-Year Door/game.iso"},
 "more_files": {"resident-evil-4": ["games/Resident Evil 4/disc2.iso"]},
 "aux": {"swiss/cheats/G8ME01.txt": "paper-mario-ttyd", "pawtation/quips.txt": "pawtation"},
 "titles": {"paper-mario-ttyd": "Paper Mario: The Thousand-Year Door"}}
```
`files` is disc 1 of each game, `more_files` any further discs, `aux` the small extras and who owns them. Paths are
relative, forward-slashed, and never contain `..`. Additive changes only; readers must ignore unknown keys.
