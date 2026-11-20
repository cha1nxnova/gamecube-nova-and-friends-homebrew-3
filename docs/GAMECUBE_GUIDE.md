# Playing on the GameCube: a short guide

Your setup: **Action Replay disc + GC2SD adapters (microSD) + stock Swiss.**
One small card boots Swiss; your bigger cards hold the games Pawtation rotates.

> Nova says: "Read it once all the way through, then follow it like a prescription. No improvising the dose." 🐾

## What you need

| Thing | Notes |
|---|---|
| **Boot card** | A microSD of **2 GB or smaller** (Action Replay can't read bigger, SDHC cards). Only Swiss lives here. |
| **Game cards** | Your bigger microSDs, one per GC2SD. Pawtation fills these. |
| **A real memory card** | For saves. A GC2SD can't save games. |
| **Action Replay disc** | Starts Swiss from the boot card. |
| **Swiss** | The official release from github.com/emukidid/swiss-gc/releases (the `.7z` file; open it with 7-Zip). The last one checked here is **r2119**. |

## 1. Make the boot card (once)

1. Format the 2 GB card as **FAT** (Windows picks this by default for a card that small).
2. Unpack the Swiss `.7z` somewhere on your computer.
3. Put the card in your computer and run (change `E:\` and the path to match yours):
   ```
   python -m pawtation boot-card --mount E:\ --swiss-dol "C:\Downloads\swiss_r2119\ActionReplay\AUTOEXEC.DOL" --go
   ```
   That copies it to the card as `autoexec.dol`. Leave out `--go` first if you want to preview.
   (The desktop app's **Boot card…** button does the same.)
4. Label this card **BOOT** with a sticker so it never ends up in the game rotation.

## 2. Fill the game cards (every rotation)

1. Format each game card as **FAT32** the first time. (Windows' own formatter won't do FAT32 above 32 GB; a free
   FAT32 formatter tool will.)
2. In Pawtation: `plan` → `plan --commit` → `sync 1 --mount E:\` (dry run) → add `--go` to copy for real.
   Games land in `games/<Title>/game.iso`.
3. Only `.iso` / `.gcm` files work. If `scan` lists a `.rvz`, `.gcz` or `.ciso`, convert it to `.iso` with
   Dolphin first.

## 3. Playing

1. **Power off.** Real memory card in **Slot A**, GC2SD with the **boot card in Slot B**.
2. Put in the Action Replay disc and power on. It should start Swiss by itself.
3. In Swiss, swap the boot card for a game card (powering off to swap is safest), then pick the SD device again
   so Swiss re-reads it.
4. Open `games`, choose a game, press **A** to start. Saves go to the real memory card in Slot A.
5. Done for the night? Power off; nothing needs to be closed.

## Tips

- **Swiss settings** (on the console, in Swiss's settings screen): turn on the *Carousel* game browser and *hide
  unknown file types* for a tidier list. Swiss saves these to the card itself.
- **Keep a spare boot card** with the same Swiss on it. If a new Swiss release misbehaves, swap back.
- **Two-disc games** travel together as `disc1.iso` / `disc2.iso`. When the game asks for disc 2, Swiss should
  offer to swap.
- **Cheats:** put them in `mods/<game>/card/swiss/cheats/<disc ID>.txt` (see `docs/MODDING.md`). Press **Y** on
  the game's screen in Swiss to choose them.

## If something goes wrong

| What you see | Try |
|---|---|
| The Action Replay menu comes up, not Swiss | Boot card is over 2 GB, isn't FAT, or is in the other slot. Try Slot A. If it still won't start, see "Backup route" below. |
| A game isn't in the list | It's probably not an `.iso`/`.gcm`; convert it. Also try the unknown-files setting. |
| Swiss says the file is too fragmented | Reformat the card and let Pawtation fill it fresh (Swiss can't start a file split into more than 40 pieces). |
| A black screen after starting a game | Try the game's video setting in Swiss (forcing the region's video mode), then power-cycle. |

**Backup route (not yet tested on your hardware):** some Action Replay discs use the release's
`ActionReplay/SDLOADER.BIN` instead. Swiss's own file notes say it starts Swiss from the card and that `swiss.dol`
must also be on the card. So copy `SDLOADER.BIN` and the release's `DOL/swiss_r2119.dol` (renamed to `swiss.dol`)
to the boot card's root as well.

## Still unchecked on real hardware

Nobody has run this on your console yet. Please note what happens the first time (which slot worked, which file the
Action Replay picked up, whether two-disc games swap) and add it to `HANDOFF.md`, so the next person knows.
