# packs/

Your own content packs. Everything in this folder except this file is ignored by git, so nothing here is
committed unless you choose to.

    packs/<name>/pack.json     {"name": "My pack", "rating": "all"}      or "afterdark"
    packs/<name>/pets.json     extra lines, same shape as data/pets.json (lists are appended)
    packs/<name>/scenes.json   extra scenes, same shape as data/scenes.json
    packs/<name>/sprites/      optional replacement or extra sprite frames

Packs rated `all` always load. Packs rated `afterdark` load only after After Dark has been unlocked on this
computer (`python -m pawtation afterdark`). See `docs/SPEC_V2.md` section 4 and `docs/MODDING.md`.
