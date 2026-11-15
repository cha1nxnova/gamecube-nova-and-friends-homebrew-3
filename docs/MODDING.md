# Modding guide

Pawtation is built to be bent. There are four ways to change it, from "no code" to "new feature". Facts about
Swiss below come from `docs/RESEARCH_NOTES.md` (source files and line numbers are cited there).

| You want to... | Do this | Code needed |
|---|---|---|
| Ship cheat codes or other small files with a game | `mods/<game-key>/card/...` | none |
| Play a patched version of a game you own | `python -m pawtation patch` | none |
| Change what the pets say | `data/pets.json` | none |
| Add behaviour (chat commands, planner rules, save readers) | a file in `plugins/` | a few lines of Python |
| Change the app itself | `pawtation/*.py`, see `HANDOFF.md` | yes |

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
sees two copies of one game, uses the first, and `scan` tells you which file it ignored. To rotate the mod as its own
game, give it a catalog entry whose `title` (or an alias) is exactly the file name without the extension, and no
`code4`; a file name that exactly matches such an entry wins over the disc ID. Patch a plain `.iso`; compressed images
must be converted first.

## 3. Catalog and pets (data, no code)

- **Add or fix a game:** append to `data/catalog.json`: `{"key": "my-mod", "title": "My Mod", "year": 2026, "developer": "",
  "genres": [], "tags": ["cozy"], "aliases": ["file name without extension"], "code4": "GXXE"}`. Leave `code4` out unless
  it is a different ID from every other entry. Tags drive pet quips.
- **Fill in more disc IDs:** `python scripts/import_ids.py your-id-list.txt` (dry run; `--apply` to write). Format: `GXXE01 = Title` per line.
- **Pet lines:** `data/pets.json`. Per-game lines in `game_quips`, per-tag lines in `tag_quips`. A new activity is one more
  entry in `activities`; the app grows a button for it. `python -m unittest tests.test_pets_content` checks length and placeholders.

## 4. Plugins (`plugins/*.py`)

Drop a file in `plugins/`; it loads on start. `plugins/cozy_bonus.py` is a working example. A file whose name starts
with `_` is ignored. A plugin that crashes is reported by `python -m pawtation doctor` and skipped.

```python
def register(api):
    api.chat(r"\bboop\b", lambda brain, m, ctx: "Mochi: Boop received.")       # ctx: roms, saves, pet, text
    api.score(lambda rom, state, now: 5 if "cozy" in rom.tags else 0)          # nudge the rotation planner
    api.on("synced", lambda card_id, report, mount, **kw: print("done", card_id))
    api.on("planned", lambda plan, roms, **kw: None)
    api.command("hello", lambda args: print("hi"), help="say hi")              # python -m pawtation hello
    api.pet_content("idle", "mochi", ["A new line, added at runtime."])
    api.progress_parser("G8ME", read_ttyd)                                     # see below
```

`api.core`, `api.pets`, `api.saves` are the modules themselves if you need more. Plugins are ordinary Python running
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

## 5. What goes on a card (so mods land where the loader looks)

    <card>/.pawtation.json                  manifest: what Pawtation wrote (only these are ever deleted)
    <card>/games/<Title>/game.iso           single-disc game
    <card>/games/<Title>/disc1.iso, disc2.iso   multi-disc game (Swiss pairs discs by their headers)
    <card>/swiss/cheats/<ID6>.txt           from your mods/ folder, if any
    <card>/pawtation/quips.txt              plain-text pet lines for a future on-console companion

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
