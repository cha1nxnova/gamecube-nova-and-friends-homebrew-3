# Swiss theming map @ v0.6r2119 (for the private "Pawtation" theme)

Read-only analysis, 2026-11-15. Nothing was built, run or modified upstream-side; no toolchain was available here.
Source: shallow clone `<R>/swiss-gc` at tag `v0.6r2119` = commit `163f8b1` (2026-09-24), detached HEAD.
`<R>` = `/tmp/claude-0/-home-user-Calendar-thing-3/9a964607-7d81-5744-8f0c-5e8996d674bb/scratchpad/research`.
Paths are relative to the Swiss repo root unless noted. `S/` = `cube/swiss/source/`, `FBM.c` = `S/gui/FrameBufferMagic.c`.

Legend: unmarked = read at the tag (file:line given). `EXT` = read in a current external source, not the exact version
the tag was built with (`<R>/ext/libogc2` @ cb7745a 2026-11-12, `<R>/ext/gamecube-tools` @ 9545458 2026-01-09,
devkitPro `devkitppc-rules` master). `INFERRED` = my reasoning, not read or run.

Ground rules carried by this document (owner's decision, see `FORK_GUIDE.md` section 1): the fork is private, personal,
always labelled unofficial, never published; nothing goes upstream (no PR, issue, discussion, mail, support request); no
`git push` anywhere. Upstream's `AGENTS.md` (19 lines) / `CLAUDE.md` (`@AGENTS.md`) exist at this tag and state a
no-LLM-contribution policy; that is upstream contribution policy and is the reason for the "nothing upstream" rule.

Corrections to `RESEARCH_NOTES.md` section A (those notes were taken on master `d817e8d`, not the tag):
- A4 line numbers are off at the tag: TPL open is `FBM.c:333-340`, logo draw `FBM.c:1515`, backdrop tint `FBM.c:512`, colours `FBM.c:738-742, 896-898, 1262-1264`, info pages `S/gui/info.c:313-338`.
- A4 title strings: at the tag the version is the literal `"version 0.6"` (`FBM.c:1517`); there is no `GIT_VERSION`.
- A5/"no external theme override" is wrong at the tag: stock Swiss loads `swiss/backdrop.tpl` from the boot device (`FBM.c:2283-2353`, called at `S/main.c:311`). See 1.9.
- A3 package list: at the tag `Makefile:63` checks `devkitppc-licenses gamecube-tools-git libogc2-git libogc2-libdvm-git libogc2-pkg-config ppc-libdeflate ppc-libiconv ppc-libmad ppc-libpsoarchive ppc-libuchardet ppc-libxxhash ppc-zlib-ng-compat`.

## 1. Art pipeline

### 1.1 Build chain (no Makefile edit needed for art)
| Stage | Where | Fact |
|---|---|---|
| discover scripts | `cube/swiss/Makefile:52-53,100-101` | `TEXTURES := source/images source/images/buttons`; `SCFFILES := $(foreach dir,$(TEXTURES),$(notdir $(wildcard $(dir)/*.scf)))`; `TPLFILES := $(SCFFILES:.scf=.tpl)` |
| `.scf` -> `.tpl` | EXT `libogc2/gamecube_rules:23-25` | `%.tpl : %.scf` runs `gxtexconv -s $< -d $(DEPSDIR)/$*.d -o $@` (the `.d` lists every image, so editing an image rebuilds) |
| ID header | EXT `gxtool/tfbinarytdf.cpp:41-55` | gxtexconv also writes `<out>.h` next to the `.tpl`: one `#define <id> <index>` per entry, index = position in the script -> `build/images.h`, `build/buttons.h` |
| `.tpl` -> object | `cube/swiss/Makefile:166-169` | `%.tpl.o %_tpl.h : %.tpl` -> `$(bin2o)`; EXT `base_tools:57-58`: `bin2s -a 32 -H <name>_tpl.h` then assembled by gcc. Gives `images_tpl[]`, `images_tpl_size` (symbol names INFERRED from use at `FBM.c:333`) |
| ordering | `cube/swiss/Makefile:116,161` | `HFILES := ... images_tpl.h buttons_tpl.h tags.h`; `$(OFILES_SOURCES) : $(HFILES)` so all C waits for the generated headers |
| includes | `S/gui/FrameBufferMagic.h:38-41` | `#include "images_tpl.h"`, `"images.h"`, `"buttons_tpl.h"`, `"buttons.h"` (found via `-I$(CURDIR)/$(BUILD)`, Makefile:123) |

Tools: `gxtexconv` (package `gamecube-tools-git`; uses the FreeImage library, so PNG/TIFF/TGA/BMP load directly) and
`bin2s` (devkitPro tools). Nothing else is needed for art. The `.psd` files and `S/resources/*` are masters only; no
Makefile references `S/resources/` (grep).

### 1.2 `.scf` format (EXT `gxtool/parser.cpp:192-232`, `converter.cpp:331-398`, `gxtexconv.cpp:16-26`)
One entry per `< ... />`; lines starting with `#` are skipped; `filepath` is relative to the script's directory
(`converter.cpp:254-255`). Tokens: `filepath="f" id="name" colfmt=N [palfmt=N] [wraps=N wrapt=N] [minfilt=N magfilt=N]
[mipmap=yes minlod=N maxlod=N remaplod=N] [xsize=N ysize=N]`.
| Token | Values | Default |
|---|---|---|
| `colfmt` | 0 I4, 1 I8, 2 IA4, 3 IA8, 4 RGB565, 5 RGB5A3, 6 RGBA8, 8 CI4, 9 CI8, 14 CMPR (same numbers as `GX_TF_*`) | 6 |
| `palfmt` (CI only) | 0 IA8, 1 RGB565, 2 RGB5A3 | 1 |
| `wraps`/`wrapt` | 0 clamp, 1 repeat, 2 mirror | repeat if both sides are powers of two, else clamp (`texturefile.cpp:356-391`) |
| `minfilt`/`magfilt` | 0 near, 1 linear (2-5 = mip variants) | linear/linear (`texturefile.cpp:58-88`) |
| `mipmap=yes` | needs power-of-two sides <= 1024 (`converter.cpp:451-484`) | no. Neither stock script uses mipmaps |
Conversion rules that matter for art: I4/I8 take `(R+G+B)/3` and ignore alpha (`tfbinarytdf.cpp:79-91`); IA8 takes
`I=(R+G+B)/3`, `A=alpha` or 255 if the image has no transparency (`:194-206`); CI+IA8 palette: `I` = palette grey,
`A` = palette transparency (`:653-673`); RGB5A3: alpha >= 224 becomes opaque RGB555, else 3-bit alpha + RGB444 (`:344-349`).
gxtexconv does not premultiply. A side that is not a multiple of 4 is bilinearly rescaled up to one (`image.cpp:85-93`).

### 1.3 `S/images/images.scf` (34 entries, script order = texture index; sizes read with PIL / `file`)
| # | id | file | px | src mode | colfmt -> GX | Use (tint = vertex colour in `_DrawImageNow`, `FBM.c:490-647`) |
|---|---|---|---|---|---|---|
| 1 | `backdrop` | backdrop.png | 320x240 | P16+trns | 8 CI4, palfmt 0 IA8, magfilt 0 | background tile atlas, see 1.9 |
| 2 | `backdrop_ind` | backdrop_ind.png | 40x32 | LA | 3 IA8, near/near | indirect tile map for the backdrop |
| 3 | `banner_mask` | banner_mask.tif | 96x32 | P | 0 I4 | rounded-corner alpha mask over game banners (`FBM.c:1234,1283`) |
| 4 | `bbaimg` | bba.tif | 140x64 | RGBA | 3 IA8 | BBA device picture |
| 5-8,10,12,15,22,31 | `dirimg dolimg dolcliimg elfimg fileimg fpkgimg gcmimg mp3img tgcimg` | *.tif | 96x32 each | RGBA | 6 RGBA8 | file-type "banner" icons with the label text baked into the art; assigned in `S/devices/filemeta.c:266-437` |
| 9,11,14,16,18,19,33,34 | `eth2gcimg flippyimg gcloaderimg gcnetimg kunaigcimg m2loaderimg wiikeyimg wodeimg` | *.tif | 64x80, 104x40, 120x88, 72x88, 120x80, 112x56, 120x80, 120x40 | L | 0 I4 | device pictures, tinted {216,216,216} (m2loader: white) |
| 13,30 | `gcdvdsmall systemimg` | *.tif | 84x84, 76x48 | RGBA | 3 IA8 | DVD and System device pictures |
| 17,28,32 | `hddimg sdsmall usbgeckoimg` | *.tif | 104x76, 64x80, 64x84 | PA | 9 CI8, palfmt 0 | IDE-EXI, SD card, USB Gecko pictures (grey + alpha) |
| 20,21 | `memcardimg memcardimg_ind` | memcard.png, memcard_ind.png | 352x16, 8x8 | L | 9 CI8 palfmt 0 magfilt 0; 1 I8 near/near | memory card picture as tile atlas + indirect map (virtual 80x92, `FBM.c:552-556`) |
| 26,27 | `qoobimg qoobimg_ind` | qoob.png, qoob_ind.png | 352x16, 8x8 | L | same scheme | Qoob picture (virtual 96x102, `FBM.c:535-539`) |
| 23-25 | `ntscjimg ntscuimg palimg` | *.tif | 32x20 | RGBA | 5 RGB5A3 | region flags (`filemeta.c:291-361`) |
| 29 | `swissimg` | swiss.tif | 96x32 | L | 0 I4 | **title logo: white "Swiss" wordmark**, drawn at (36,32) 96x32 (`FBM.c:1515`) |
(`#` = 1-based script line; the generated index is line-1.) Not in any script: `backdrop.tif` (640x480 master),
`memcard.tif`, `qoob.tif`, `gamecube.png`, `*.psd`, `filetype-font.ttf`; `gamecube_rgb.h` is a C array used for the memory
card save icon (`S/devices/memcard/deviceHandler-CARD.c:19,388`), unrelated to the UI.

### 1.4 `S/images/buttons/buttons.scf` (12 entries)
| id | px | colfmt | wrap | Use |
|---|---|---|---|---|
| `boxinner`, `boxouter` | 16x16 | 0 I4 | clamp | quarter-corner masks for every panel: fill and border (`_DrawSimpleBox`, `FBM.c:467-487`) |
| `btndevice btnsettings btninfo btnrefresh btnexit` | 24x24, 32x32, 32x32, 24x32, 32x32 | 0 I4 | default | the 5 bottom menu glyphs, drawn white (`FBM.c:1562-1566`), offsets in hand-written `btns.h` |
| `btnhilight` | 68x52 | 1 I8 | default | glow behind the selected menu glyph, tint {127,134,255} (`FBM.c:560-565,1557`) |
| `checked_32` / `unchecked_32` | 32x32 / 16x16 | 0 I4 | default / mirror | checkbox, tints {0,128,0} / {87,87,87} (`FBM.c:581-587`) |
| `loading_16` | 128x16 | 0 I4 | mirror | 8-frame spinner strip, frame picked by s-coords (`FBM.c:750-761`) = precedent for sprite-strip animation |
| `star_16` | 8x16 | 0 I4 | mirror S | autoload star, tint {255,255,0} |

### 1.5 Loading code (`FBM.c:331-388`, `init_textures()`, called from `DrawInit` `FBM.c:2270`)
```c
TPL_OpenTPLFromMemory(&imagesTPL, (void *)images_tpl, images_tpl_size);       /* 333 */
TPL_OpenTPLFromMemory(&buttonsTPL, (void *)buttons_tpl, buttons_tpl_size);    /* 334 */
TPL_GetTextureCI(&imagesTPL, backdrop, &backdropTexObj, &backdropTlutObj, GX_TLUT0);  /* 335 */
GX_InitTexObjUserData(&backdropTexObj, &backdropTlutObj);                     /* 336 */
TPL_GetTexture(&imagesTPL, backdrop_ind, &backdropIndTexObj);                 /* 337 */
GX_InitTexObjUserData(&backdropIndTexObj, &backdropTexObj);                   /* 338: this link switches tiling on */
TPL_GetTexture(&imagesTPL, swissimg, &swissTexObj);                           /* 340 */
```
All other entries follow one of two patterns: non-CI = `TPL_GetTexture(&tpl, id, &xTexObj);`; CI = `TPL_GetTextureCI(...)`
plus `GX_InitTexObjUserData(&xTexObj, &xTlutObj)` (sdsmall 342-343, hdd 344-345, qoob 346-347, memcard 352-353, usbgecko
355-356). The TexObj globals are at `FBM.c:34-88`; twelve are `extern` in `FrameBufferMagic.h:82-93`. EXT `libogc/tpl.c:153-200`:
`TPL_OpenTPLFromMemory` patches pointers inside the embedded blob in place (no copy, no heap); `TPL_GetTextureCI` returns -1
if the entry has no palette (`tpl.c:290-291`), so a CI loader line must match a CI entry.

### 1.6 The two render paths (decides how alpha must be authored)
- Default path (`drawInit()`, `FBM.c:390-447`): 2 TEV stages, blend `GX_BL_ONE, GX_BL_INVSRCALPHA` (`:441`). Result:
  `rgb = tex.rgb * vtx.rgb * vtx.a`, `a = tex.a * vtx.a`. So vertex colours are straight alpha, but **texture colour must
  already be premultiplied by texture alpha**. I4/I8 are naturally so (alpha = intensity). Stock RGBA art is black where
  alpha is 0 (8 files checked with PIL: no exception) but its translucent edge pixels are not consistently premultiplied
  (dir.tif: 287 of 1118), so the visible cost of straight-alpha art is only slightly bright soft edges.
- Straight-alpha path: only `_DrawTexObjNow` when the texture's mag filter is `GX_NEAR` (`FBM.c:678-681`: 1 TEV stage,
  `GX_BL_SRCALPHA`), plus the game-banner branches (`:1141-1142, 1225-1228, 1274-1277`). A sprite declared
  `minfilt=0 magfilt=0` and drawn with `_DrawTexObjNow`/`DrawTexObj` needs no premultiplication and stays pixel-crisp.

### 1.7 Constraints on a replacement image
| Question | Answer |
|---|---|
| Same name + same `.scf` line | drop-in, zero code change |
| Must dimensions match? | Not technically: texcoords are 0..1 and scale is taken from the texture (`FBM.c:618-620`), so a different size is stretched into the same on-screen rectangle. Keep identical dimensions unless you also edit the draw rectangle. Fixed rectangles: logo 96x32 (`FBM.c:1515`), backdrop 640x480 (`:2273`), menu glyphs (`btns.h`), file icons 96x32 and 72x24 rotated (`:1132-1133,1217-1218,1288-1294`), device pictures = `deviceTexture {id,w,h,realW,realH}` tables inside every driver (e.g. `S/devices/fat/deviceHandler-FAT.c:659`). Entries with baked `ss/ts`/offsets (QOOB, MEMCARD, UNCHECKED, STAR, GCLOADER, GCODE, FLIPPY, `FBM.c:535-612`) must keep their size |
| Power of two? | No (clamp). Only needed for repeat/mirror wrap or mipmaps. Max side 1024 (GX limit, INFERRED; gxtexconv checks it only for mipmaps) |
| Size multiples | Use multiples of 8 (GX blocks: I4/CI4/CMPR 8x8, I8/IA4/CI8 8x4, others 4x4, consistent with EXT `tpl.c:56-84`); gxtexconv silently rescales non-multiples of 4 |
| Alpha | see 1.6. I4/I8 mask art: white = opaque. IA8/RGB5A3/RGBA8 in the default path: transparent pixels MUST be black; premultiply translucent pixels for clean edges |
| Format choice | one-colour glyph tinted in code: I4 (0); soft glow: I8 (1); grey+alpha: IA8 (3); colour+alpha: RGB5A3 (5) or RGBA8 (6); big opaque picture: CMPR (14) or RGB565 (4); paletted: CI4/CI8 + palfmt |
| Changing CI <-> non-CI | requires swapping the loader line (1.5) |
| Memory | texture data lives in the DOL image, no heap. Stock backdrop = 38,400 + 2,560 bytes. 640x480: CMPR 153,600; CI8 307,200; RGB565 614,400; RGBA8 1,228,800 bytes (derived from `tpl.c:56-84`) |

### 1.8 Adding a NEW texture (smallest-conflict way: its own script)
1. Put the art in `S/images/`, e.g. `pawmascot.png`.
2. Create `S/images/pawart.scf` with `<filepath="pawmascot.png" id="pawmascotimg" colfmt=5 wraps=0 wrapt=0 minfilt=0 magfilt=0 />`.
   The wildcard at Makefile:100 picks it up: `build/pawart.tpl`, `build/pawart.h`, `build/pawart_tpl.h` (INFERRED from the
   rules; not built). Alternative: append the line to `images.scf` (IDs are name-based macros, so position does not matter).
3. `FBM.c`: `#include "pawart_tpl.h"` + `#include "pawart.h"`; globals `TPLFile pawTPL; GXTexObj pawmascotTexObj;`; in
   `init_textures()`: `TPL_OpenTPLFromMemory(&pawTPL, (void *)pawart_tpl, pawart_tpl_size); TPL_GetTexture(&pawTPL, pawmascotimg, &pawmascotTexObj);`.
4. Draw it: `DrawTexObj(&pawmascotTexObj, ...)` (event) or `_DrawTexObjNow(...)` (immediate, inside `FBM.c`). Only if you want
   it through `DrawImage`/tinting: append `TEX_PAW...` at the END of `enum TextureId` (`FrameBufferMagic.h:50-80`) and add a
   `case` in `_DrawImageNow`.
Hazards: (a) the script's base name becomes a generated header name: `pawart.scf` -> `pawart.h`; never name a script like a
hand-written header (`pawtation.scf` would generate `pawtation.h` and be shadowed, because source dirs precede `build` on
the include path, Makefile:121-124). (b) every `id` is a global `#define` visible in almost every file: use a unique id
and never reuse it as a C identifier. (c) C file base names must be unique across all `SOURCES` dirs (objects are flat).

### 1.9 Backdrop specifics
- Stock = tile-compressed: `backdrop.png` holds unique 16x16 tiles, `backdrop_ind.png` (40x32 IA8) picks a tile per
  16x16 screen cell (`ss = 640; ts = 480`, `FBM.c:518-521`; `GX_SetTevIndTile(..., 16, 16, 16, 16, ...)`, `:639-641`).
- Stock colour is produced by a TEV trick, not by the art: for a CI texture with IA8 palette (or IA4/IA8) the code sets
  `GX_SetTevColorIn(GX_TEVSTAGE0, GX_CC_TEXA, GX_CC_TEXC, GX_CC_RASC, GX_CC_ZERO)` and `color = {0,0,255,255}` (`:507-513`):
  per channel `out = (1-c)*A + c*I`. Stock palette: I = 65..80, A = 38..55, hence dark navy (R=G=A, B=I). The tint is a
  per-channel selector between two dark values: `{255,0,255}` gives a dark plum (R=B~72, G~46), never a bright pink.
  A pink backdrop needs new art.
- Non-IA formats are drawn as-is in white: CI with RGB565/RGB5A3 palette (`:499-506`) and everything in `default:` (`:514-516`).
- **Zero-code option already in stock Swiss**: `DrawLoadBackdrop(devices[DEVICE_CUR])` (`S/main.c:311`) opens
  `<boot device root>/swiss/backdrop.tpl` (`FBM.c:2285`), picks one texture (by month/weekday/hour/day when the file has
  2,3,4,6,7,12,24,30-31,365-366 textures, else random, `:2295-2328`), loads CI or non-CI (`:2330-2341`) and unlinks the tile
  map (`:2342`). Build it on the PC: `gxtexconv -i backdrop.png -o backdrop.tpl colfmt=14`. Limits: only when a boot device
  initialised; no validation of the file (a corrupt TPL is read as-is, EXT `tpl.c:92-151`: risk of a hang at boot,
  INFERRED; delete the file to recover); texture is heap-allocated (`tpl.c:249`); the handle stays open by design.
- Built-in replacement: change `images.scf` line 1 to a plain 640x480 entry and edit `FBM.c:335-338` (use
  `TPL_GetTexture` for non-CI, and `GX_InitTexObjUserData(&backdropIndTexObj, NULL)` to stop tiling). 2-4 lines.

## 2. Product name, version and credits: every site

| Site | Text / object | Theme action |
|---|---|---|
| `FBM.c:1515` | logo texture `TEX_SWISS` (the title is an IMAGE, not text) | replace art (step 3) or draw text instead |
| `FBM.c:1516` | `drawString(142, 39, "for GameCube", 0.55f, ALIGN_LEFT, defaultColor);` | free slot (quip or "unofficial theme of Swiss") |
| `FBM.c:1517` | `drawString(142, 56, "version 0.6", ...)` | keep the upstream version visible, e.g. "based on Swiss 0.6 r2119" |
| `FBM.c:1519-1520` | `"commit: %s \267 revision: %s", GIT_COMMIT, GIT_REVISION` right-aligned at `fbWidth-36`, y=56 | see note on revision below |
| `FBM.c:1522-1531` | CPU temperature (centre x=`fbWidth-246`, y=39) and clock (right, y=39) | leave |
| `S/gui/info.c:312-322` (page 4/5) | `"Version Info (4/5):"`, `"Swiss version 0.6"` (y115), `"by emu_kidid & Extrems, 2026"` (y140), `"Commit %s; Revision %s"` (y165), `"Built with " _V_STRING` (y190), `"Source/Updates/Issues"` + `"github.com/emukidid/swiss-gc"` (y240/264), `"Web/Support"` + `"www.gc-forever.com"` (y310/334), IRC line (y378) | KEEP all upstream lines. Add fork lines in the free rows y=90, 215, 287, 356 |
| `S/gui/info.c:324-338` (page 5/5) | Patreon supporters, "Extra Greetz", `"...and a big thanks to YOU, for using Swiss!"` | keep unchanged |
| `S/swiss.c:1231` | `"Something went wrong.\nPlease open an issue with your hardware\nconfiguration and Swiss settings."` (inside `load_app`) | recommended 1-string edit: this build must not send anyone upstream (string literal only, no logic) |
| `S/gui/settings.c:73-75,122,271` | tooltips and the label `"Swiss Video Mode:"` | leave (matches the config key) |
| `S/config/config.c:149,156,233,256,285,508,847` | file headers `"# Swiss Configuration File!"`, key `"Swiss Video Mode"` | DO NOT change: file format shared with stock |
| `S/main.c:49-53,332` | `static const dvddiskid Swiss = {"GSWA","GL",...}` compared with the boot disc ID | DO NOT change: functional |
| `S/util.c:175-186` | autoboot names incl. `"*/swiss_r[1-9]*.dol"` | DO NOT change: functional, see 6.3 |
| `S/httpd.c:22,30`, `S/swiss.c:2033`, `print_debug` strings | page title, NKit hint, debug | leave |
| `Makefile:3`, `cube/swiss/Makefile:18`, `buildtools/iso/*.hdr` | `swiss_r<N>` artefact names, `TARGET := swiss`, ISO header "SWISS FOR THE NINTENDO GAMECUBE" | leave; irrelevant for `make dev` |

There is no splash screen and no string table: first frame is backdrop + title bar + menu glyphs (`FBM.c:2271-2278`), then
`"Detecting devices..."` (`S/main.c:442`) and `"Loading settings"` (`S/config/config.c:1306`). Panel headings ("System Info
(1/5):", "Device Selection", "Recent:", "%s Cheats:") do not contain the product name. The UI shows no licence text at
this tag (grep for GPL/licence in `S/gui`, `swiss.c`, `main.c`: none), so a GPL line on the info page is an addition.
Text encoding is the console's ANSI IPL font (Windows-1252 code points; `\267` middle dot, `\260` degree, `\205` ellipsis).

Suggested info page 4/5 (all upstream lines stay; four additions): y90 `"Pawtation - unofficial personal theme"`;
y115 keep `"Swiss version 0.6"` (prefix "Based on " if wanted); y215 `"Swiss is free software under the GNU GPL v2 (see LICENSE)"`;
y287 `"Unofficial build: do not report problems to the Swiss project"`; y356 `"Theme changes: cosmetic only"`.

Revision note: `GIT_REVISION` = `git rev-list HEAD | wc -l` (`cube/swiss/Makefile:60`). In a shallow clone it is `1`
(verified in this clone); in a full clone of the tag it should be 2119 (INFERRED from the tag name); every theme commit
adds 1, so the fork would display a number that looks like a newer official revision. Put the base in a theme constant
(`"r2119"`) and label the live value as the fork's. `GIT_REVISION` is display-only (`FBM.c:1519`, `info.c:315`, `main.c:290`);
`GIT_COMMIT` is functional (6.3).

## 3. Colours

All look-defining colours are in two files. Outside them the UI only uses the globals `defaultColor` (about 165 uses in
`swiss.c`, `info.c`, `settings.c`, `mp3.c`, `wkf.c`, `FBM.c`) and `deSelectedColor` (9 uses). `swiss.c`, `settings.c`,
`info.c` and all drivers contain no colour literal (grep), so a palette never needs to touch them.

| Widget | Function | Line | Literal (r,g,b,a) | Role |
|---|---|---|---|---|
| Text | `S/gui/IPLFontWrite.c` globals | 21 | `defaultColor` {255,255,255,255} | all normal text |
| | | 23 | `deSelectedColor` {80,80,73,255} | disabled / unselected text |
| | | 22 | `disabledColor` {175,175,182,255} | unused (grep) |
| | `DrawFadingLabel` | FBM 1085 | {255,255,255,0} | "Press (Y) for help", alpha animated |
| Panel alpha | `#define GUI_MSGBOX_ALPHA 225` | FBM 32 | | one knob for all panel translucency |
| Panel border (silver) | `_DrawProgressBar` 740, `_DrawMessageBox` 861, `_DrawSelectableButton` 898, carousel 1125, file row 1264, `_DrawEmptyBox` 1436, `_DrawTransparentBox` 1483, `_DrawVertScrollBar` 1623 | | {200,200,200,225} x8 | every rounded border |
| Panel fill (black) | `_DrawProgressBar` 738, `_DrawMessageBox` 860, `DrawEmptyBox` 1453, keyboard key 2001 | | {0,0,0,225} x4 | message boxes, settings/info/dialog panels |
| Progress bar | `_DrawProgressBar` | 741 | {255,128,0,225} | determinate bar (orange) |
| | | 742 | {0xb3,0xd9,0xff,225} | indeterminate bar (light blue) |
| | | 749 | {255,255,255,miniModeAlpha} | "Loading..." spinner + label |
| Selected button | `_DrawSelectableButton` | 896 | {96,107,164,225} | Back/Next/Save, recent list |
| Keyboard key | `DrawGetTextEntry` | 2001 | {96,107,164,225} / {0,0,0,225} | selected / idle key |
| Tooltip | `_DrawTooltip` | 950, 951 | border+text {255,255,255,255}; fill {122,122,122,255} | help boxes, device details |
| File row | `_DrawFileBrowserButton` | 1263 | {46,57,104,225} | selected row (standard + fullwidth) |
| Carousel card | same | 1124 | {0,0,0,128} | card fill |
| Scrollbar | `_DrawVertScrollBar` | 1621 | {46,57,104,225} | thumb |
| Title bar | `_DrawTitleBar` | 1510 | {0,0,0,128} | top bar fill, no border |
| Menu bar | `_DrawMenuButtons` | 1547 | {255,255,255,51} | bottom bar fill |
| Menu glow | `_DrawImageNow` `TEX_BTNHILIGHT` | 564 | {127,134,255,255} | selected menu glyph |
| Menu glyphs, logo, colour art | `_DrawImageNow` default | 494 | {255,255,255,255} | shared default: also multiplies device art and a full-colour backdrop |
| Backdrop | `_DrawImageNow` `TEX_BACKDROP` | 512 | {0,0,255,255} | channel selector, see 1.9 |
| Checkbox / star | `_DrawImageNow` | 582, 585, 589 | {0,128,0}, {87,87,87}, {255,255,0} | checked, unchecked, autoload star |
| Device pictures (I4) | `_DrawImageNow` | 541,547,593,600,603,607,610,614 | {216,216,216,255} x8 | WODE, WiiKey, GC Loader, ETH2GC, Flippy, GCNET, GCode, KunaiGC |
| No-op | 739, 897, 1262, 1500, 1511, 1548, 1622 | | {0,0,0,0} | "no fill"/"no border" |
| EFB clear | `S/video.c:265` (`:254-255` XFB) | | {0,0,0,255} / `COLOR_BLACK` | only visible in black (cubeboot) mode |

Dead code: `BUTTON_COLOUR_INNER 0x2088207C` / `BUTTON_COLOUR_OUTER COLOR_SILVER` (`FrameBufferMagic.h:22-23`) are unused;
`_DrawMessageBox` ignores its `D_WARN/D_INFO/D_FAIL/D_PASS` type (`FBM.c:854-864`): all message boxes look the same.

Data-driven (not reachable by a palette): game banners read from the disc image; file-type icons and region flags
(colours baked into RGBA art, 12 files); device pictures (grey art, per-device `deviceTexture` tables); row alpha 128 for
hidden/dot files (`FBM.c:1407`); caret colour copies the label colour (`:1046`).

Best seam: one new header `S/gui/pawtation_theme.h`, included by `FBM.c` and `IPLFontWrite.c` only (every `SOURCES` dir is
on the include path, `cube/swiss/Makefile:54`). Write macros in the stock form so they also work as static initialisers:
```c
#define PAW_TEXT          (GXColor){255,255,255,255}              /* IPLFontWrite.c:21 */
#define PAW_PANEL_BORDER  (GXColor){200,200,200,GUI_MSGBOX_ALPHA}  /* 8 sites */
#define PAW_SELECT_ROW    (GXColor){46,57,104,GUI_MSGBOX_ALPHA}    /* 1263, 1621 */
```
Call sites that change: 46 literals on 45 lines in `FBM.c` (38 if the seven no-op `{0,0,0,0}` stay) + 3 lines in
`IPLFontWrite.c` + 2 `#include`s. About 20 named colours cover everything. To tint only the logo and menu glyphs, set
`color` inside their own `case`s (`FBM.c:523-525, 566-580`) rather than changing the shared default at 494.
Readability traps: text is white on the selection fills (896, 1263), and `deSelectedColor` is dark grey on black panels;
changing fills without re-checking both text colours can make text unreadable.

## 4. UI drawing API (`FBM.c`, `FrameBufferMagic.h:106-143`, `IPLFontWrite.c/h`)

Model. `uiDrawObj_t { int type; void *data; struct uiDrawObj *child; bool disposed; }` (`FrameBufferMagic.h:43-48`).
`child` is a single chain, not a tree: `DrawAddChild(parent, child)` appends at the END of the parent's chain
(`FBM.c:2225-2238`); draw order = insertion order (`videoDrawEvent` recursion, `:2102-2151`). Root objects live in the
linked list `videoEventQueue` (`:223-250`). Constructors only allocate; nothing is visible until published.
| Call | Line | Meaning |
|---|---|---|
| `uiDrawObj_t* DrawPublish(uiDrawObj_t *evt)` | 2240 | append a root object (drawn above earlier roots) |
| `uiDrawObj_t* DrawRepublish(uiDrawObj_t *old, uiDrawObj_t *new)` | 2248 | mark `old` disposed + append `new` (flicker-free swap; every screen redraw does this) |
| `void DrawDispose(uiDrawObj_t *evt)` | 2259 | mark disposed; the video thread frees the object, its chain and its strdup'ed strings next frame (`clearNestedEvent`, `:252-305`) |
| `uiDrawObj_t* DrawContainer()` | 1110 | invisible grouping node |
| `DrawEmptyBox(x1,y1,x2,y2)` / `DrawEmptyColouredBox(...,GXColor)` / `DrawTransparentBox(...)` | 1442 / 1461 / 1489 | panel; grows by 3 px (height <= 30) or 10 px, then `_DrawSimpleBox` adds 4 px per side |
| `DrawMessageBox(int type, const char *msg)` / `DrawProgressBar(bool indeterminate, int percent, const char *msg)` / `DrawProgressLoading(int pos)` | 867 / 820 / 843 | fixed 600x125 centred box; "\n" splits lines |
| `DrawSelectableButton(x1,y1,x2,y2,msg,mode)` / `DrawTooltip(const char*)` / `DrawVertScrollBar(...)` | 924 / 979 / 1632 | |
| `DrawStyledLabel(int x,int y,const char *s,float size,int align,GXColor c)` / `DrawLabel(x,y,s)` / `DrawFadingLabel(x,y,s,size)` | 1018 / 1051 / 1072 | string is copied (strdup) |
| `DrawDynamicLabel(int x,int y,const char *(*getString)(void),float size,int align,GXColor c)` | 1094 | callback evaluated EVERY frame on the video thread; return static storage; NULL = draw nothing |
| `DrawImage(int textureId,x,y,w,h,depth,s1,s2,t1,t2,centered)` | 656 | built-in texture by `enum TextureId`, tinted per id |
| `DrawTexObj(GXTexObj*,x,y,w,h,depth,s1,s2,t1,t2,centered)` | 710 | any texture, any rectangle, any sub-rectangle; vertex colour fixed white |
| `DrawFileBrowserButton[Meta]`, `DrawFileCarouselEntry` | 1338-1430 | file rows/cards (copy the file handle + banner) |
| `DrawTitleBar()` / `DrawMenuButtons(int sel)` / `DrawUpdateMenuButtons(int sel)` | 1535 / 1571 / 1599 | persistent chrome |

Persistent chrome is assembled once in `DrawInit(GXRModeObj*, bool black)` (`FBM.c:2266-2281`, called from `Initialise()`
`S/main.c:138`): `container = DrawContainer()`; unless `black` (cubeboot mode): `DrawImage(TEX_BACKDROP, 0,0,640,480,...)`,
`DrawTitleBar()`, `buttonPanel = DrawMenuButtons(MENU_NOSELECT)`; `DrawPublish(container)`; then the thread starts. This
first root is never freed (`disposeEvent` skips the first queue node, `:313-314`). The per-frame bodies are
`_DrawTitleBar` (`:1508-1532`) and `_DrawMenuButtons` (`:1543-1567`). The file area is rebuilt by `renderFileBrowser` /
`renderFileCarousel` / `renderFileFullwidth` (`S/swiss.c:308, 542, 718`) through `drawFiles*` (`:261, 472, 682`).

Render thread. `videoUpdate` (`FBM.c:2163-2223`), created by `LWP_CreateThread(..., video_thread_stack, VIDEO_STACK_SIZE,
VIDEO_PRIORITY)` (`:2280`): 64 KB static stack, `LWP_PRIO_HIGHEST` (`:93-95`). Each pass: lock `_videomutex`, free disposed
objects, for every root `drawInit()` + draw + chain, `GX_CopyDisp`, unlock, `VIDEO_Flush(); VIDEO_WaitForFlush()` (one pass
per video frame). It keeps running while the main thread blocks in I/O. `DrawShutdown()` (`:2355-2364`) joins it before a
game or DOL starts. The mutex is `static`: other files can only reach it through the `Draw*` calls.

Time / animation. There is NO frame counter (the `frames` lines are commented out, `:2166-2171`). Available: 
`VIDEO_GetRetraceCount()` (u32 vsync counter, used at `S/swiss.c:320`), `VIDEO_GetRetraceRate()` (libogc2, `swiss.c:432`),
`gettime()` + `ticks_to_millisecs()`/`diff_msec()` (`<ogc/lwp_watchdog.h>`, already included at `FBM.c:19`), `time()` (RTC,
`:1527-1531`). Precedents for per-frame state stored in the object: spinner `data->percent += 2` (`:751`), label fade
`data->color.a += fadingDirection` (`:1008-1012`), caret blink (`:1000-1004`).

Textured quad at any position/size with alpha:
- Immediate, inside `FBM.c`, tinted with alpha (default path): `GX_InvalidateTexAll(); GX_LoadTexObj(&tex, GX_TEXMAP0);
  _drawRect(x, y, w, h, 0, (GXColor){r,g,b,a}, s0, s1, t0, t1);` exactly as the spinner does (`:758-760`). `_drawRect`
  is `static void _drawRect(int x,int y,int width,int height,int depth,GXColor color,float s0,float s1,float t0,float t1)` (`:449`).
- Immediate, texture alpha only: `static void _DrawTexObjNow(GXTexObj *texObj,int x,int y,int width,int height,int depth,
  float s1,float s2,float t1,float t2,int centered)` (`:676`). Call `drawInit()` first when text was drawn before it
  (precedent `:1188-1189`); it leaves 1 TEV stage / SRCALPHA blending behind when the texture is NEAR-filtered, so draw it
  last or call `drawInit()` again.
- Coordinates: fixed logical 640x480 (`guOrtho(..., 0, 480, 0, 640, ...)`, `:403`); x right-alignment uses
  `getVideoMode()->fbWidth`. Depth is unused (Z test off, `:406`); order alone decides overlap.

Text (`S/gui/IPLFontWrite.c`). Font = console IPL ROM font, ANSI (`init_font`, `:25-32`); no bundled font.
`void drawString(int x,int y,const char *string,float scale,int align,GXColor fontColor)` (`:94-144`): `y` is the vertical
CENTRE of the line, `x` is left/centre/right per `ALIGN_LEFT 0 / ALIGN_CENTER 1 / ALIGN_RIGHT 2`; `scale` multiplies the
glyph cell (cell height 24 px at 1.0 is INFERRED; stock uses 0.45-1.0); stops at `'\n'` (`:122`); `NULL` is ignored;
characters outside the font map to its "invalid" glyph (EXT `libogc/system.c:1519`). No built-in max width; helpers:
`int GetTextSizeInPixels(const char*)` (at scale 1), `float GetTextScaleToFitInWidth(const char*, int width)`,
`float GetTextScaleToFitInWidthWithMax(const char*, int width, float max)`, `int GetFontHeight(float)`, and
`drawStringEllipsis(x,y,s,scale,align,color,rotateVertical,maxSize)` (`:228-302`, truncates with "...").

Where a mascot + quip fits (title bar is the only chrome shared by all three browser layouts):
- Title bar box: `_DrawSimpleBox(19, 17, 602, 62, ...)` (`FBM.c:1513`) = x 15..625, y 13..83. Row 1 centre y=39, row 2 y=56.
- Occupied: logo x 36..132, y 32..64; left text from x=142; right-aligned blocks end at x=604; temperature centred at x=394.
  Free middle is roughly x 240..370 (INFERRED: glyph widths come from the console ROM and could not be measured).
- Full-screen panels (settings `S/gui/settings.c:194`, info `S/gui/info.c:124`, text entry `FBM.c:1971`) start at
  y=60 -> visible edge y=46: only row 1 (y < 46) is truly always visible; row 2 and the lower half of the logo sit under
  those panels (alpha 225). The stock logo has the same behaviour.
- Bottom bar: glyph slots at x = 48 + i*119 (68 wide), box from y=422; no room for a line of text.
- Standard browser only: free rectangle x 20..145, y 345..420 under the device info box (`S/swiss.c:144-214`); it is
  covered by rows in fullwidth/carousel layouts (`:445, 682-716`).
Recommended hook: add the mascot + quip at the end of `_DrawTitleBar` (after `FBM.c:1531`). It runs every frame on the
video thread, inherits the title bar's lifetime (absent in black mode, never disposed), and needs no new event type.
Reuse the `"for GameCube"` slot (`:1516`, x=142, y=39, always visible) for the quip with
`GetTextScaleToFitInWidthWithMax(quip, <width>, 0.55f)`, and move the attribution text to row 2.
Alternative with zero changes to the draw code (no animation): after loading, publish `DrawContainer()` +
`DrawTexObj(&pawmascotTexObj, ...)` + `DrawDynamicLabel(..., paw_quip_current, ...)` once with `DrawPublish` from
`S/main.c`; it sits above the base chrome and below every later panel.

## 5. File I/O at menu time

API (`S/devices/deviceHandler.h`): `file_handle` (`:55-72`; `char name[PATHNAME_MAX]` = 1024 bytes, absolute path such as
`sdb:/dir/file`; struct is about 1.2 KB, so heap or static, not casual stack use); `DEVICEHANDLER_INTERFACE` function
pointers (`:188-219`): `s32 statFile(file_handle*)`, `s64 seekFile(file_handle*, s64, u32)`,
`s32 readFile(file_handle*, void*, u32)`, `s32 closeFile(file_handle*)`; root = `device->initial->name` (`sda:/`, `sdb:/`,
`sdc:/` in `S/devices/fat/deviceHandler-FAT.c:35-51`); slots `devices[DEVICE_CUR|PREV|DEST|CHEATS|CONFIG|PATCHES]` (`:221-229`).
Path helper: `size_t concat_path(char *pathName, const char *dirName, const char *baseName)` (`S/files.c:149-173`, bounded
by `PATHNAME_MAX`, inserts the slash). Stock conventions, all relative to the device root: `swiss/settings/global.ini`,
`swiss/settings/recent.ini`, `swiss/settings/game/%.4s.ini` (`S/config/config.c:53-58,1291`), `swiss/cheats/`,
`swiss/patches/`, `swiss/backdrop.tpl`. FatFs has long file names and exFAT on (`S/fatfs/ffconf.h:116-117,247`), names are
case-insensitive, so `pawtation/quips.txt` is a valid path.

How the settings code reads a small text file (`config_file_read`, `config.c:98-113`):
```c
file_handle *configFile = (file_handle*)calloc(1, sizeof(file_handle));
concat_path(configFile->name, devices[DEVICE_CONFIG]->initial->name, filename);
if(!devices[DEVICE_CONFIG]->statFile(configFile) && configFile->size) {
	readBuffer = (char*)calloc(1, configFile->size + 1);
	if (readBuffer) {
		devices[DEVICE_CONFIG]->readFile(configFile, readBuffer, configFile->size);
		devices[DEVICE_CONFIG]->closeFile(configFile);
	}
}
free(configFile);   /* returns NULL when the file is missing or empty */
```
It is only valid between `config_set_device()` (`:61-89`, picks the device from the SRAM-stored id and mounts it) and
`config_unset_device()` (`:91-95`, UNMOUNTS it again when it is not the browse device); `config_init` wraps exactly that
(`:1304-1347`). Do not copy three of its habits: no size cap, `readFile` result ignored, `statFile` assumed to exist
(e.g. the DVD, Qoob, USB Gecko and WODE handlers set no `statFile`; `S/swiss.c:1372` guards it).

Which device, and when. Use `devices[DEVICE_CUR]` passed as a parameter at `S/main.c:311`, i.e. right where stock calls
`DrawLoadBackdrop(devices[DEVICE_CUR])`. Start-up order in `main()`: `:275 Initialise()` (UI and video thread up, no
storage yet) -> `:293-302` first available `FEAT_BOOT_DEVICE` becomes `DEVICE_CUR` -> `:305` `init()` mounts it ->
`:306-308` `load_auto_dol` -> `:311` backdrop -> `:316` device scan -> `:319` `config_init`. At `:311` the boot device is
mounted and stays mounted. `DEVICE_CONFIG` is the wrong choice: it may be a different device, may be `NULL`, and is left
unmounted after each config operation. Never cache the pointer: `menu_loop` sets `devices[DEVICE_CUR] = NULL` and
deinitialises it when the user switches device (`S/swiss.c:2820-2827`), and autoload can switch it (`S/util.c:294-302`).
Read once at boot into RAM. If no boot device initialised, the call site is skipped: fall back to built-in quips.

Recommended sequence = the stock `.cli` reader (`S/swiss.c:1391-1414`), which works on every device with `readFile`:
```c
if(dev->readFile(fh, NULL, 0) == 0 && fh->size) {      /* opens lazily, fills size; missing file -> -1 */
	u32 n = fh->size < PAW_QUIPS_MAX ? fh->size : PAW_QUIPS_MAX;   /* cap, never trust size */
	dev->seekFile(fh, 0, DEVICE_HANDLER_SEEK_SET);
	s32 got = dev->readFile(fh, buf, n);               /* check got > 0, then buf[got] = 0 */
}
dev->closeFile(fh);                                    /* stock calls it unconditionally (swiss.c:1413) */
```
Missing file on FAT: `f_open` fails, the handler frees its own allocation and returns -1 (`deviceHandler-FAT.c:171-177`);
`closeFile` is a no-op when nothing is open (`:368-376`). Nothing leaks, no dialog appears. `FILE* openFileStream(file_handle*)`
(`S/devices/deviceHandler.c:338-347`, `funopen` wrapper, NULL when missing/empty) is the stdio alternative used by the backdrop loader.

Limits to respect: main thread stack 128 KB (EXT `libogc/lwp.c:92,184`); video thread stack 64 KB; FatFs puts its
long-name buffers on the caller's stack (`ffconf.h:116`, `FF_USE_LFN 2`); heap = arena up to `0x81700000` shared with DOL
and game loading (`cube/linker-script/ogc.ld:15`, `S/main.c:287` prints it). The global `txtbuffer[2048]` (`S/swiss.c:64`)
is main-thread scratch that `DrawMessageBox`/`DrawProgressBar` also write (`FBM.c:828,876`): never use it from the video
thread; `fbTextBuffer[256]` (`FBM.c:90`) is the video thread's scratch. Do file I/O only on the main thread at boot,
never inside a draw function or a `DrawDynamicLabel` callback (they run under the video mutex at highest priority).

## 6. Risk map

### 6.1 Never touch for a cosmetic theme
| Path | Why |
|---|---|
| `cube/patches/**`, `S/patches/**`, `S/patcher.c` (18k lines), `cube/reservedarea.h`, `cube/reservedarea.ld`, `cube/linker-script/`, `cube/asm.h`, `cube/PowerPC.h` | in-game patch code, patch tables and the fixed low-memory layout shared with running games |
| `S/devices/**`, `S/fatfs/**`, `S/littlefs/` (submodule), `S/exi.c`, `S/bba.c` | drivers and filesystems |
| `S/gcm.c`, `S/nkit.c`, `S/elf.c`, `S/aram/**`, `S/cheats/**`, `S/gameid.c`, `S/rt4k.c`, `S/wiiload.c`, `S/httpd.c`, `S/mp3.c` | disc image parsing, DOL/ELF loading, cheats engine, hash tables (`valid_dol_xxh3`, `S/nkit.c:2855`) |
| `S/config/**`, `S/files.c`, `S/util.c`, `S/video.c`, `S/input.c` | settings format + SRAM, directory scan, autoboot, video mode switching |
| `cube/packer/**`, `wii/**`, `pc/**`, `buildtools/**`, top-level `Makefile` | packaging; not needed for a private `make dev` build |
Allowed edits: `S/gui/FrameBufferMagic.c`, `S/gui/IPLFontWrite.c`, `S/gui/info.c`, art under `S/images/`, new files in
`S/gui/`, one call + one include in `S/main.c`, one string literal in `S/swiss.c:1231`.

### 6.2 Where UI and loader logic are entangled
1. `S/swiss.c` mixes renderers (`:143-855`) with `load_app` (`:1008`), `boot_dol` (`:1303`), `verify_game` (`:1898`), `load_file` (`:2276`), `check_game` (`:2375`). Draw calls sit inside loader functions; edit strings there only if needed.
2. `DrawFileBrowserButton` (`FBM.c:1338-1414`) deep-copies `file_handle`, `file_meta` and the banner and evaluates the autoload pattern; `clearNestedEvent` frees them. Recolour only (`:1124-1125, 1262-1264`).
3. `DrawArgsSelector`, `DrawCheatsSelector`, `DrawGetTextEntry` (`FBM.c:1678-2099`) contain input loops that write loader state (DOL parameters, enabled cheats, `swissSettings.wiirdDebug`, settings strings). Only line 2001 is cosmetic.
4. Drivers reference the UI enum: `deviceTexture = {TEX_..., w, h, realW, realH}` in every device handler. Never reorder or remove `enum TextureId` entries; append only. Keep device picture sizes.
5. `S/devices/filemeta.c:266-437` uses the `extern` file-icon/flag TexObjs; keep their names.
6. `DrawInit` also starts pad scanning and sets the video mode; `DrawShutdown` must be able to join the video thread before any game starts: add no threads, no blocking calls and no I/O to the draw path.
7. Shared globals: `txtbuffer`, `swissSettings`, `curDir`, `devices[]` (see section 5).
8. `DrawLoadBackdrop` swaps the backdrop TexObj from the main thread without taking the video mutex (stock behaviour); do not imitate that for theme state: build completely, then publish with one final assignment.

### 6.3 Identity strings that are functional (the non-obvious trap)
`load_auto_dol` (`S/util.c:187-228`, run at boot for every `FEAT_AUTOLOAD_DOL` device incl. SD, `S/main.c:306`) scans the
boot device root for `*/swiss_r[1-9]*.dol`, `sd[abc]:/[abxyz].dol`, `start.dol`, `ipl.dol`, `sd[ab]:/AUTOEXEC.DOL`,
`*/boot.dol`, `*/boot2.dol` (`:175-186`) and chain-boots a match when
`(pattern starts with '*' && trailer < 7 bytes) || (trailer >= 7 && trailer != GIT_COMMIT && trailer not in tags.h)` (`:209-211`).
The trailer is the short commit hash that the release target appends to the DOL (`Makefile:82,85,87`); `tags.h` is generated
from `git for-each-ref refs/tags` (`cube/swiss/Makefile:172-175`). Consequences for the fork (INFERRED from the code, not run):
- A `make dev` DOL has NO trailer. If it sits in the boot device root as `boot.dol`, `boot2.dol` or `swiss_r*.dol`, it
  matches a `*` pattern and re-boots itself: a boot loop. Robust fix: append the hash exactly like `Makefile:82` (own
  hash = never self-booted). Untrailered files are only safe under the non-`*` names (`AUTOEXEC.DOL`, `ipl.dol`, ...).
- Keep the upstream tag refs in the private repo: with `v0.6r2119` present, `tags.h` contains `"163f8b1"` (verified here)
  and the themed build will not chain-boot an official `swiss_r2119.dol` lying on the card. Without tags it would.
- Stock Swiss started first will chain-boot a themed DOL using one of those names (different or missing trailer).
Also functional, never "rebrand": `GIT_COMMIT`, the `swiss/` directory names, config keys, the `GSWA`/`GL` disc ID.

### 6.4 Rules inherited from the owner's decision
Local commits only, never `git push`; nothing sent upstream. The inherited workflow
`.github/workflows/continuous-integration-workflow.yml` triggers `on: [push, pull_request, workflow_dispatch]`; it can only
run if the fork is ever pushed to a hosted remote, which the rules exclude. Keep `LICENSE` and upstream credits intact;
label the build unofficial in the title bar and on the info page.

## 7. Build facts at the tag

| Topic | Fact |
|---|---|
| Top-level targets (`Makefile:42-205`, `.NOTPARALLEL`) | `all` (:45) = clean compile-patches compile compile-packer build recovery-iso build-AR build-gci build-ipl build-wii build-geckoserver package; `dev` (:48) = clean compile-patches compile; `clean` (:50), `compile-patches` (:59), `compile` (:62), `compile-packer` (:66), `build` (:71), `recovery-iso` (:122), `package` (:130), `build-AR` (:164), `build-gci` (:171), `build-geckoserver` (:179), `build-ipl` (:186), `build-wii` (:199) |
| `compile` precondition | `Makefile:63` runs `$(PACMAN) -Q <12 packages>` first (list at top of this file); it fails where dkp-pacman does not know them. `make -C cube/swiss` skips that check (after one `make compile-patches`) |
| `compile-patches` | builds `cube/patches` and writes generated `*.bin.s` / `*_bin.h` into `S/patches/` (`cube/patches/Makefile:10`, git-ignored). Required once: `S/main.c:34` includes `stub_bin.h` |
| Revision | `REVISION = git rev-list HEAD \| wc -l`, `SVN_REVISION = swiss_r$(...)` (`Makefile:2-3`); in C: `-D'GIT_COMMIT="$(git rev-parse --short HEAD)"' -D'GIT_REVISION="$(git rev-list HEAD \| wc -l)"'` (`cube/swiss/Makefile:60`). Needs a git work tree; a shallow clone yields `1` (verified); upstream CI uses `fetch-depth: 0` and `submodules: true` |
| Submodule | `S/littlefs` (`.gitmodules`) is empty in a plain clone: `git submodule update --init` |
| Outputs | `make dev`: `cube/swiss/swiss.dol` + `swiss.elf` (`TARGET := swiss`, `OUTPUT := $(CURDIR)/$(TARGET)`, `cube/swiss/Makefile:18,84`), intermediates (incl. `swiss.elf.map`) in `cube/swiss/build/`. `make all`: `swiss_r<N>/` tree + `.7z` + `.tar.xz` (`Makefile:130-160`); `DOL/swiss_r<N>.dol` is the xz-packed DOL from `cube/packer` with the commit hash appended (`:81-82`) |
| Flags | `CFLAGS = -g -O2 -Wall -Wno-format-truncation -Wno-scalar-storage-order -fno-strict-aliasing -D_GNU_SOURCE $(MACHDEP) $(INCLUDE) <pkg-config cflags> -DGIT_COMMIT -DGIT_REVISION -DLFS_MULTIVERSION` (`cube/swiss/Makefile:60`); EXT `MACHDEP = -DGEKKO -mogc -mcpu=750 -meabi -mhard-float`. No `-Werror`. GNU C extensions are in use (nested functions `S/gui/info.c:276-309`, `<stdcountof.h>` `S/util.c:3`): needs the current devkitPPC (INFERRED) |
| Link | `-T ../../linker-script/ogc.ld -T ../../reservedarea.ld` (`:64`); load address `0x80003100`, `__Arena1Hi = 0x81700000` (`cube/linker-script/ogc.ld:11,15`) |
| Source list | WILDCARD per directory: `CFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))` (`:95`). A new `S/gui/pawtation.c` is compiled and linked with no Makefile edit. A new directory would have to be added to `SOURCES` (`:20-50`): do not create one |
| Include path | `INCLUDES := include $(SOURCES) ..` (`:54`) + `build/` (`:123`) |
| Art tools | `gxtexconv` + `bin2s` only (1.1). Optional and outside the build: any editor that exports PNG; a premultiply step if translucent colour art goes through the default path (1.6) |

## 8. Minimal patch plan (4 steps, each builds and can be checked alone)

| Step | Files | Purpose | Est. lines |
|---|---|---|---|
| 1 Palette | ADD `S/gui/pawtation_theme.h` | named colours + `PAWTATION` switches, stock values first | ~45 new |
| | EDIT `S/gui/FrameBufferMagic.c` | `#include`; replace 38-46 colour literals (table in section 3) | ~40 changed |
| | EDIT `S/gui/IPLFontWrite.c` | `#include`; `defaultColor`, `deSelectedColor` (`:21-23`) | ~3 changed |
| 2 Strings | EDIT `S/gui/pawtation_theme.h` | `PAW_NAME`, `PAW_BASE "Swiss 0.6 r2119"`, unofficial label | ~6 new |
| | EDIT `S/gui/FrameBufferMagic.c` | title bar text `:1516-1519` | 3 changed |
| | EDIT `S/gui/info.c` | page 4/5: keep upstream lines `:313-322`, add fork/GPL/unofficial lines | ~5 added, 0-1 changed |
| | EDIT `S/swiss.c` | `:1231` message must not send the user to upstream | 1 changed |
| 3 Art | REPLACE `S/images/swiss.tif` | "Pawtation" wordmark, same 96x32 I4 -> no code; tint via the `TEX_SWISS` case | 0-1 changed |
| | backdrop, option A | `swiss/backdrop.tpl` on the SD card, built with `gxtexconv` on the PC | 0 |
| | backdrop, option B | REPLACE `S/images/backdrop.png`, EDIT `images.scf:1` and `FBM.c:335-338` | 3-5 changed |
| | optional | menu glyphs (same sizes), `btnhilight`, 9 file-type icons (recolour baked text) | 0 |
| 4 Mascot + quip | ADD `S/images/pawmascot.png`, `S/images/pawart.scf` | sprite strip, e.g. 4 frames of 32x32 = 128x32, RGB5A3, clamp, near/near | 1 line + art |
| | ADD `S/gui/pawtation.c`, `S/gui/pawtation.h` | `void paw_init(DEVICEHANDLER_INTERFACE *dev); const char *paw_quip_current(void); int paw_mascot_frame(void);` built-in fallback quips | ~150 new |
| | EDIT `S/gui/FrameBufferMagic.c` | 2 includes, `TPLFile`/`GXTexObj` globals, 2 lines in `init_textures()`, ~10 lines at the end of `_DrawTitleBar` | ~16 added |
| | EDIT `S/main.c` | include + `paw_init(devices[DEVICE_CUR]);` next to `:311` | 2 added |
Totals in existing upstream files: about 75 changed/added lines in 5 files (`FrameBufferMagic.c`, `IPLFontWrite.c`,
`info.c`, `swiss.c`, `main.c`) plus binary art; everything else is new files. Upstream rebases should then conflict mostly in
`FrameBufferMagic.c`.

Checks per step: 1 = build with stock values gives an identical-looking UI, then change values one at a time and look at
file browser (3 layouts), settings, info, a tooltip (Y on a setting), a message box, the on-screen keyboard, device
select, progress bar. 2 = title bar + info page 4/5 show both names, the upstream authors and URL. 3 = logo and backdrop
in all video modes. 4 = boot with: no `pawtation/` folder; empty file; one line; 40 lines; 500 lines; a line of 300
characters; a renamed JPEG; CRLF endings; card removed. Test in Dolphin with an SD image first (INFERRED that the menu
runs there), then on the console with an untrailered DOL under a safe name (6.3).

Step 4 failure-tolerance rules (all must hold):
1. One read, at boot, on the main thread, at one call site after the boot device's `init()` returned 0. No retry, no I/O in any draw function or label callback, no I/O after the menu starts.
2. Guard `dev`, `dev->initial`, `dev->readFile`, `dev->seekFile`, `dev->closeFile` for NULL; do not require `statFile`.
3. Missing file, read error, zero length, or zero valid lines -> silently use the built-in quips. Never show a message box, never wait for a button, never `print` to the screen: the theme path cannot block boot.
4. Hard caps: read at most 4096 bytes whatever the file size (never allocate by `fh->size`); at most 40 lines; at most about 60 characters per line (truncate), then auto-fit with `GetTextScaleToFitInWidthWithMax`.
5. No heap for content: `static char buf[4096 + 1]`, `static const char *lines[40]` pointing into it, and a `static file_handle` (or calloc + free on every path). Nothing is ever freed or reallocated after boot -> no leak, no dangling pointer for the video thread.
6. Check the `readFile` return value; terminate at `buf[got]`.
7. Sanitise: split on CR/LF; trim; skip blank lines and lines starting with `#`; accept only bytes 0x20-0x7E; if the buffer contains a NUL or more than a few non-printable bytes, treat the file as binary and ignore it completely.
8. Always `closeFile()` after the open attempt (frees FatFs' file object); never write, create or rename anything on the card.
9. Publish last: fill `buf`/`lines` completely, then store the line count in one final assignment; the draw side reads the count once per frame and treats 0 as "use built-ins".
10. Draw side: only read-only state plus `VIDEO_GetRetraceCount()`; no `sprintf` into `txtbuffer`; handle a NULL quip; restore GX state with `drawInit()` before the sprite and draw the sprite last.
11. Compile-time switch (`#define PAWTATION_MASCOT 1`) so step 4 can be turned off to bisect a problem.
12. Skip everything when `swissSettings.cubebootInvoked` is set (black mode has no title bar; harmless either way).

## 9. INFERRED items and things not determined
INFERRED (reasoned, not read at the tag or not run): bin2s symbol names; IPL font cell height 24 and all text-width
estimates; that the installed `gxtexconv`/libogc2 behave like the current external sources read here; full-clone revision
= 2119; auto-pickup of a second `.scf`; the self-boot-loop for untrailered `boot.dol`/`boot2.dol`/`swiss_r*.dol`; a
corrupt `swiss/backdrop.tpl` hanging boot; that a built DOL ends exactly at its last section (no padding read as a
trailer); GX 1024 limit and block sizes; Dolphin as a test bed; compiler version requirement.
Not determined: (1) real glyph metrics, hence the exact free width in the title bar and the scale a 40-character quip
gets; (2) size of the built DOL and any size limit of the owner's boot chain (packed vs unpacked DOL); nothing was
compiled, so "builds" is by reading only; (3) how linear filtering behaves on the CI backdrop when scaled; (4) whether the
packaging targets (`make all`) work in a fork without the full package set; (5) behaviour on real hardware of anything in
this map.
