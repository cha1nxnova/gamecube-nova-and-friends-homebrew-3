# Pawtation 🐾  (paw + rotation)

Rotate your legally acquired GameCube disc images across 5 (or more) GC2SD SD cards, with a rotation timer,
a desktop app, and two chat pets: **Mochi** (cat, deadpan) and **Biscuit** (dog, chaos).

Pure Python 3.9+, standard library only, works offline.

## Quick start
```
python -m pawtation init --library "D:\GameCube\ROMs"   # writes config.json
python -m pawtation doctor                               # is this computer ready?
python -m pawtation scan                                 # what did we find? (reads disc IDs, pairs multi-disc games)
python -m pawtation plan                                 # preview a rotation
python -m pawtation plan --commit                        # save it + start the timer
python -m pawtation sync 1 --mount E:\                   # dry run for card 1
python -m pawtation sync 1 --mount E:\ --go              # really copy (add --verify to re-read and checksum)
python -m pawtation sync all --go                        # every plugged-in card Pawtation has labelled before
python -m pawtation cards                                # which cards are plugged in, what is on them
python -m pawtation chat                                 # talk to the pets in a terminal ("help" lists ideas)
python -m pawtation gui                                  # desktop app (needs tkinter)
python -m pawtation mods / patch / saves / wrapped       # mod files, patched copies, save summaries, season recap
python -m unittest discover -s tests                     # run tests
```
Linux GUI: `sudo apt install python3-tk`. Every command has `--help`. Making it your own: `docs/MODDING.md`.

## Your hardware flow (Action Replay + GC2SD)
1. **Boot card:** a *separate small standard SD, 2 GB or less* (the Action Replay SD Media Launcher reads only standard SD, not SDHC/SDXC).
   Put Swiss on it as `autoexec.dol`: `python -m pawtation boot-card --mount E:\ --swiss-dol swiss.dol --go`.
2. Boot the Action Replay disc with the boot card in the GC2SD; it launches Swiss.
3. Swap in one of your 5 game cards (rotated by Pawtation), refresh Swiss's device list, play. Swapping while powered on is the common community
   workflow but is at your own risk; power off first if unsure.
4. **Saves:** the GC2SD can't act as a save memory card. Use a real GameCube memory card for saves (Swiss can also emulate one on some setups; see docs/FORK_GUIDE.md sources).

## How rotation works
- **Pinned favorites:** your top 5 (`config.json -> pinned`) go one-per-card, in order, so every card has a favorite.
- **Everything else:** fills remaining space by score = star rating (dominant) + weeks since last loaded + a little randomness.
  A non-pinned game is on at most one card per season.
- **Timer:** `rotation_days` (default 14). The app shows a countdown and Mochi/Biscuit nag when it's due.
- **Sync is safe:** only files Pawtation wrote (tracked in `.pawtation.json` on the card) are ever deleted.
  Your Swiss files, saves and other games are left alone. Removal happens before copying; files are copied one at a
  time to reduce fragmentation (Swiss prefers contiguous files; for best results re-format a card now and then and let Pawtation refill it).
- **Add a card:** add an entry under `cards` in `config.json`. Nothing else changes.
- **Cards know who they are:** after its first sync a card carries its number, so later syncs find it by itself, and
  syncing card 2's games onto card 1 by mistake is refused (`--force` to re-purpose a card).
- **Multi-disc games** count as one game and both discs travel together.
- **Interrupted copy?** Pull the card or press Ctrl+C whenever; no half-written game is left under a real name, and the next sync continues.

## Things you should know (honest notes)
1. **Top 5:** Paper Mario TTYD, Animal Crossing, Soulcalibur II, Mario Kart Double Dash, Chibi-Robo (Animal Crossing replaced Katamari Damacy, which is a PS2 game, not GameCube). Change `pinned` in `config.json` any time.
2. **Image formats:** Swiss starts `.iso`/`.gcm`. It refuses `.gcz`/`.rvz` and has no `.ciso` support, so Pawtation shows those in `scan` but never puts them on a card. Convert them to `.iso` with Dolphin or NKit.
3. **Game list:** `data/catalog.json` has 651 titles (from Wikipedia's GameCube list), 444 with a North American disc ID checked against GameTDB. Games without an ID match by file name, including dump-set names like `Legend of Zelda, The - The Wind Waker (USA).iso`. Only the original 79 have tags (which drive pet quips). Sources: `docs/CATALOG_SOURCES.md`.
4. **Saves:** `saves` (and asking the pets about "saves") shows game, size, date and the description text each save carries. Real story progress needs a per-game reader; none ship because none could be checked against a real save (`docs/MODDING.md`). Set `saves_dir` in `config.json` to a folder of exported `.gci`/`.gcs` files.
5. **Loader / fork:** Swiss was not forked or modified. Read `docs/FORK_GUIDE.md` section 1 before deciding; the Swiss maintainer asks that AI tools not be used on that code.
6. **Tested how:** the logic has automated tests (temp folders standing in for SD cards). The desktop app was run under a virtual Linux display; see `docs/GUI_CHECKLIST.md` for what was and was not exercised. Nothing has been run on Windows or macOS, on a real SD card, or on a real GameCube.
7. **Action Replay boot:** how your AR disc launches Swiss from the GC2SD varies by AR version. Swiss's release archive contains an `ActionReplay/AUTOEXEC.DOL`; that is the file to give `boot-card`. An existing `autoexec.dol` is kept as `autoexec.dol.bak`.
