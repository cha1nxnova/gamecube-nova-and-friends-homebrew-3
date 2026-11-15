# T2: Catalog expansion
Context: `data/catalog.json` has ~79 seed titles; the GameCube library is roughly 650 releases.
Goal: add many more titles with correct metadata. Fields: key (slug), title, year, developer, genres[], tags[], optional aliases[], optional code4.
Rules: add `code4` ONLY if you can confirm it from a source you cite in your report (e.g. a user-supplied GameTDB/Redump export or a reputable database). If unsure, omit it.
Do not invent titles, years, or developers; skip anything you can't verify. Keep tags from the existing vocabulary where possible (furry, cats-and-dogs, cozy, racing, party, horror, rpg, ...); add new tags only with a matching entry in `data/pets.json` -> tag_quips.
Optional: write `scripts/import_ids.py` that merges a user-supplied "ID = Title" text file into the catalog by code4 (dry-run by default).
Verify: JSON loads, no duplicate keys, tests pass. Edit only data/catalog.json, scripts/import_ids.py, data/pets.json (tag_quips).
