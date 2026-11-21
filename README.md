# Pawtation 🐾  (paw + rotation)

Rotate your own legally acquired GameCube disc images across 5 (or more) GC2SD SD cards, with a rotation timer, a
desktop app, a CLI, and a small household of characters who live on the app's stage.

Pure Python 3.9+, standard library only, works offline (the one exception: the optional one-click Swiss download).

## Get Pawtation.exe (Windows, nothing to install)
1. On GitHub, open this repository's **Actions** tab, then the newest green **Build Pawtation.exe** run.
2. Under **Artifacts**, download **Pawtation-windows** and unzip it into its own folder (e.g. `Documents\Pawtation`).
   Your settings, ratings and downloaded Swiss files are kept next to `Pawtation.exe`.
3. Double-click `Pawtation.exe`. Windows may say "Windows protected your PC" (the app is not from a known publisher):
   click **More info**, then **Run anyway**.
4. The first time, **GameCube setup** opens and walks you through everything: your games folder, your game cards,
   getting Swiss (one click), the boot card, the first rotation and what to do at the console. The
   **GameCube setup…** button opens it again any time.

GitHub builds a fresh `Pawtation.exe` every time code is pushed (`.github/workflows/build-windows.yml`); the build also
starts the app once to check it opens and finds its files.

## The cast
- **Nova** (serval, he/him) and **Iggy** (fennec fox, they) are the mascots and are home most of the time, usually
  together. **Duskie** (golden jackal, he/him) is a regular guest. Ten neighbours (Pickle, Vesper, Tuft, Hazel,
  Sprout, Stilts, Flurry, The Refills, Mochi and Biscuit) drop in now and then for a few minutes. Vesper only comes
  round at night and Sprout only by day. Canon: `docs/CHARACTERS.md`.
- **Who is home** changes by itself every 20 to 90 minutes. You can also set up a **meetup** yourself: any one, any
  pair, or all three (`cast --gather nova duskie`, `cast --everyone`, or the chips in the app).
- They talk in **scenes**: short multi-character exchanges for whoever is home, the time of day, a rotation, a sync,
  or a game. In chat, name a character to talk to them; if they are out, someone who is home answers for them.
- **The stage** in the desktop app shows everyone who is home as die-cut sticker sprites (idle, blink, talk, wave,
  happy, sleep, a special move), with walk-ons and walk-offs. A low-poly Nova is the window icon and the sync animation;
  low-poly busts and turntables of all three are in `assets/renders/`.

**After Dark** is an opt-in tier for adults (18+): flirtier, innuendo-level banter between the three adult main
characters. It is off by default. Unlocking asks for your date of birth once, checks it against today's date and then
forgets it: only "unlocked" and the day you confirmed are saved. Chat can explain it but never unlock it. While it is
locked, its lines are not even read from disk. The lines written into `/pawtation/quips.txt` on your SD cards are
always all-ages, unlocked or not. Nothing sexually explicit ships with Pawtation. `python -m pawtation afterdark --lock`
turns it off again.

**The look:** two themes, **Blush** (light) and **Cosmic** (dark), switched with the header button or F2. Every colour
comes from `data/theme.json` and is checked for contrast (WCAG AA). Reduced motion is honoured
(`gui_reduce_motion: true` in `config.json`, or `PAWTATION_REDUCE_MOTION=1`).

## Quick start
```
python -m pawtation init --library "D:\GameCube\ROMs"   # writes config.json
python -m pawtation doctor                               # is this computer ready?
python -m pawtation swiss get                            # download the official Swiss release's boot files
python -m pawtation scan                                 # what did we find? (reads disc IDs, pairs multi-disc games)
python -m pawtation plan                                 # preview a rotation
python -m pawtation plan --commit                        # save it + start the timer
python -m pawtation sync 1 --mount E:\                   # dry run for card 1
python -m pawtation sync 1 --mount E:\ --go              # really copy (add --verify to re-read and checksum; see note 9)
python -m pawtation sync all --go                        # every plugged-in card Pawtation has labelled before
python -m pawtation cards                                # which cards are plugged in, what is on them
python -m pawtation gui                                  # desktop app (needs tkinter)
python -m pawtation chat                                 # talk to whoever is home ("help" lists ideas)
python -m pawtation cast                                 # who is home right now
python -m pawtation cast --gather nova duskie            # a meetup (also --everyone, --random, --minutes N)
python -m pawtation scene                                # play a scene now (--when night, rotated, game:<key>...)
python -m pawtation afterdark                            # After Dark: --status, unlock (asks once), --lock
python -m pawtation mods / patch / saves / wrapped       # mod files, patched copies, save summaries, season recap
python -m unittest discover -s tests                     # run tests
```
Linux GUI: `sudo apt install python3-tk`. Every command has `--help`. Making it your own (characters, scenes, packs,
plugins): `docs/MODDING.md`.

## Your hardware flow (Action Replay + GC2SD)
Step by step, with troubleshooting: **`docs/GAMECUBE_GUIDE.md`**. Swiss is always the official, unmodified release (`docs/SWISS.md`).

1. **Boot card:** a *separate small standard SD, 2 GB or less* (the Action Replay SD Media Launcher reads only standard SD, not SDHC/SDXC).
   Put Swiss on it as `autoexec.dol`: `python -m pawtation boot-card --mount E:\ --swiss-dol "C:\Downloads\swiss_r2119\ActionReplay\AUTOEXEC.DOL" --go`.
2. Boot the Action Replay disc with the boot card in the GC2SD; it launches Swiss.
3. **With Swiss running**, swap the boot card for one of your game cards (rotated by Pawtation), pick the SD device again
   in Swiss, play. Do not power off to swap: the Action Replay can only start Swiss from the small boot card, so after a
   power cycle you have to boot from the boot card again. Swap on Swiss's file browser, never while a game is loading.
4. **Saves:** the GC2SD can't act as a save memory card. Use a real GameCube memory card for saves (Swiss can also emulate one on some setups; see `docs/RESEARCH_NOTES.md`).

## How rotation works
- **Pinned favorites:** your top 5 (`config.json -> pinned`) go one-per-card, in order, so every card has a favorite.
- **Everything else:** fills remaining space by score = star rating (dominant) + weeks since last loaded + a little randomness.
  A non-pinned game is on at most one card per season.
- **Timer:** `rotation_days` (default 14). The app shows a countdown, and whoever is home mentions it once per session when it's due.
- **Sync is safe:** only files Pawtation wrote (tracked in `.pawtation.json` on the card) are ever deleted.
  Your Swiss files, saves and other games are left alone. Removal happens before copying; files are copied one at a
  time to reduce fragmentation (Swiss prefers contiguous files; for best results re-format a card now and then and let Pawtation refill it).
- **Add a card:** add an entry under `cards` in `config.json`. Nothing else changes.
- **Card size:** set each card's `capacity_gb` to the size printed on it (e.g. `32`). Until a card has been synced once,
  the planner fills only about 95% of that; after a sync it uses the card's real, measured size (never more than
  `capacity_gb`). A changed size counts from the next `plan --commit`.
- **Cards know who they are:** after its first sync a card carries its number, so later syncs find it by itself, and
  syncing card 2's games onto card 1 by mistake is refused (`--force` to re-purpose a card).
- **Multi-disc games** count as one game and both discs travel together.
- **Interrupted copy?** Pull the card or press Ctrl+C whenever; no half-written game is left under a real name, and the next sync continues.

## Art
The sprites and renders are committed PNGs under `assets/`; the app never needs the art tools, and it still starts
(with text instead of pictures) if every image is missing. To change or rebuild art you need the dev-time tools
(headless Chromium for the 2D rasteriser; Pillow optional):
```
python3 art/build.py                 # 2D sticker sprites -> assets/sprites (--only nova, --contact, --check)
python3 art/lowpoly/build.py         # low-poly renders -> assets/renders (--only iggy, --list)
```
Details: `docs/ART_PIPELINE.md`, `docs/ART_LOWPOLY.md`.

## Things you should know (honest notes)
1. **Top 5:** Paper Mario TTYD, Animal Crossing, Soulcalibur II, Mario Kart Double Dash, Chibi-Robo (Animal Crossing replaced Katamari Damacy, which is a PS2 game, not GameCube). Change `pinned` in `config.json` any time.
2. **Image formats:** Swiss starts `.iso`/`.gcm`. It refuses `.gcz`/`.rvz` and has no `.ciso` support, so Pawtation shows those in `scan` but never puts them on a card. Convert them to `.iso` with Dolphin or NKit.
3. **Game list:** `data/catalog.json` has 651 titles (from Wikipedia's GameCube list), 444 with a North American disc ID checked against GameTDB. Games without an ID match by file name, including dump-set names like `Legend of Zelda, The - The Wind Waker (USA).iso`. Only the original 79 have tags (which drive game quips). Sources: `docs/CATALOG_SOURCES.md`.
4. **Saves:** `saves` (and asking about "saves" in chat) shows game, size, date and the description text each save carries. Real story progress needs a per-game reader; none ship because none could be checked against a real save (`docs/MODDING.md`). Set `saves_dir` in `config.json` to a folder of exported `.gci`/`.gcs` files.
5. **Swiss:** Pawtation uses stock Swiss releases only. The earlier private theme fork was removed on 2026-11-20 at the owner's request, out of respect for the Swiss maintainers' request that AI tools not be used on their code (`docs/SWISS.md`). All the theming lives in this app.
6. **Tested how:** the logic has automated tests (temp folders standing in for SD cards). The desktop app was run under a virtual Linux display only; see `docs/GUI_CHECKLIST.md` for what was and was not exercised. Nothing has been run on Windows or macOS, on a real SD card, or on a real GameCube.
7. **Action Replay boot:** how your AR disc launches Swiss from the GC2SD varies by AR version. Swiss's release archive contains an `ActionReplay/AUTOEXEC.DOL`; that is the file to give `boot-card`. An existing `autoexec.dol` is kept as `autoexec.dol.bak`.
8. **Version 1 saves:** an old `state.json` keeps loading; Mochi's and Biscuit's version-1 stats are left alone.
9. **`--verify`** re-reads each copied file and compares checksums. On Linux it reads the card itself. On Windows and
   macOS the re-read may come from the PC's memory, so there it may not detect anything. The real test on Windows is
   starting the game on the console.
10. **Library on an external drive?** If it is unplugged, `sync` and `plan --commit` stop with a message and change
   nothing. A planned game whose library file is missing, renamed or now compressed stays on its card for the current
   season; once a new plan leaves it out (it can no longer be copied), the next sync removes it like any game that
   rotates out. So keep a playable `.iso` in the library for every game you want to keep rotating.
