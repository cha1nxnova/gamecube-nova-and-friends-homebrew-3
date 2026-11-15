# Pawtation theme for Swiss (private, unofficial)

A small cosmetic patch queue over **Swiss** (the GameCube homebrew loader, github.com/emukidid/swiss-gc,
GPL-2.0, by emu_kidid, Extrems and contributors) at release tag **`v0.6r2119`**
(commit `163f8b1de75328ad3a9a79caabff924930c04213`). It changes colours, the title logo and backdrop, and
adds Nova and a start-up quip to the title bar. Nothing else.

## Terms (from `docs/FORK_GUIDE.md` section 1, the owner's decision of 2026-11-15)

- **Private and unofficial.** This build is for the owner's own consoles. It is labelled "unofficial theme,
  based on Swiss" in the title bar and on the info screen. It is not made, endorsed or supported by the
  Swiss project.
- **Nothing goes upstream.** No pull requests, issues, discussions, emails or support requests to the Swiss
  project or its community about this fork or anything built from it. Never `git push` the fork anywhere.
  Upstream's `AGENTS.md` asks that LLM tools not be used with Swiss code. This fork was made with agent help
  by the owner's choice, which is one more reason it stays out of upstream's space. If you find a bug, check
  it on **stock** Swiss and report it by hand, with no fork code.
- **Attribution is kept.** Swiss's name, authors, version line, commit/revision line, links, supporter list
  and `LICENSE` are unchanged. The info screen (page 4/5) only gains the line "Pawtation theme: private,
  unofficial, not supported by the Swiss project".
- **GPL-2.0.** If a build is ever given to anyone else, you must also give them the matching source: the
  upstream tag plus `patches/` here (and keep the licence and the release's `Licenses/` folder with it).
  This is not legal advice.
- **Cosmetic only.** No changes to patches, device drivers, DVD/GCM/NKit code, the loader or the reserved
  area.

## What is in this folder

| Path | What |
|---|---|
| `patches/0001-0004*.patch` | `git format-patch --binary v0.6r2119..pawtation-theme`, one commit per step. `patches/SHA256SUMS` lists their sha256 sums |
| `apply.sh` | clones (or reuses `SWISS_SRC`) upstream, checks the tag's commit hash, the patch checksums and the resulting tree hash (`f8721a7a...`), runs `git am`, then builds in Docker. It stops at the first mismatch |
| `docker/Dockerfile` | the build image recipe: upstream CI's container, pinned by digest, plus the packages CI installs |
| `art/make_art.py` | regenerates all theme art from `assets/sprites/nova/96/idle_*.png`, `assets/renders/star.png` and the Cosmic colours in `data/theme.json` (Pillow, fixed seed) |
| `art/out/` | the generated images (identical to the ones in patches 0003/0004) and `preview.png` |

No upstream source file and no built binary is stored here.

## The four patches

| # | Commit (local) | Files | Lines |
|---|---|---|---|
| 1 | Palette | ADD `gui/pawtation_theme.h` (47); `gui/FrameBufferMagic.c` +28/-27; `gui/IPLFontWrite.c` +4/-3 | +79/-30 |
| 2 | Identity | `pawtation_theme.h` +11; `FrameBufferMagic.c` +4/-4; `gui/info.c` +2; `swiss.c` +1/-1 (the `load_app` failure text no longer says "open an issue") | +18/-5 |
| 3 | Art | ADD `images/pawlogo.png` (96x32, I4, tinted pink), `images/pawbackdrop.png` (640x480, CMPR); `images/images.scf` +2/-2; `FrameBufferMagic.c` +3/-4; `pawtation_theme.h` +1 | +6/-6 + 2 images |
| 4 | Mascot + quip | ADD `gui/pawtation.c` (121), `gui/pawtation.h` (27), `images/pawart.scf` (1), `images/pawmascot.png` (256x64, RGB5A3, 4 frames); `FrameBufferMagic.c` +43/-4; `pawtation_theme.h` +7/-2; `main.c` +2 | +201/-6 + 1 image |

Paths are under `cube/swiss/source/`. In total: 13 files, +299/-42 lines, plus 3 PNGs.

Look: navy-plum panels (`#241d40`), hot pink (`#ff4fa3`) borders, scrollbar, menu glow, progress bar and
logo, dark-pink selection fill (`#b02670`) behind off-white text (`#f1eff8`, about 5:1), lilac-grey for
deselected text. Per-device pictures, file-type icons, region flags and the checkbox/star tints are left as
upstream.

Title bar, left to right: Nova (64x64, 4-frame idle, a new frame every 16 retraces), the pink "Pawtation"
wordmark with a paw, then the quip. "unofficial theme, based on Swiss 0.6 r2119" sits under the wordmark.
On the right are the clock, then the CPU temperature (moved from row 1 to row 2) and
"commit: <hash> · fork rev: <N>". The commit hash and revision are the fork's own: r2123 for this queue,
because the Makefile counts commits.

### Quip file
`pawtation/quips.txt` on the boot device: plain ASCII, one quip per line, `#` lines ignored. Pawtation's
desktop sync writes it. It is read once at boot, on the main thread, right after stock Swiss loads its
own `swiss/backdrop.tpl`, on the same device. Limits: at most 4096 bytes are read, the first 40 usable lines
are considered, and each line is cut to 60 printable characters (bytes outside 0x20-0x7E are dropped).
A file with a NUL byte, or with more than 1 non-printable byte in 8, is treated as binary and ignored.
Missing, empty, unreadable, binary or all-blank files, or no boot device, give a built-in Nova line. All
buffers are static: no heap, nothing to leak, nothing shown to the user, no retries. Long quips are shrunk
to fit (down to scale 0.45) and then cut with "...". Set `PAWTATION_MASCOT 0` in `gui/pawtation.h` to turn
the mascot and quip off.

## Rebuild

```sh
# from this repository's root; Docker must be running
swiss_fork/apply.sh            # full release set: swiss-gc-pawtation/swiss_r2123/...
swiss_fork/apply.sh dev        # quick: swiss-gc-pawtation/cube/swiss/swiss.dol (unpacked)
SWISS_SRC=/path/to/clean/clone swiss_fork/apply.sh --no-build
```
By hand: `git clone https://github.com/emukidid/swiss-gc && cd swiss-gc && git checkout -b pawtation-theme v0.6r2119
&& git submodule update --init --recursive && git am --keep-cr patches/*.patch`, then
`docker run --rm --init --network none -v "$PWD:/src" -w /src swiss-build:local make`.
`--keep-cr` is required, because several upstream files use CRLF line endings. To change the art, run
`python3 swiss_fork/art/make_art.py`, copy `art/out/paw*.png` into `cube/swiss/source/images/`, commit,
and re-export the patches.

## Themed build (2026-11-15)

Built from branch `pawtation-theme` at local commit `f0504d6f` (revision 2123) with image `swiss-build:local`
(devkitPPC 16.2.0, libogc2 r2500.cb7745a).

| Artifact | Bytes | sha256 |
|---|---|---|
| `swiss_r2123/DOL/swiss_r2123.dol` (packed, trailer `f0504d6f`) | 1416776 | `28d505fdba52ed46b418bd5284254683216bd56fee056d14dec0d1ce92975b59` |
| `swiss_r2123/ActionReplay/AUTOEXEC.DOL` (identical copy) | 1416776 | `28d505fdba52ed46b418bd5284254683216bd56fee056d14dec0d1ce92975b59` |
| `cube/swiss/swiss.dol` (unpacked, same build) | 4064128 | `cafc938c30d833b4be134f4e52df7ae6f99f5b4ebe360b02ecee218a8acd9b56` |

Copies are in `/home/user/swiss-work/artifacts/themed/` (outside this repository, with `SHA256SUMS`). A rebuild
through `apply.sh` gets different commit hashes (`git am` sets new committer dates), so its DOL bytes will
differ. The source tree hash is what stays fixed.

## What is verified and what is not

Verified:
- `make dev` succeeds after each of the four commits, and the full `make` (release set `swiss_r2123`) succeeds,
  with no compiler warnings from the changed files.
- The textures were decoded back out of the built objects: backdrop 640x480 CMPR, logo 96x32 I4, mascot strip
  256x64 RGB5A3. Each looks as intended.
- The new strings and the built-in quips are in the DOL.
- The quip reader (`pawtation.c`) was compiled on the PC against stub headers, with AddressSanitizer and
  UBSan, and run against: no folder, empty file, one line, 40 lines, 500 lines, a 300-character line, 3 KB of
  random bytes, CRLF with comments, tabs and UTF-8, control bytes only, 100 KB of zeros, a 5000-byte line,
  and no device. Every case gave a printable quip of 60 characters or fewer, with no sanitizer errors and
  one close for every open.
- `git am --keep-cr` of `patches/` onto a clean clone at the tag reproduces the branch's tree exactly.
  `apply.sh dev` was run end to end on a fresh clone and built.
- `art/make_art.py` is deterministic: a second run gives byte-identical PNGs, and those match the images in
  the patches.

**Not verified: the theme has NOT been seen running.** No emulator in this environment shows Swiss's UI.
Dolphin presents only a black screen for stock Swiss too; see `docs/BUILD_LOG.md` section 6. One forced
attempt with the themed DOL was also black. Nothing has run on a GameCube. In particular these are
unchecked: the exact on-screen layout (the console font's glyph widths are only known at runtime; the
layout reasoning used approximations), the mascot's straight-alpha draw and GX state reset, the readability
of every screen, PAL/480p modes, and quip reading on real SD adapters. `PAWTATION_MASCOT 0` has not been
compiled. Follow the hardware test protocol in `docs/FORK_GUIDE.md` section 5 (spare boot card, stock-Swiss
card kept for rollback), and check the step 1-4 lists in `docs/SWISS_THEME_MAP.md` section 8.

Boot-name caution (`SWISS_THEME_MAP.md` 6.3): the unpacked `swiss.dol` has no commit trailer. Do not put it
on a card as `boot.dol`, `boot2.dol` or `swiss_r*.dol`, because it may chain-boot itself. The packed
release DOL has the trailer.
