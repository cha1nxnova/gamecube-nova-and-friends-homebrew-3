# Pawtation (GameCube: Nova and friends)

Private, personal project. A desktop app + CLI (Python 3.9+, standard library only) that rotates the owner's own
GameCube disc images across SD cards, starring the owner's characters Nova, Iggy and Duskie. It sets up stock Swiss boot cards; Swiss itself is never modified.

- Read `HANDOFF.md` first, then `docs/SPEC_V2.md` (contracts between modules) and `docs/CHARACTERS.md` (canon).
- `python3 -m pawtation --help` lists commands. Tests: `python3 -m unittest discover -s tests`
  (GUI tests need tkinter and a display: `xvfb-run -a python3.12 -m unittest discover -s tests`).
- Runtime code under `pawtation/` is standard library only. Art tools under `art/` may use dev-time tools
  (headless Chromium, Pillow); what they generate under `assets/` is committed, and the app must still start
  with every image missing.
- SD-card safety is absolute (HANDOFF.md "Rules of the road"): only files listed in a card's own manifest are
  ever deleted or overwritten, every manifest path goes through `core.card_path`, sync is a dry run by default.
- Characters: never change a species, palette or marking; no character addresses the player with pet names;
  other artists' reference art is never committed. Iggy uses any/all pronouns (docs write "they").
- After Dark is an opt-in 18+ tier behind a one-time date-of-birth check. Nothing sexually explicit is authored
  in this repository, and a birth date is never stored. `packs/` is the owner's own space and is git-ignored.
- The Hidden World (docs/SPEC_V2.md section 9) is a hidden, passcode-locked compartment inside After Dark for
  the owner's own packs. It ships empty: author nothing for it, and never mention or hint at it in the UI, help
  text or README.
- Swiss is **stock only** (`docs/SWISS.md`): never clone, read, patch, build or debug Swiss source with an AI tool,
  and never contact the Swiss project about anything made here. The old theme fork was removed on 2026-11-20.
- Never commit `config.json`, `state.json`, disc images, saves, real names or birth dates.
- Tests must never touch the real config or state: pass a cfg/state, or patch `core.CONFIG_PATH` / `STATE_PATH`.
