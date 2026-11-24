# Design

## Context

See `proposal.md` for motivation. Currently `src/static/index.html` and `src/static/architecture.html` inline their own `:root` CSS variables (`--bg:#f7f8fa`, `--accent:#0f9aae`, system fonts) and `src/api/web.py` serves `/`, `/architecture`, and `/architecture.svg` from `src/static/`. `src/voice/ui.js` injects the voice mic button (`.vbtn`, `.vbtn.live`, `.vbtn.on`) into `.inwrap` and relies on DOM IDs (`#col`, `#login`, `#footer`, `#input`, `#send`, `#voiceStatus`, `#demoMode`, `#guardrailToggles`).

## Goals / Non-Goals

**Goals:**
- Centralize all `docs/DESIGN.md` tokens and shared component primitives (glass header, pills, aurora backdrop, focus rings, reduced-motion rules) in `src/static/theme.css`.
- Apply the visual system across `src/static/index.html` and `src/static/architecture.html` without changing any DOM IDs, JS event contracts, or API payloads.
- Keep small-caption text AA-compliant (`#6e7575` for `--ink-3` on white) and guarantee offline usability via system font fallbacks.

**Non-Goals:**
- Course-site-specific elements from `docs/DESIGN.md` (PRO badge, module door cards, welcome video modal, `tools/make_thumb.sh`, `tools/gen_art.py` illustrations).
- Changes to FastAPI chat/voice/A2A/MCP backend logic or `src/api/web.py` service URL configuration (existing env-driven host/port settings remain untouched).

## Decisions

1. **Shared `src/static/theme.css` served at `GET /theme.css`**
   - *Rationale*: Both `index.html` and `architecture.html` share the exact `:root` tokens, sticky white-glass header, pill buttons, focus rings, and `@media (prefers-reduced-motion: reduce)` rules. Extracting them avoids duplicating ~120 lines of CSS across HTML files.
   - *Alternative considered*: Inlining tokens in each HTML file. Rejected because it drifts easily and violates DRY.

2. **Google Fonts `@import` with system font stack fallbacks**
   - *Rationale*: `docs/DESIGN.md` specifies `Inter Tight` and `Instrument Serif` (italic). Including `@import` in `theme.css` with `"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif` and `Georgia, serif` fallbacks gives the exact typography online while degrading cleanly in offline/air-gapped test environments.

3. **Aurora backdrop scoped to `#login` view only**
   - *Rationale*: `docs/DESIGN.md` explicitly states: "Use the aurora for heroes, the welcome screen and the chat panel; not behind body text." Scoping `.aurora` behind the sign-in card keeps chat transcripts and pipeline step tables on pure `#ffffff` (`--paper`).

## Risks / Trade-offs

- **Offline font load latency or blocked CDN** → System font fallbacks (`--sans`, `--serif`, `--mono`) render immediately via `display=swap` without blocking page load or tests.
- **Voice UI DOM coupling** → `src/voice/ui.js` queries `.inwrap` and toggles `.vbtn.live` / `.vbtn.on`. Keeping all existing class names and IDs intact ensures `tests/unit/test_voice.py`, `tests/unit/test_demo_mode.py`, and `tests/unit/test_session_refresh.py` remain green.

