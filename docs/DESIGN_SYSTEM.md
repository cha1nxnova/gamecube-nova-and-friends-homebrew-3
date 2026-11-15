# Pawtation design system

Brief for the GUI engineer. The tokens live in `data/theme.json`, with a built-in copy in `pawtation/theme.py`
(`theme.load(name)` returns the colour roles, `theme.tokens()` the rest). The GUI takes every colour, size,
font and duration from there: no hex literals in `gui.py`. Preview: `art/out/theme_preview.html` (rendered to
`art/out/theme_preview.png`, plus `stage_*.png`). The preview is an HTML approximation, not real tkinter.

All numbers below were measured with `theme.contrast()` (WCAG 2.x). `python3 -m pawtation.theme` prints the
full audit; `tests/test_theme.py` enforces it.

---

## 1. Principles

1. **The mascots drive it.** Pink is Nova's sticker edge, blue is his eyes, gold is Duskie and the smiley. If a
   colour is not from the cast, it needs a reason.
2. **Pink-forward.** Pink owns the chrome: header band, primary buttons, selection, progress, focus ring, stage
   glow. Blue is secondary (links, info, secondary buttons). Gold means stars, ratings, "worth a look".
3. **Sticker, not flat.** Thick keylines (2 to 3 px), pill buttons, cards with a white keyline and a hard offset
   shadow. Deliberately unlike a clinical flat UI, a paper UI or a near-black UI.
4. **Ink is navy, never black.** `ink` is Nova's `#1b1c30` on light surfaces; text on pink is navy, not white.
5. **Playful but calm where it matters.** Dialogs (confirm, error, After Dark) drop the glow, state facts
   plainly, and never nag.
6. **Colour is never the only cue.** Every status has an icon or word; pinned, selected and busy have shapes.
7. **Two themes, one brand.** "Blush" (light, default) and "Cosmic" (dark navy-plum with glowing pink) share
   every role name, shape and size; only the colours move.
8. **Honest toolkit.** ttk (clam) first. Anything else is Canvas-drawn and has a ttk fallback (section 5).

---

## 2. Tokens

### 2.1 Colour roles (required by SPEC_V2 section 6)

| Role | Light "Blush" | Dark "Cosmic" | Used for |
|---|---|---|---|
| `bg` | `#fff5fa` | `#17122b` | window |
| `surface` | `#ffffff` | `#241d40` | cards, table, fields, bubbles |
| `surface_alt` | `#ffe9f3` | `#322855` | striped rows, headings, chips |
| `stage` | `#ffe4f0` | `#110c24` | mascot stage background |
| `ink` | `#1b1c30` | `#f1eff8` | body text |
| `ink_muted` | `#625a78` | `#b9b0d2` | captions, status line, placeholders |
| `line` | `#e2358d` | `#d14f98` | control borders (keylines) |
| `primary` | `#ff3d9a` | `#ff4fa3` | primary fills, progress, header |
| `primary_ink` | `#1b1c30` | `#1b1c30` | label on primary |
| `primary_soft` | `#ffd6e9` | `#4a2050` | hover rows, troughs, ghost hover |
| `accent` | `#3d8fe0` | `#5fa9f2` | secondary fills, info |
| `accent_ink` | `#1b1c30` | `#1b1c30` | label on accent |
| `accent_soft` | `#dcecfc` | `#1c3358` | secondary button fill, info toast |
| `success` | `#0f7b5b` | `#62e0b4` | success text/icon |
| `warning` | `#8f5600` | `#ffcf6b` | warning text/icon |
| `danger` | `#b8162f` | `#ff8266` | error text, danger fill |
| `focus` | `#d916c0` | `#ff8cf0` | focus ring |
| `selection` | `#ff5fad` | `#ff4fa3` | selected row |
| `selection_ink` | `#1b1c30` | `#1b1c30` | text on selection |
| `nova` | `#2b2d42` | `#ff6fdc` | Nova name tag fill |
| `iggy` | `#5a6699` | `#5a6699` | Iggy name tag fill |
| `duskie` | `#fec349` | `#ffd37c` | Duskie name tag fill |

Iggy's sprite periwinkle is `#7582b5`; the tag uses the darker `#5a6699` so white text reaches 5.53:1. Sand
`#d2b48c` is a sprite colour and a stage decoration only, never a text background.

### 2.2 Added roles (documented additions)

| Role | Light | Dark | Purpose |
|---|---|---|---|
| `primary_hover` / `primary_active` | `#ff62ae` / `#f43a92` | `#ff78b9` / `#f04499` | primary button states |
| `primary_text` | `#c2136e` | `#ff85c0` | pink used as text (pinned rows, ghost button label, links to pink things) |
| `accent_hover` / `accent_active` | `#62a6ea` / `#3a8adc` | `#84bff7` / `#4a97e6` | secondary states |
| `accent_text` | `#1b62b0` | `#8cc8ff` | links, info headings |
| `gold` / `gold_ink` | `#f7bd45` / `#1b1c30` | `#ffc94d` / `#1b1c30` | star fills, gold badge |
| `gold_soft` / `gold_text` | `#ffefc9` / `#8a5a00` | `#3d3122` / `#ffd166` | rotation-due banner, star glyph as text |
| `success_soft` / `warning_soft` / `danger_soft` | `#e0f6ea` / `#ffefc9` / `#ffe1e3` | `#153828` / `#3d3122` / `#47202a` | toast fills |
| `danger_ink` / `danger_hover` / `danger_active` | `#ffffff` / `#cb2b43` / `#9f1127` | `#1b1c30` / `#ff9b84` / `#f2714f` | danger button |
| `header` / `header_ink` | `#ff3d9a` / `#1b1c30` | `#ff4fa3` / `#1b1c30` | app header band |
| `line_soft` | `#ffc4de` | `#4b3b6e` | hairlines, row separators (decorative, not for control borders) |
| `disabled` / `disabled_ink` | `#f3e6ee` / `#978da6` | `#2b2547` / `#81789c` | disabled controls (exempt from contrast, always keep the label) |
| `stage_floor` / `stage_glow` | `#ffa9cf` / `#ffbfdb` | `#2e2440` / `#4a1c58` | stage floor and the glow ellipses |
| `keyline` / `shadow` | `#ffffff` / `#f4b6d3` | `#f1eff8` / `#0a0717` | sticker edge and drawn drop shadow |
| `nova_ink` / `iggy_ink` / `duskie_ink` | `#ff6fdc` / `#ffffff` / `#1b1c30` | `#1b1c30` / `#ffffff` / `#1b1c30` | text on the name tags |
| `cameo` / `cameo_ink` | `#e9e3f4` / `#1b1c30` | `#3a3060` / `#f1eff8` | neutral tag for cameo and new characters |

New characters: `theme.character_colors(colors, char_id, cast_entry)` returns (fill, ink): the theme role if
present, else the cast colour with a legible ink, else cameo.

### 2.3 Measured contrast (selected; full list from `python3 -m pawtation.theme`)

| Pair | Light | Dark | Needs |
|---|---|---|---|
| `ink` on `bg` | 15.69 | 15.93 | 4.5 |
| `ink` on `surface` | 16.73 | 13.92 | 4.5 |
| `ink` on `surface_alt` | 14.50 | 11.74 | 4.5 |
| `ink` on `stage` | 14.03 | 16.74 | 4.5 |
| `ink_muted` on `bg` | 6.05 | 8.81 | 4.5 |
| `ink_muted` on `surface` | 6.46 | 7.70 | 4.5 |
| `ink_muted` on `surface_alt` | 5.60 | 6.50 | 4.5 |
| `primary_ink` on `primary` | 5.09 | 5.50 | 4.5 |
| `primary_ink` on `primary_active` (pressed) | 4.67 | 4.77 | 4.5 |
| `accent_ink` on `accent` | 4.94 | 6.73 | 4.5 |
| `accent_ink` on `accent_active` | 4.66 | 5.46 | 4.5 |
| `selection_ink` on `selection` | 5.97 | 5.50 | 4.5 |
| `danger_ink` on `danger` | 6.58 | 6.88 | 4.5 |
| `primary_text` on `surface` | 5.81 | 7.07 | 4.5 |
| `accent_text` on `surface` | 6.14 | 8.92 | 4.5 |
| `gold_text` on `surface` | 5.93 | 10.99 | 4.5 |
| `success` on `surface` | 5.24 | 9.69 | 4.5 |
| `warning` on `surface` | 6.00 | 10.86 | 4.5 |
| `danger` on `surface` | 6.58 | 6.52 | 4.5 |
| `success` on `success_soft` (toast heading) | 4.63 | 7.89 | 4.5 |
| `danger` on `danger_soft` | 5.36 | 5.73 | 4.5 |
| `nova_ink` on `nova` | 5.50 | 6.82 | 4.5 |
| `iggy_ink` on `iggy` | 5.53 | 5.53 | 4.5 |
| `duskie_ink` on `duskie` | 10.45 | 11.84 | 4.5 |
| `primary` on `bg` (fill/keyline) | 3.08 | 5.96 | 3.0 |
| `primary` on `surface` | 3.29 | 5.21 | 3.0 |
| `accent` on `bg` | 3.17 | 7.29 | 3.0 |
| `accent` on `surface` | 3.39 | 6.37 | 3.0 |
| `line` on `bg` (control border) | 3.84 | 4.56 | 3.0 |
| `line` on `surface` | 4.10 | 3.99 | 3.0 |
| `line` on `surface_alt` | 3.55 | 3.36 | 3.0 |
| `line` on `stage` | 3.43 | 4.79 | 3.0 |
| `focus` on `bg` | 4.08 | 8.86 | 3.0 |
| `focus` on `surface` | 4.35 | 7.75 | 3.0 |
| `focus` on `stage` | 3.65 | 9.31 | 3.0 |

Rules that follow from the numbers:
- Pink as **text** on light must be `primary_text` (`#c2136e`), never `primary` (3.08:1 is for fills only).
- Text **on** pink, blue, gold, red-in-dark is navy `*_ink`. On light `danger`, text is white.
- `disabled_ink` is exempt from the 4.5 rule (WCAG exempts inactive controls) but must stay a visible label.
- `line_soft` is decoration only (row separators); control borders always use `line`.

### 2.4 Type

Fonts cannot be bundled. The GUI calls `theme.pick_font(candidates, installed)` (no tkinter needed; pass
`tkinter.font.families()`), or `theme.fonts(installed)` for all three roles. First installed wins; a role with
nothing installed falls back to the toolkit default.

| Role | Ordered candidates (see theme.json for the full list) |
|---|---|
| display | Fredoka, Baloo 2, Nunito, Quicksand, Varela Round, M PLUS Rounded 1c, Arial Rounded MT Bold, Hiragino Maru Gothic ProN, Chalkboard SE, Ubuntu, Trebuchet MS, Cantarell, Avenir Next, Verdana, DejaVu Sans, Helvetica Neue, Arial |
| body | Nunito, Varela Round, M PLUS Rounded 1c, Ubuntu, Cantarell, Avenir Next, Trebuchet MS, Verdana, Noto Sans, DejaVu Sans, Helvetica Neue, Segoe UI, Liberation Sans, Arial |
| mono | JetBrains Mono, Cascadia Mono, Cascadia Code, SF Mono, Menlo, Consolas, DejaVu Sans Mono, Ubuntu Mono, Liberation Mono, Courier New |

On a stock Windows machine this resolves to Trebuchet MS / Verdana (friendly, not clinical); on macOS to
Chalkboard SE or Avenir Next; on Linux to Ubuntu, Cantarell or DejaVu Sans. Segoe UI is deliberately late in the
body list (it is another app's identity).

| Style | Family | px | Weight | Use |
|---|---|---|---|---|
| display | display | 26 | bold | header title |
| title | display | 20 | bold | dialog titles, empty-state heading |
| heading | display | 16 | bold | card headings, table header |
| body | body | 14 | normal | everything else |
| body_strong | body | 14 | bold | buttons, selected row |
| small | body | 12 | normal | captions, status line |
| tag | body | 12 | bold | name tags, chips |
| mono | mono | 13 | normal | paths, JSON, card ids |

Leading 1.4. Convert px to tk points with `theme.tk_size(px, ui_scale)` (negative size = pixels in tk; the helper
handles it). Never go below 12 px.

### 2.5 Space, radius, size, keyline, elevation

| Token | Values |
|---|---|
| space (px) | 0, 2, 4, 8, 12, 16, 24, 32, 48 (use only these; window gutter 18) |
| radius | none 0, sm 6, md 10, lg 16, pill 999 |
| size | header 64, control 36, control_sm 28, control_lg 44, row 30, chip 30, progress 22, meter 12, star 22, hit_min 28 |
| layout | window_min 960 x 640, default 1120 x 780, side panel 448 |
| keyline | hair 1, control 2, card 2, sticker 3, focus 3 (+2 gap) |
| elevation (hard offset shadow, px dx,dy) | flat 0,0; card 3,3; raised 4,5; dialog 6,7 (colour `shadow`) |

Elevation is a second rectangle drawn offset behind the card in `shadow`, then the card in `surface` with a
`keyline` (white) inner edge and a `line` (pink) outer edge. No blur.

### 2.6 Motion

| Token | ms | Use |
|---|---|---|
| fast | 90 | button press, hover |
| base | 160 | toast in/out, tab change |
| slow | 280 | dialog fade, stage swap |
| sparkle | 900 | progress sparkle pulse, stage twinkles |
| stripe | 700 | busy progress stripe shift |
| blink_min / blink_max | 2800 / 6500 | random sprite blink gap |
| bubble_hold / toast_hold | 6000 / 4500 | how long they stay |
| sprite_fps_max | 12 | idle animation cap |

**Reduced motion:** when `theme.reduce_motion_requested(cfg)` is true (config.json `"gui_reduce_motion": true`, or env
`PAWTATION_REDUCE_MOTION=1`), use `theme.motion(reduced=True)`: all durations 0, no sprite
animation (static idle frame), no sparkle pulse, busy bar shows a static striped fill with a text percentage or
"Working...". Information must never depend on motion.

### 2.7 Sprites

| Where | Size | Notes |
|---|---|---|
| Stage (Nova + Iggy, and Duskie when home) | 192 px | `theme.stage_sprite_size(width, count)` shrinks to fit |
| Stage compact (3 at home, narrow window) | 96 px | stage height 188 |
| Cameo chips, dialog header | 96 px | |
| Empty state | 192 px | |
Sprites overlap by 24 px, gap 16 px in compact, baseline at 92% of the stage height (on the floor ellipse).
Sprites already carry their white die-cut sticker edge; do not add another outline.

---

## 3. Components

Hover and active colours come from the `*_hover` / `*_active` roles. **Focus** is always a 3 px `focus` ring with
a 2 px gap (Canvas) or a `focuscolor`/`highlightthickness` ring (ttk). **Busy** = label changes to "Working..."
with a `+` glyph, same colours as hover, not clickable. **Disabled** = `disabled` fill, `disabled_ink` text,
`line_soft` border, no hover.

### 3.1 App header band

| | |
|---|---|
| Description | 64 px pink band across the top with the sparkle mark, "Pawtation" (display), the rotation timer pill, theme toggle and help. |
| Tokens | fill `header`; text `header_ink` (5.09 / 5.50); timer pill `keyline` fill + `ink` text (16.73 / 14.69); outline buttons `header_ink` border 2 px, transparent fill |
| States | Rotation due: timer pill becomes `gold` fill, `gold_ink` text, label "Rotation due" and a diamond glyph (not colour only). Hover on header buttons: `keyline` at 30% mix. Focus: ring in `keyline` (the pink focus colour would vanish on pink). |
| Build | ttk Frame with `header` bg; pill is Canvas or a Label with `relief=solid`, bordered; fallback is a square label. |

### 3.2 Buttons

| Variant | Use when | Default | Hover | Active | Disabled | Focus | Busy |
|---|---|---|---|---|---|---|---|
| Primary (pill) | the one main action per view ("Plan new rotation", "Sync") | fill `primary`, border `line` 2 px, text `primary_ink` | `primary_hover` | `primary_active`, 1 px down | disabled set | 3 px `focus` ring | hover colour, "+ Working..." |
| Secondary | other actions (Rescan, Pick folder) | fill `accent_soft`, border `accent`, text `accent_text` (5.10) | `accent_hover` fill, `accent_ink` text | `accent_active` | disabled set | ring | as above |
| Ghost | tertiary (Fortune, Joke chips, Cancel on cards) | transparent, text `primary_text`, no border | `primary_soft` fill | `surface_alt` | `disabled_ink` text | ring | n/a |
| Danger | destructive and confirmed ("Remove 3 games", "Sync anyway") | fill `danger`, text `danger_ink` | `danger_hover` | `danger_active` | disabled set | ring | as above |

Height `control` 36 (hit_min 28 for compact toolbars). Padding 16 horizontal, 8 vertical. Labels are
sentence case verbs. Pill shape needs a Canvas widget (`PillButton`: polygon of two arcs and a rectangle, text
centred, binds Enter/Space/click, takes keyboard focus). Fallback: `ttk.Button` with style `Pawtation.TButton`
(clam theme, flat fill, 2 px `line` border, `padding=(16, 6)`, `map()` for hover/active/disabled). One primary
per view; destructive actions are never the default focus in a confirm dialog.

### 3.3 Search field

Pill outline, `surface` fill, `line` border 2 px, placeholder in `ink_muted` (6.46), clear "x" appears when
non-empty. Focus: border becomes `focus` 3 px. Disabled ("Scanning..."): `disabled` fill. Error (date fields):
`danger` border plus an icon and message below in `danger` text; never a border change alone. ttk: `ttk.Entry`
with `fieldbackground=surface`, `bordercolor=line`, `lightcolor/darkcolor=line`, focus via `map`.

### 3.4 Game table

| Part | Spec |
|---|---|
| Frame | card sticker: `surface`, `line` border, shadow `card` |
| Header row | `surface_alt` fill, heading font, sort arrow glyph (up/down triangle) after the title of the sorted column |
| Rows | 30 px; even rows `surface`, odd rows `surface_alt` (hover `primary_soft`) |
| Selection | `selection` fill + `selection_ink` text (5.97 / 5.50), bold. A thick left bar in `line` marks it too. |
| Pinned | heart glyph in the first column + title in `primary_text` (bold), so it is readable without colour |
| Rating | five stars, 22 px, filled `gold` with a `gold_text` outline, empty stars outline only; read-only in the table, clickable in the "Rate selected" row; stars have a text twin ("4 of 5") for screen readers and the status line |
| Disabled/not on a card | `ink_muted` text, italic "not on a card" |
Build: `ttk.Treeview` with `rowheight=30`, tag colours via `tag_configure` for pinned/odd; stars are text glyphs
in a Treeview column (gold_text colour, tag) to stay native. Selected-row colour via `style.map`.

### 3.5 Card-strip chips

One chip per SD card in a horizontal strip: name, "used/total GB", short status ("showing", "inserted",
"too full", "not set up"). `surface` fill, `line` border (2 px), radius `md`; the card currently inserted gets a
`primary_soft` fill and a pink 3 px keyline; "too full" shows `danger` text and a warning glyph; "not set up" is
dimmed (`disabled`). Selected chip is a toggle: `selection` fill. Hover: `primary_soft`. Focus ring. Size
`chip` 30 tall minimum. Canvas or ttk Label with `relief`; ttk fallback loses rounded corners only.

### 3.6 Progress bar and cancel

Chunky bar, 22 px tall, `line` 2 px border, trough `primary_soft`, fill `primary`. Determinate: sparkle glyph
rides the leading edge (`sparkle` motion, static in reduced motion). Indeterminate/busy: diagonal stripes
shifting every `stripe` ms. Always paired with text ("42% Copying Chibi-Robo! 571 MB of 1.36 GB, about 2
minutes left") in `body`, and a **Cancel sync** secondary button. After cancel the text states what stays
("nothing is deleted that Pawtation did not put there"). ttk fallback: `ttk.Progressbar` style with
`troughcolor=primary_soft`, `background=primary` (flat, square). Canvas is needed for stripes and sparkle.

### 3.7 Mascot stage

| Part | Spec |
|---|---|
| Panel | sticker card, `lg` radius, `stage` background, `line` border 3 px, `card` shadow |
| Glow | two concentric ellipses (`stage_glow` then a lighter mix) behind the characters |
| Floor | `stage_floor` ellipse across the bottom, sprites stand on it |
| Twinkles | 3 to 5 four-point stars in `keyline`/`gold` (static in reduced motion) |
| Speech bubble | `surface` fill, `line` border 2 px, tail pointing at the speaker, text `ink` (16.73 / 13.92). Name tag overlaps the top-left corner. |
| Name tag | pill, fill = the character's role (`nova`, `iggy`, `duskie`, `cameo`), text `*_ink`, white keyline; shows "Name pronoun" (Nova he/him, Iggy any/all, Duskie he/him) in tag font. Always shown below sprites and on bubbles. |
| Who-is-home chips | one per character in the row under the stage: coloured dot, name, and an affordance pill. At home: "Send out" (secondary). Away: dashed-border chip, "out", and "Invite" (primary-soft pill). Disabled while a rotation is syncing. |
| Stat meters | affection (pink `primary`) and energy (gold `gold`), 12 px tall, `line` border, trough `surface_alt`, with a numeric label ("14/20"). Never colour only. |
| Chat row | one-line entry in a pill with a "Send" primary button; quick chips (Pet, Feed, Play, Joke, Suggest, Fortune) are ghost buttons. |
Stage rendering is Canvas (ovals, polygons, sprite PhotoImages). Fallback: a `ttk.Frame` in `stage` colour with
the sprites as Labels and a plain Label for the bubble.

### 3.8 Dialogs

Sticker card on a dimmed window, `dialog` shadow, `lg` radius, a 96 px cameo sprite at the left, title (title
font), body text, optional mono detail box (`surface_alt`, mono).

| Dialog | Spec |
|---|---|
| Confirm | title says what will happen ("Sync Card 3 for real?"); body gives counts and sizes; footer: ghost/secondary "Keep it a dry run" (default focus) and primary "Sync Card 3". A destructive confirm uses the danger button and is never the default. |
| Error | warning/x icon in `danger`, plain-language cause, what is safe ("Files Pawtation did not write are never touched"), mono detail box, "Copy details" ghost, "Cancel" secondary, optional danger "Sync as Card 3 anyway". |
| After Dark age gate | Calm and factual. Title "After Dark" with a quiet "optional - 18+" tag (`surface_alt`, not alarming). Body says what it is, that nothing else needs it, that the date of birth is checked and **not saved**, and that it can be turned off at any time. Field accepts YYYY-MM-DD, MM/DD/YYYY, DD.MM.YYYY. Buttons: secondary "Not now" (default focus), primary "Check and turn on". Under-18: a plain message in `danger` with an icon, "After Dark stays off." and only "Close". No countdowns, guilt wording, pre-ticked boxes or repeated prompts. |
Keyboard: Escape = the safe choice (cancel/Not now); Enter = default focused button; Tab loops inside the dialog.

### 3.9 Toasts and status line

Toast: radius `md`, 2 px border in the status colour, fill `*_soft`, text `ink`, heading in the status colour,
icon on the left (info "i", success tick, warning triangle, error x). Stack bottom-right inside the window, held
`toast_hold`, never auto-dismiss errors. Status line: bottom bar, `ink_muted` on `bg` (6.05), a small coloured
icon at the left (tick for ok), 12 px.

| Kind | Border | Heading | Fill | Icon |
|---|---|---|---|---|
| info | `accent` | `accent_text` | `accent_soft` | i in circle |
| success | `success` | `success` | `success_soft` | tick |
| warning | `warning` | `warning` | `warning_soft` | triangle ! |
| error | `danger` | `danger` | `danger_soft` | x in circle |

### 3.10 Empty states

Stage-style panel at 192 px sprites with a speech bubble and one primary button.
- No library yet: Nova says "The shelf is empty. Point me at your library folder and I will count every disc.
  Twice." Button "Pick library folder", caption "Nothing is copied or changed until you press Sync."
- No search results: Iggy, "Nothing matches that. Try fewer words, or clear the filter." Button "Clear search".
- No cards set up: "Name your SD cards in Settings. I will do the maths."
- Everyone out (nobody home): empty stage floor with a dim "Invite someone" prompt.
Lines come from `data/pets.json`/`scenes.json`; never pet names for the player.

---

## 4. Patterns

| Pattern | Flow |
|---|---|
| First run | Empty library state, one primary action (Pick library folder). After a library is picked: card setup chips appear dimmed with "not set up". Nova greets once; no tour. |
| Syncing | Primary becomes busy, progress bar + Cancel visible, who-is-home chips disabled, a toast on finish ("Card 3 synced. 2 games copied, 0 removed."), characters comment but do not block. |
| Rotation due | Once per session: a `gold_soft` banner ("Rotation due. It has been 14 days. Plan a new one when you feel like it.") with a "Plan new rotation" button; the header timer pill turns gold. No modal, no repeat nag. |
| Dry run first | Every sync shows "planned" status (counts, sizes) before copying; the confirm dialog is the only gate. |

---

## 5. ttk vs Canvas

| Needs Canvas | ttk covers | Fallback if Canvas is skipped |
|---|---|---|
| Pill buttons and chips (rounded ends) | Colours, borders, padding, hover/active/disabled via `style.map` | Square `ttk.Button` with the same colours and 2 px `line` border |
| Sticker cards (offset shadow) | Frame with border | Frame with `relief=solid`, no shadow |
| Progress sparkle and stripes | Flat `ttk.Progressbar` | Plain bar plus the percentage text |
| Stage (glow, floor, twinkles, bubble tail) | n/a | Flat `stage` background, sprites as Labels, rectangular bubble |
| Star ratings | Text glyphs | Same (glyphs are native) |
| Name tags | Label with bg/fg | Square label |
Use ttk theme `clam` as the base. Colours are set through `ttk.Style.configure/map`; fonts via `theme.fonts`.
macOS Aqua ignores some ttk styling; clam is forced on all platforms for consistency.

---

## 6. Accessibility

- **Keyboard order:** header (timer, theme, help) -> toolbar (primary, secondary, ghost) -> search -> card
  chips -> game table -> rate/pin row -> progress/cancel -> stage (who-is-home chips, quick chips, chat entry,
  Send) -> status line. Every control reachable and activatable by keyboard; shortcuts: Ctrl+F search, F1 help,
  Esc closes dialogs, Delete (with confirm) removes selection, 1 to 5 rate the selected row.
- **Focus visibility:** 3 px `focus` ring (>= 3.65:1 on every surface in light, >= 6.5:1 in dark) with a 2 px gap;
  on pink fills the ring uses `primary_ink` (5.09 / 5.50); never rely on a colour change alone.
- **Colour-independent cues:** status always has an icon plus word; pinned has a heart; selected has a left bar
  and bold; sort has an arrow; meters have numbers; "too full" has a glyph.
- **Colour-vision check** (`art/out/cvd_check.py`, Machado 2009, protanopia, deuteranopia, tritanopia):
  success vs danger text stays far apart under all three (delta-E 99.8 normal, 17.3 protan, 30.2 deutan,
  108.9 tritan). Weak pairs under CVD: success vs `primary_text` (4.5 deutan, light), `success_soft` vs
  `accent_soft` (7.0 tritan, dark), `accent_soft` vs `primary_soft` (8.1 deutan, light). These are never used
  to carry meaning alone: they are always separated by icon, label or position.
- **Reduced motion:** section 2.6.
- **Hit sizes:** nothing smaller than `hit_min` 28 px in either direction; primary controls `control` 36 px;
  star hit targets 22 px glyph in a 28 px cell; dense toolbars only at `control_sm`.
- **Contrast:** section 2.3; both themes pass every pair the GUI uses (audit in the test).
- **Scale:** sizes are px at scale 1; `theme.tk_size(px, ui_scale)` supports a UI scale setting; layouts must
  not clip at 125 % and 150 %.
- **Text:** body 14 px minimum 12 px, left-aligned, sentence case, plain wording; characters never use pet names
  for the player, and never stand in for factual error text.

---

## 7. Do and don't

| Do | Don't |
|---|---|
| Pink for chrome, primary buttons, selection, progress, focus | Pink text on light surfaces in plain `primary` (use `primary_text`) |
| Navy ink on pink, blue and gold fills | White text on `primary` (fails) or pure black anywhere |
| One primary pill per view | Two competing pink buttons |
| Gold only for stars, ratings, rotation-due | Gold as a general highlight or for warnings (warning has its own role) |
| Name + pronoun on every character tag | Guess pronouns, rename characters, or colour a tag outside its role |
| Pair status colour with an icon and a word | Colour-only status |
| Keep dialogs calm: facts, safe default focus, Esc cancels | Dark patterns: guilt text, countdowns, pre-ticked boxes, repeated After Dark prompts |
| Take colours, sizes, fonts and timings from `theme` | Hex literals or magic numbers in `gui.py` |
| Honour reduced motion | Animation that carries information |
| Let the fallback (square ttk) work fully | Ship a feature that only works when the Canvas pills draw |

---

## 8. Open questions for the owner

1. Pink strength: `#ff3d9a` on light gives 3.08:1 as a fill against the window (just above the 3.0 bar). Happy
   with this exact hue, or should the light primary go a touch deeper (`#f0278b`) for stronger edges?
2. Dark theme as default at night? Add "follow the OS" (needs per-OS detection; stdlib cannot do it reliably
   on Linux)?
3. Font installs: should Pawtation suggest (not bundle) Fredoka/Nunito for the full look, or stay silent?
4. Stars: five stars with half stars, or whole stars only (current)?
5. Duskie's tag is gold in both themes; should Duskie get her own stage background tint when home?
6. Name tags: always show pronouns (current), or only on first appearance each session?
7. Header timer: show days and hours (current), or only days to keep it calmer?
8. Sticker shadows in Cosmic are near-invisible; keep them for parity or replace with a pink glow ring?
9. Toast position bottom-right overlaps the stage on narrow windows; move above the status line instead?

---

## 9. Not verified

Real tkinter rendering (clam theme on Windows, macOS, Linux), actual font availability, Canvas pill and sparkle
performance, and OS-level high-DPI scaling. All visuals above were checked in the HTML preview only. Contrast
values are exact; layout sizes are the design intent and may need a nudge in the real widgets.
