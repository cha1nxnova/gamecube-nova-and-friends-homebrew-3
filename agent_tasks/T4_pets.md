# T4: Pet content expansion
Context: `data/pets.json`. Mochi = deadpan cat who loves naps; Biscuit = excitable dog. Theme: cats/dogs/furry-adjacent humor and GameCube references. Original characters only; no copyrighted dialogue; no song lyrics.
Goal: +40 jokes, +4 lines per existing bucket per pet, quips for every top-5 game (Paper Mario TTYD, Animal Crossing, Soulcalibur II, Mario Kart Double Dash, Chibi-Robo) and every tag in the catalog, +3 activities (e.g. "fetch", "laser", "groom") with energy/affection rules.
Style: short (<= 140 chars), warm, never mean, no real people. Keep placeholders valid ({game} {card} {days}).
Verify: JSON loads; run `python -m pawtation chat` and exercise each new activity; tests pass. Edit only data/pets.json (+ pets.py only if a new activity needs logic).
