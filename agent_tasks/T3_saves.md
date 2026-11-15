# T3: Per-game save progress parsers
Context: `pawtation/saves.py` reads .gci headers (game code, modified time, blocks) and has an empty `PROGRESS_PARSERS` hook. Pets must not claim progress they can't read.
Goal: implement parsers ONLY for games where you can document the save layout from a reliable source or from sample .gci files the user provides. Targets: Paper Mario TTYD (G8ME), Animal Crossing (GAFE), Chibi-Robo (GGTE), Mario Kart DD (GM4E), Soulcalibur II (GRSE).
Reality check: GC saves can be compressed/checksummed/encrypted per game. If you have no sample files, deliver a parser *skeleton + test fixtures plan* and say plainly that nothing is implemented. Never fabricate offsets.
Wire-up: surface `info["progress"]` in `PetBrain.reply` (save/progress intent) with Mochi/Biscuit flavor text.
Verify: tests with synthetic fixtures; report what is real vs. skeleton. Edit only saves.py, pets.py, tests/.
