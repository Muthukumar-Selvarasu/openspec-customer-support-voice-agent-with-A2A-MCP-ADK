# FDE Companion design system

How the paid student site looks and feels, and the rules for adding to it. It describes what's built today: `proof/premium.css` layered over the live site's own styles, the chat in `proof/companion.js`, the drawings and the video thumbnails. When the two disagree, the code wins; fix this file.

The one-line version: **a white page, ink type with one serif italic word in teal, a gold PRO badge, soft teal/gold/coral light, and ink-and-watercolour drawings.** It should feel calm and expensive, never loud.

---

## 1. Principles

1. **Premium, and clearly not the free course.** The free Agent Engineering course shares the plain white-and-teal base. What makes this one paid: the gold PRO badge, the serif italic accent, the aurora, the drawings, the soft lift on cards, the docked chat. Keep all of them.
2. **Change only what is asked.** If Hamza asks to change one colour, change that colour. Never strip the rest of the look to "simplify".
3. **One accent per moment.** One italic word per headline. One coral thing per drawing. One primary (teal) button per group.
4. **Light only.** A dark version was tried and rejected. There is no dark theme.
5. **Quiet motion.** Things drift, lift and fade in; nothing bounces or flashes. Every animation has a reduced-motion fallback.
6. **Plain words.** No internal codes on screen (no `VST`, `m0`, `V03`). Say "the companion video", "Module 2".

---

## 2. Colour

### Tokens

Copy these as the source of truth. They live on `:root` in `proof/premium.css` (premium layer) and the base site's CSS.

```css
:root {
  /* page and surfaces */
  --paper:      #ffffff;  /* the page. Pure white (decided 2026-11-11) */
  --paper-2:    #f5f3ee;  /* warm off-white for quiet panels */
  --bg-soft:    #f6f5f1;  /* base site: code, table heads, footer, steps panel */
  --bg-mist:    #eef4f3;  /* teal-tinted panel: active index item, prompts, tags */
  --line:       #e8e5de;  /* every hairline border */
  --line-2:     #cfcdc6;  /* stronger border: inputs, ghost buttons, checkboxes */

  /* type */
  --ink:        #111414;  /* headings, body */
  --ink-2:      #4d5454;  /* secondary text, descriptions */
  --ink-3:      #7a8080;  /* captions, meta (see contrast note) */

  /* brand */
  --teal:        #1d7581; /* the accent: italic words, numbers, links, labels */
  --teal-deep:   #165e68; /* hover, gradient end, text on mist */
  --teal-bright: #2a9aa7; /* gradient start, focus borders, glows. Not for text */
  --teal-glow:   rgba(42, 154, 167, 0.22); /* focus ring, glows behind video */
  --gold:        #e3b866; /* PRO badge, aurora, highlights. Not for text */
  --gold-ink:    #9a6b1c; /* gold you can read: eyebrows, kickers */
  --coral:       #ff6a4d; /* focal accent: play triangles, drawings. Not for text */
  --coral-ink:   #c2432b; /* coral you can read, when it must be text */
  --green:       #2f7d4a; /* done: ticked steps, completion */
  --green-soft:  #e6efe1;
}
```

### What each colour means

| Colour | Means | Used for |
|---|---|---|
| **Teal** | the course, "go here" | italic headline word, module numbers, links, labels, primary buttons, progress bars |
| **Gold** | premium, success | PRO badge, eyebrow lines (as gold ink), aurora, highlights |
| **Coral** | look here; or "not this" | play triangles, the focal point of every drawing, the "Highly experimental" badge, warning dots |
| **Green** | done | ticked steps, "all done" messages |
| **Ink greys** | everything else | type and lines |

Teal, gold and coral appear together only as **light**: the aurora, the gradient edge on a hovered card, the chat orb and its input ring. In flat UI, pick one.

### Contrast on white (checked 2026-11-12)

| Colour | Ratio | OK for |
|---|---|---|
| ink | 18.5 | anything |
| ink-2 | 7.7 | anything |
| teal-deep | 7.4 | anything |
| teal | 5.4 | body text and links |
| green | 5.1 | body text |
| coral-ink | 5.1 | body text |
| gold-ink | 4.7 | small caps eyebrows, body text |
| **ink-3** | **4.0** | **18px+ only.** Captions at 13–14px fall just short of AA. The base site's `#6e7575` (4.7) passes; prefer it for new small text |
| teal-bright | 3.3 | large text (24px+) and borders only |
| coral | 2.8 | never text: shapes and drawings only |
| gold | 1.9 | never text: fills and glows only |

White text on the teal button gradient starts at 3.3 on the bright end; keep button labels 15px+ and weight 600.

### The aurora

The premium hero's signature: three blurred radial glows on white, drifting slowly.

```css
background:
  radial-gradient(38% 48% at 16% 28%, rgba(42, 154, 167, 0.22), transparent 70%),  /* teal, top left */
  radial-gradient(34% 44% at 84% 18%, rgba(255, 106, 77, 0.14), transparent 70%),  /* coral, top right */
  radial-gradient(44% 50% at 62% 92%, rgba(227, 184, 102, 0.22), transparent 70%); /* gold, bottom */
filter: blur(24px);
animation: aurora 22s ease-in-out infinite alternate;  /* drift 4%, turn 8°, scale 1.08 */
```

Over it, a 5% film-grain layer (SVG turbulence, `mix-blend-mode: multiply`). Coral is always the faintest of the three. Use the aurora for heroes, the welcome screen and the chat panel; not behind body text.

### Tinted card backgrounds (base site)

```css
--mist-grad:  radial-gradient(120% 120% at 0% 0%,   #d9eceb 0%, #eef5f4 45%, #f7faf9 100%); /* teal */
--sand-grad:  radial-gradient(120% 120% at 100% 0%, #efe6d6 0%, #f5f0e6 45%, #faf8f3 100%); /* gold */
--slate-grad: radial-gradient(120% 120% at 0% 100%, #dfe4ec 0%, #eef1f5 45%, #f8f9fb 100%); /* cool */
```

Module cards rotate through these. Outcome boxes and figures use mist; notes use sand.

---

## 3. Type

Two families, loaded from Google Fonts:

```css
@import url("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap");
--sans:  "Inter Tight", "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif;
--serif: "Instrument Serif", Georgia, serif;
--mono:  ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
```

- **Inter Tight** for everything: headings, body, buttons.
- **Instrument Serif italic** for **one** word per headline, in teal, weight 400, `letter-spacing: -0.01em`. Also for big module numbers on cards. Never a whole sentence, never body text.
- **Mono** for code, file paths, keyboard keys, timestamps.

```html
<h1>The one place for <em>everything</em> in the course.</h1>
```
```css
h1 em { font-family: var(--serif); font-style: italic; font-weight: 400; color: var(--teal); }
```

### Scale

| Role | Size | Weight | Tracking | Notes |
|---|---|---|---|---|
| Home hero h1 | `clamp(40px, 4.1vw, 66px)` / 1.03 | 600 | -0.025em | `text-wrap: balance` |
| Page h1 | `clamp(2.375rem, 3.6vw, 3.25rem)` / 1.05 | 600 | -0.035em | |
| h2 | `clamp(1.625rem, 2.2vw, 1.9375rem)` / 1.15 | 400–600 | -0.025em | |
| h3 | 1.375rem | 400–500 | -0.015em | |
| Lead (`.sub`) | 19px / 1.55 | 400 | | ink-2, max 40em |
| Body | 1.0625rem (17px) / 1.6 | 400 | -0.005em | |
| Reading (`.prose`) | 1.125rem (18px) / 1.7 | 400 | | max 46em per line |
| Eyebrow / kicker | 12.5px | 700 | 0.16em, uppercase | gold-ink |
| Card label | 0.8125rem (13px) | 500–600 | 0.06–0.1em, uppercase | teal |
| Small / meta | 0.875rem (14px) | 400 | | ink-3 |
| Card number | 40–56px serif | 400 | | teal |

Body has `-webkit-font-smoothing: antialiased`; paragraphs and list items use `text-wrap: pretty`.

---

## 4. Space, shape and depth

### Layout

| Token | Value |
|---|---|
| Page width (`--wrap`) | 1320px |
| Gutter | 32px; 16px under 720px |
| Header height | 64px |
| Topic page grid | index 260px · main up to 900px · checklist 340px |
| Docked chat (`--cc-w`) | 420px; pushes the page left at 1280px and wider |
| Home hero padding | 88px top, 96px bottom |
| Section gap on home | `clamp(64px, 7vw, 104px)` |

Breakpoints in use: **1280** (index becomes a drawer), **1100** (cards 3→2 columns), **1023** (one column), **720** (cards 2→1, smaller gutter), **640** (chat launcher becomes an icon).

### Radius

| Radius | Used for |
|---|---|
| 999px | pills: buttons, facts, chips, badges, tags |
| 24px (`--radius`) | big cards: module cards, outcome boxes, checklist panel |
| 20px | video players |
| 18px | small cards: repo card, course-repo stats |
| 14px (`--radius-sm`) | steps, refs, tables, page nav, chat sources |
| 10–12px | inner rows, links inside cards, inputs, chat send button |

### Shadow

Shadows are long, soft and low: light from above, never a hard edge.

```css
--lift: 0 30px 60px -34px rgba(17, 20, 20, 0.28);              /* hovered card, video */
/* video player in a hero */
box-shadow: 0 0 0 1px rgba(17,20,20,.06), 0 40px 80px -36px rgba(17,20,20,.35), 0 0 70px -20px var(--teal-glow);
/* primary button */
box-shadow: 0 12px 28px -12px rgba(29,117,129,.6), inset 0 1px 0 rgba(255,255,255,.25);
/* focus and hover ring */
box-shadow: 0 0 0 4px var(--teal-glow);   /* with border-color: var(--teal-bright) */
```

### Glass

The header, hero fact pills, chat header and footer, and welcome screen are white glass:

```css
background: rgba(255, 255, 255, 0.78);
backdrop-filter: saturate(180%) blur(16px);
border-bottom: 1px solid var(--line);
```

---

## 5. Motion

```css
--ease: cubic-bezier(.2, .7, .2, 1);   /* every transition */
```

| Kind | Duration | Example |
|---|---|---|
| Hover colour or border | 0.2s | links, chips, ghost buttons |
| Hover lift | 0.3–0.35s, up 2–4px | cards, launcher |
| Drawing on hover | 0.6s, scale 1.05 | module card art |
| Enter | 0.35–0.5s, fade + 8px rise (chat messages also unblur 4px) | welcome screen, chat messages |
| Leave | 0.28s fade | welcome screen |
| Panel slide | 0.45–0.5s | chat panel |
| Ambient | 6–22s, linear or alternate | aurora (22s), chat orb (6s), chat edge (6s), glows (14–18s) |

Rules: animate `transform` and `opacity`, not layout. Every looping or entering animation is switched off under `@media (prefers-reduced-motion: reduce)`.

---

## 6. Components

### Header
White glass, sticky. Brand name in ink, weight 600, followed by the **PRO badge**:

```css
content: "PRO"; padding: 3px 8px 2px; border-radius: 999px;
font-size: 10.5px; font-weight: 700; letter-spacing: 0.14em; color: #3a2706;
background: linear-gradient(135deg, #f6e2b4, var(--gold) 55%, #cf9f4f);
box-shadow: 0 4px 14px -4px rgba(207, 159, 79, 0.55);
```

The PRO badge is the brand mark of the paid site. It appears in the header and on every video thumbnail. Don't use gold gradients anywhere else.

Nav links ink-2, ink on hover. The right-hand pill is white with a hairline border. No Maven or sales links (they stay hidden until `LIVE_URL` is set, then read "Live sessions").

### Buttons

| Kind | Look | When |
|---|---|---|
| Primary (`.pill`) | teal gradient `135deg, teal-bright → teal-deep`, white text, button shadow | the one main action in a group |
| Secondary (`.pill--ghost`) | white, ink text, hairline border, small shadow | everything else |
| Text link | teal, weight 500 | inline actions |
| Small (`.copy`, chips) | white pill, 1px line-2 border, 12–13.5px | copy prompt, suggested questions |

All buttons are pills, padding about 13px 24px, gap 10px for an arrow. A trailing arrow moves 3px right on hover. Hover on white buttons: border turns teal-bright with the 4px teal-glow ring.

### Fact pills (hero)
White glass pills, hairline border, 14px, ink-2 with the number in bold ink: "**6** modules".

### Module cards ("doors")
- Tinted background (mist, sand or slate gradient), radius 24, hairline border.
- Top to bottom: the drawing (168px tall, sits on the bottom edge), serif number in teal (40px with art, 56px without), title (1.375rem), description (ink-2, 15px), teal "Open →" link pinned to the bottom.
- Cards in a row share lines through `subgrid`, so titles and links align.
- Hover: rise 4px, `--lift` shadow, and a **teal → gold → coral gradient border** fades in. The drawing scales 1.05.
- Not open yet: drawing at 55% saturation and 80% opacity, "Soon" in ink-3.
- Foundation, Voice and Demo day use a word instead of a number, in serif italic.
- Nine cards fill three columns; at two columns the last card spans the row with its drawing beside the text.

### Small stat cards (course repo section)
White, radius 18, hairline border. Big number (34px, 600), label (ink-2, 14px), teal link line. A soft radial glow sits in the top right corner, teal / gold / coral by position, and grows on hover.

### "From the course repo" card (topic pages)
White to faint mist gradient, radius 18. Uppercase teal label with a GitHub icon. Each row: bold title, then the file path in mono, ink-3, truncated with an ellipsis. Row hover: `#eef4f3`.

### Video players
Radius 20, `overflow: hidden`, the hero video shadow (hairline + long drop + teal glow). The **play button** is a white circle with a **coral** triangle: 104px on the welcome screen (gentle pulse), 28px inline (the "Watch the welcome" link), 64px teal on embedded Looms.

### Welcome screen
Full screen over the page: white at 92% with a teal glow top left and a gold glow bottom right, blurred. Gold-ink uppercase kicker above the player, a round close button top right, a note in ink-3 and a "Continue" pill below. The pill turns into a primary teal button when the video ends. Shown once (`fde-welcome-seen`).

### Topic page
- Left index: uppercase ink-3 group labels; links ink-2; the **active topic is a teal gradient pill with white text**.
- Right checklist: soft panel, radius 24; each step a white card with a 24px rounded checkbox that fills **green** with a white tick when done. Locked steps at 50% opacity.
- Prompts to copy sit on mist, with a small "Copy" pill.
- Notes in reading text: blockquote with a 3px coral left rule; admonitions on soft or mist with a small teal dot (coral for warnings).

### The chat
Docked on the right, 420px, closed until "Ask the companion" or ⌘J.

- **Launcher**: white glass pill bottom right; the **orb** (conic gradient teal → teal → gold → coral, turning every 6s, faster and pulsing while thinking), the label, the "Highly experimental" badge and a `⌘J` key.
- **Panel**: white fading to warm off-white, a 2px animated teal/gold/coral line on its left edge, two slow glows (teal top right, gold bottom left).
- **Header and footer**: white glass, hairline borders.
- **Your messages**: teal gradient bubble, white text, corner `16 16 4 16`.
- **Answers**: plain text, no bubble; quotes with a 2px teal-bright rule on faint mist; a teal caret while typing; a shimmering teal/gold bar and mono file names while searching.
- **Sources**: white cards, radius 14. Pages on this site have a teal-tinted border and a teal path; GitHub files show a mono path in grey. Every answer keeps its sources.
- **Input**: white textarea inside a 1.5px teal → gold → coral gradient ring, radius 16; send button is a teal gradient square, radius 11.
- **"Highly experimental" badge**: coral-ink `#a3361f` on `#fff1ec`, border `#ffd3c7`, 10px uppercase, pill. Keep it as long as the chat only retrieves.

### Focus
Every interactive element shows focus: the base `outline: 2px solid var(--teal); outline-offset: 3px`, or on white pills, teal-bright border plus the 4px teal-glow ring. Never remove focus without replacing it.

---

## 7. Drawings

Every module card, page hero and video thumbnail carries a drawing in **fdebench's style**. Make them with `tools/gen_art.py` (prompts and history in `proof/art/PROMPTS.md`).

- **Style**: fine black ink linework, loose light watercolour washes, lots of white, transparent background, no scenery behind the subjects.
- **People**: a man and a woman together, adults with natural proportions, warm and grounded. Not cartoons, not 3D clay.
- **Colour**: **coral `#FF6A4D` is the single focal point**, teal `#1D7581` second, then sage, sand and warm greys.
- **The robot**: small and friendly, white, rounded head, dark visor with a smile, coral antenna tip and joints. It helps; it is never the hero.
- **No text** in drawings: no letters, logos or UI labels. Screens show shapes only.
- **For thumbnails**, ask for the subjects in the right two thirds and the left third empty.
- The image API returns ~1.6MB WebP; recompress (Pillow, quality 80) before committing. Card thumbnails are 720px wide.

---

## 8. Video thumbnails

Every video gets one (1280×720 JPEG), made with:

```sh
tools/make_thumb.sh <drawing.webp> "<kicker>" "<title with one <em>word</em>>" "<meta>" <out.jpg>
# tools/make_thumb.sh proof/art/welcome-hero.webp "Before you start" "Welcome to the <em>bootcamp.</em>" "Watch first · 5 min" proof/welcome-video/poster.jpg
```

Layout (template `tools/thumb-card.html`):
- White background, drawing on the right at 700px tall, bleeding off the right and bottom edges.
- Top left: "FDE Companion" in ink-3 with the **PRO** badge.
- Left column, 520px wide, centred vertically: gold-ink kicker (19px, uppercase, 0.16em), title (88px, 600, -0.035em) with one serif italic teal word at 1.08em, then a coral dot and the meta line ("Watch first · 5 min") in ink-2.

Done: welcome, the companion video. Still to do: the topic videos.

---

## 9. Words on screen

- Plain, short, active. "Open the course repo", not "Navigate to the repository resource".
- "We", not "I" (except "I'm Hamza" in the welcome).
- No internal codes or old names: no `VST`, `m0`, project names like LUMINA or ARGUS. Use the structure: **Foundation**, **Modules 1–6**, **Voice agents session**, **Demo day**.
- No sales language and no Maven links on the paid site.
- Headlines say something ("The one place for everything in the course"), and carry one italic word.
- Eyebrows and labels are 1–4 words.

---

## 10. Do and don't

| Do | Don't |
|---|---|
| White page, aurora only in heroes and the chat | Warm paper backgrounds, or a dark theme |
| One serif italic word per headline, in teal | Whole serif sentences, or serif in body text |
| One primary teal button per group | Two primary buttons side by side |
| Coral for play buttons, drawings and "look here" | Coral, gold or teal-bright as text colour |
| Teal + gold + coral together only as light | Rainbow fills on flat UI |
| Long, soft, low shadows | Hard drop shadows, or shadows on drawings |
| Pills for every button and chip | Square buttons |
| Ink-and-watercolour drawings with a man, a woman and the robot | Stock photos, icons as illustrations, cartoons, 3D clay |
| Reduced-motion fallback for every animation | Bouncy or flashing motion |
| Change only the thing that was asked | "Clean up" the pro look while making an unrelated change |

---

## 11. Where it lives

| What | File |
|---|---|
| Premium tokens and components | `proof/premium.css` |
| Base tokens (mist, sand, radius, ease, type scale) | the live site's CSS (mirrored into `build/`) |
| Chat styles | the `css` string in `proof/companion.js` |
| Drawing style prompt | `STYLE` in `tools/gen_art.py` |
| Drawing scenes | `proof/art/PROMPTS.md` |
| Thumbnail template | `tools/thumb-card.html`, `tools/make_thumb.sh` |
| Video look (motion, layout, art) | `videos/docs/STYLE.md` |

**Known mismatch:** `videos/docs/STYLE.md` still lists paper as `#FBFAF7`. The site moved to pure white `#ffffff` on 2026-11-11; the videos can keep their warm paper since they're a separate medium, but say so there if that's the intent.
