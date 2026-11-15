# Pawtation (GameCube: Nova and friends)

Private, personal project. A desktop app + CLI (Python 3.9+, standard library only) that rotates the owner's own
GameCube disc images across SD cards, starring the owner's characters Nova, Iggy and Duskie, plus a private
cosmetic fork of the Swiss loader kept as a patch queue.

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
- Swiss fork (`swiss_fork/`, see `docs/FORK_GUIDE.md` section 1): private, cosmetic only, Swiss's authors and
  GPL-2.0 licence stay credited, and nothing ever goes upstream (no pull requests, issues or support requests).
- Never commit `config.json`, `state.json`, disc images, saves, real names or birth dates.
- Tests must never touch the real config or state: pass a cfg/state, or patch `core.CONFIG_PATH` / `STATE_PATH`.
