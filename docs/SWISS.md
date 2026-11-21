# Swiss: stock only

Pawtation uses **official, unmodified Swiss releases** (github.com/emukidid/swiss-gc, GPL-2.0, by emu_kidid,
Extrems and contributors). This file is the rule for every agent and human working here.

## Decision on record (2026-11-20)

The owner chose stock Swiss and asked for the private themed fork to be removed. The earlier fork
(`swiss_fork/`, a patch queue over `v0.6r2119`, plus `docs/BUILD_LOG.md` and `docs/SWISS_THEME_MAP.md`) was
deleted from the working tree on that date. It remains in git history only; do not restore or rebuild it.

Why: Swiss's own repository carries an `AGENTS.md` asking that AI tools not be used with Swiss code (writing,
debugging, tests, docs, or explaining it). The GPL would allow a private fork, but the owner chose to respect the
maintainers' request.

## Rules

- **Do not** clone, read, patch, build or debug Swiss source with an AI tool, in this repository or outside it.
- **Do not** contact the Swiss project about anything made here: no pull requests, issues, discussions or support
  requests. If stock Swiss misbehaves, the owner reports it by hand.
- All theming (Nova, Iggy, Duskie, colours, quips) lives in Pawtation: the desktop app, the CLI, and the file and
  folder names Pawtation puts on cards. Do not claim on-console theming that Swiss itself does not offer.
- Use a **release**, never master. Keep one known-good boot card untouched as a rollback before trying a newer
  release.

## What Pawtation does with Swiss

- `swiss get` (and **Get Swiss** in the setup wizard, `pawtation/swissget.py`) downloads the newest official release
  archive (`.tar.xz`) from Swiss's GitHub releases page, checks its size and the SHA-256 GitHub publishes, and copies
  out only `ActionReplay/AUTOEXEC.DOL`, `ActionReplay/SDLOADER.BIN` and `DOL/swiss_r<N>.dol`. Nothing else in the
  archive is read. This is release *binaries*, used as shipped; it is not working with Swiss source, and must stay
  that way. It is the only code in Pawtation that goes online.
- `python -m pawtation boot-card --mount <card> --swiss-dol <file> --go` copies the release's
  `ActionReplay/AUTOEXEC.DOL` to the root of a 2 GB (or smaller) boot card as `autoexec.dol`, keeping any existing
  one as `autoexec.dol.bak`. It touches nothing else on the card.
- Only `.iso`/`.gcm` go onto game cards; Swiss refuses `.gcz`/`.rvz` and has no `.ciso` support.
- Settings that Swiss offers itself (carousel browser, recent list, hide unknown files, autoload) are set on the
  console in Swiss's settings screen, not by Pawtation.

User-facing steps: `docs/GAMECUBE_GUIDE.md`. Facts about release contents and file formats: `docs/RESEARCH_NOTES.md`.
