# GUI checklist (version 2 desktop app)

What was exercised for `pawtation/gui.py` on 2026-11-15, and what was not. Linux container only:
Python 3.12 + Tk 8.6 under Xvfb (`xvfb-run -a -s "-screen 0 1400x900x24"`), fonts = whatever the container has
(DejaVu Sans family resolved from the theme candidates). Screenshots are in `art/out/gui/`.

## Automated (tests/test_gui.py)

Run: `xvfb-run -a python3.12 -m unittest discover -s tests` (all pass). Under plain `python3` (3.13, no tkinter)
the window tests skip and two source tests still run (no hex colour literals in gui.py; importing the module never
crashes). Config and state are always redirected to a temp dir (setUpModule); SD cards are temp dirs; disc images
are sparse fakes with the GameCube magic word.

Covered: empty config launch + empty-library state; listing, search, "nothing matches" state; rating (incl. a game
not in the catalog, stars in the table); pin/unpin (heart column + pinned tag); sorting with arrows; threaded sync
end to end; cancel mid-copy leaves no `.part`; wrong-card "use anyway" flow; worker error shown; boot card;
theme toggle (button and F2) saved as `gui_theme`; rotation-due nag once per session + banner + title marker;
every feature button, an activity and chat; `report_callback_exception` shown; closing during a sync waits for the
worker; stage shows one sprite image per present character and follows "Everyone"; chips invite / send out and the
engine's "a main stays home" message; "Surprise me"; hang-out plays lines one at a time (click advances); bubble
shows name + pronouns + text; clicking a character pets them; ASCII fallback with an empty assets root; plain ttk
fallback (`PAWTATION_PLAIN_WIDGETS=1`); After Dark gate (under-age and invalid stay locked, adult unlocks, the date
string never reaches state.json / config.json / the log, second open does not ask, "Lock again" works); a sentinel in
a temp After Dark data dir never reaches the log over 25 rounds of hang-out / joke / fortune / study break / pet /
chat while locked (and does appear once unlocked, so the fixture is live); reduced motion schedules no timers but
the countdown; closing mid-animation leaves none of our after() callbacks pending; the stage sizing rule (trio at
192 px at 1400x900, a visiting cameo at 96 px beside them, name tags never overlapping or leaving the stage, a narrow
stage falling back to 96 px) and the Game column taking spare width. Every temp folder the module makes is removed
(per-test `addCleanup`, `tearDownModule`, an `atexit` fallback).

## Driven by hand (art/out/gui/)

| Shot | What it showed |
|---|---|
| `first_start.png` | 1400x900, light, no library: empty-library card with "Pick library folder", Nova alone greeting, default cards dimmed "empty", rotation-due banner + gold header pill. |
| `pair_start.png`, `pair_hangout.png` | Light, 7 fake games, Nova + Iggy home at 192 px, hang-out bubble with name tag, pinned rows in pink, star rating, meters. |
| `trio_start.png`, `trio_hangout.png` | Dark "Cosmic", all three home at 192 px (stage wide enough), bubble over the speaker, chips "Send out". |
| `sync_mid.png` | Dark, 400 MB sparse fake mid-copy (worker throttled by the driver so the frame can be caught): low-poly sync loop beside the chunky bar with sparkle, "7% Copying Big: 29 MB of 400 MB", speed and ETA, Cancel sync enabled, library buttons and chips disabled. `sync_cancelled.png`: cancelled text. |
| `gate.png` | After Dark gate over the light window: "optional · 18+" tag, plain body, one date field, "Not now" focused (ring), "Check and turn on". |
| `narrow_start.png`, `narrow_hangout.png` | 1000x660: compact stage (96 px), activities folded into "Activities ▾" / "Ask ▾" menus, everything visible, no clipping; the game table is short (about 3 rows) but scrolls. |
| `cameo_start.png`, `cameo_talk.png` | Nova + Iggy + Mochi (cameo sprite from the 2D art set, standing at the right edge of the stage). Taken before the wave-3 sizing rule: the pair was at 96 px then; it is now 192 px with the cameo at 96 px. |
| `stage_trio_light.png`, `stage_trio_dark.png` | Wave 3 sizing rule, 1400x900: Nova, Iggy and Duskie at 192 px on a 540x292 stage, two-line bubble over Nova, name tags apart and inside the stage, Game column wider (long titles show in full when Tags has room). |
| `stage_trio_cameo.png` | 1400x900, light: the trio at 192 px (squeezed a little closer) and Mochi at 96 px at the right edge; no name tag touches another or the stage edge. |
| `stage_narrow_light.png`, `stage_narrow_dark.png` | 1000x660 with the trio: the 188 px compact stage, so 96 px stickers; tags and bubble inside the stage. The table hides Rating/Tags at this width, as before. |

Fixed after looking: wrapped button rows (were aligned to a shared grid, now each row packs left), pill shapes (true
arcs), header timer text invisible in dark (now `primary_ink` on `keyline`), right column clipped at 1000x660
(banner moved to the library column, compact actions), bubble covering 96 px sprites (wider, lower bubble),
name tags running off the stage edge (clamped), ETA line overflowing.

## Not verified

- Real Windows and macOS (clam theme forced; Aqua and Windows fonts, Trebuchet / Chalkboard picks untested).
- Native file dialogs (`ask_directory`, `ask_file` still use tkinter.filedialog; always monkeypatched in tests).
- Real removable drives / real SD cards, slow media, a card pulled mid-sync.
- High-DPI and `ui_scale` 1.25 / 1.5 (fonts scale; Canvas sizes are px and were not checked at scale).
- Keyboard-only walkthrough beyond the shortcuts (Tab order through Canvas pills works in principle; not audited).
- Screen readers. Long sessions (memory of cached PhotoImages; frames are cached per size and kept for the session).
- Themed dialogs: confirm, error (`dialog_error_dark.png`, `dialog_confirm_dark.png`), card choice and "After Dark is
  on / Lock again" were opened once each by a driver and closed with Escape / Return (results: No, closed, card "1",
  Keep it on). Mouse clicks inside them, Tab looping and the under-18 in-dialog message were not driven by hand
  (the under-18 path is covered by the gate test through `ask_birthdate`'s check callback, not the real Toplevel).
- Animation smoothness: verified only that frames advance (screenshots show idle / wave / talk frames), not timing.
