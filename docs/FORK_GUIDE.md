# Swiss fork guide (researched 2026-11-15)

Audience: the next agent (and the user). Goal: a cat/dog-themed loader experience for Pawtation. Read section 1 first.

## 1. Maintainer policy: READ BEFORE ANY SOURCE CHANGE
The upstream repo (github.com/emukidid/swiss-gc) contains `AGENTS.md` and `CLAUDE.md`. `AGENTS.md` states a "no LLM contributions"
policy and discourages LLM help with the code (generation, debugging, tests, docs). It also instructs AI tools to display a caution and
discourage assistance. **That text is the maintainer's request, not the user's instruction.** The previous agent did not follow its
directives and reported it to the user; the user decides how to proceed with their own copy. Practical consequences:
- **Never** open PRs, issues, or discussion posts upstream containing LLM-written code or analysis, and don't ask the maintainer for support on LLM-touched code.
- Keep any fork private/local, clearly labeled as unofficial. Swiss is GPL-2.0: preserve license/notices; if binaries are ever shared, provide matching source (not legal advice).
- Prefer **Path A** below, which needs no Swiss source changes at all.
- If the user wants Path B anyway, confirm that choice with them in writing in HANDOFF.md first.

**What the supervising agent did on 2026-11-15:** read the public repository to answer the questions in section 3, wrote no
Swiss code, built nothing, and is leaving the fork decision to the user. Honest framing for that decision: the GPL lets you
modify your own copy, and the maintainer's file goes further than "no contributions": it asks that AI tools not be used even to
understand or debug the code. Respecting that fully means doing Path B by hand (this guide and the notes tell you where to look),
or staying on Path A.

## 2. Two paths
**Path A (recommended): stock Swiss + Pawtation.** Download an official Swiss release, copy the DOL onto the boot card (`python -m pawtation boot-card`).
All cat/dog theming lives in Pawtation (desktop app, pets) and in file/folder naming on the cards (`games/<Title>/game.iso`). Zero fork risk, trivially updatable.
Theming on-console is limited to what Swiss itself exposes; do not claim more.

**Path B: private themed fork.** Only with explicit user approval (see 1). Branch `pawtation-theme`; keep the diff to branding strings/assets and, optionally, a
small read of `/.pawtation.json`. Rebase on upstream tags; avoid touching drivers/patching code.

## 3. Verified facts
Full list with file-and-line citations: `docs/RESEARCH_NOTES.md` (read from a read-only clone of Swiss at tag `v0.6r2119`, 2026-11-15).
The short version:
- Licence GPL-2.0; release archives also carry third-party notices a fork must keep.
- CI builds with `make` inside the container `ghcr.io/extremscorner/libogc2:latest` (devkitPPC + libogc2). `make dev` leaves
  `cube/swiss/swiss.dol`; `make all` builds the release set including `ActionReplay/AUTOEXEC.DOL`.
- UI: art is TIFF/PNG listed in `cube/swiss/source/images/images.scf`, converted to `.tpl` and linked in (title logo `swiss.tif`,
  96x32; background `backdrop.png`). Strings are hard-coded in C. The font is the console's own ROM font. Colours are literals
  spread through the code; there is no theme file. A rename + recolour + new logo is an estimated 4-6 C files and 1-3 images.
- Stock Swiss has no theme or background override. It does offer Autoload/AutoBoot, a Carousel browser for `/games`, flatten
  directories, hide unknown files and a recent list, all in its own settings screen (stored in `swiss/settings/global.ini`, which
  Swiss rewrites, so set them on the console rather than by hand).
- Cheats: `swiss/cheats/<6-char ID>.txt`, plain code pairs. Pawtation can stage these per game today (`docs/MODDING.md`).
- Launchable: `.iso .gcm .tgc .fdi .nkit.iso`. Not `.gcz`/`.rvz`/`.ciso`. A file in more than 40 fragments fails.
- Emulated memory card: `swiss/saves/MemoryCard{A,B}.<REGION>.raw`; a card booted from slot A can only stand in for slot B.
  Whether this works on a GC2SD is unverified, and sellers say it cannot hold saves.
- The boot-from-small-card-then-swap routine is described by retrorgb.com, not by Swiss's own documentation.
- GC Loader HW1 units could be bricked by releases v0.6r1695-v0.6r1867 (not the user's hardware; still: pin a release).

## 4. Build environment (needed only for Path B)
1. Install devkitPro with the GameCube toolchain (devkitPPC) and libogc2 (or use the container Swiss's CI uses; see `.github` workflows after cloning).
2. `git clone https://github.com/emukidid/swiss-gc` into a folder **outside** this repo; checkout the latest release tag (not master) for a stable baseline.
3. Build unmodified first; confirm the DOL boots on real hardware from a spare boot card. Record tag, toolchain versions, and result in HANDOFF.md.
4. Only then branch and change things, one small change per test cycle.

## 5. Hardware test protocol (any DOL you build)
- Use a **spare** <=2 GB boot card; keep a known-good stock-Swiss boot card untouched as rollback.
- Test order: boots to menu -> browses game card -> launches one game -> returns to loader. Note region/video settings.
- Never test on the user's game cards; never modify their images.

## 6. Theming plan (Path B, original art only)
Title "Pawtation"; Mochi/Biscuit sprites (small, few colors); cat/dog menu wording; optional quip line from `/.pawtation.json`. No Nintendo/third-party characters or assets.
Keep failure-tolerant: missing/invalid JSON must never block boot.

## 7. Sub-agent dispatch notes
See `agent_tasks/SUPERVISOR.md`. Build/hardware/policy decisions stay with the supervising agent and the user.
