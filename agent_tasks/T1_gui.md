# T1: Desktop GUI hardening
Context: `pawtation/gui.py` (tkinter) was only syntax-checked; the build sandbox had no display. Core logic is tested.
Goal: make the GUI run correctly on Windows/macOS/Linux and not freeze during SD copies.
Do: (1) launch it (needs a display; if you have none, say so and stop - do not fake results); (2) fix runtime bugs; (3) run `core.sync_card` in a worker thread
with progress reporting (extend `sync_card` with an optional `progress(cb)` argument, default no-op, keep CLI behavior identical); (4) add a "Boot card..." button calling `core.prepare_boot_card`; (5) add a "Countdown" notification (window title flashes when rotation is due).
Constraints: stdlib only; core stays UI-free; never copy/delete on a real card in tests (use temp dirs).
Verify: `python -m unittest discover -s tests`; manual GUI checklist in your report.
Edit only: pawtation/gui.py, pawtation/core.py (progress arg), tests/.
