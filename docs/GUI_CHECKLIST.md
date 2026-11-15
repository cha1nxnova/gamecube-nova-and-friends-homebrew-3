# GUI checklist (verified by running under `xvfb-run python3.12`, tkinter 8.6, Linux only)

Screenshots live in the session scratchpad `gui_shots/` (not committed): 
- `06_empty_1280x800_dark.png` empty config, window enlarged: widgets scale, nothing clipped, "Rotation due NOW" shown.
- `02_populated_dark.png` populated library at 980x640 after plan/rate/pin/play: wrapped activity buttons, pet bars, card strip, pinned hearts.
- `03_populated_light.png` same in the light theme: text legible.
- `04_syncing_dark.png` threaded sync mid-copy: progress bar, "Copying <title> - 104 MB / 300 MB", plan/sync buttons disabled, Cancel enabled.

Exercised by tests/test_gui.py (skipped without tkinter + display): construct/destroy, empty config, search filter, rating
(catalog and non-catalog games), pin toggle, threaded sync to a temp card, cancel leaves no `.part`, "labelled as card" force flow,
worker exception reporting, boot card, theme toggle saved, nag-once, pet buttons, callback-exception dialog, close-during-sync.

NOT verified: Windows/macOS, real removable drives or auto-detected mounts, native file dialogs, title flashing visually,
F1/Ctrl shortcuts via real key events, the paw-prefix title in a real window manager.
