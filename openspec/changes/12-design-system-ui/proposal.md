# Proposal

## Why

The shopper chat UI (`src/static/index.html`) and cascade architecture inspector (`src/static/architecture.html`) currently use an ad-hoc gray/cyan theme that predates `docs/DESIGN.md`. Aligning the web UI with `docs/DESIGN.md` gives the customer support voice agent and glass-box inspector a cohesive, high-contrast, accessible visual system (pure-white reading surface, semantic teal/gold/coral/green tokens, glass header, pill controls, and reduced-motion support) without altering backend APIs or pipeline behavior.

## What Changes

- Introduce a shared stylesheet (`src/static/theme.css`) served by `src/api/web.py` (`GET /theme.css`) with the `:root` color, typography, radius, shadow, glass, and motion tokens from `docs/DESIGN.md`.
- Update `src/static/index.html` to adopt the pure-white `--paper` canvas, `Inter Tight` + `Instrument Serif` (italic teal accent) typography with offline system fallbacks, sticky white-glass header, pill-shaped mode/guardrail/action controls, aurora + film-grain backdrop behind the sign-in card only, gradient-ring composer, and semantic status/step/table styling.
- Update `src/static/architecture.html` to share the same `theme.css` tokens, sticky glass header, `--lift` card surface, and semantic legend/log colors.
- Align voice button states in `src/voice/ui.js` and `src/static/index.html` with the semantic `--teal` (listening/live) and `--coral` / `--coral-ink` (recording/active warning) tokens.
- Enforce visible keyboard focus rings on all interactive elements and `@media (prefers-reduced-motion: reduce)` fallbacks for all animations.
- Add unit tests verifying `/theme.css` delivery, design-system token/accessibility invariants in the static pages, and no regressions to existing web routes.

## Capabilities

### New Capabilities

(None)

### Modified Capabilities

- `web-and-cli-channels`: Add visual design-system, contrast/focus accessibility, and reduced-motion requirements for the shopper web UI, voice controls, and architecture inspector while preserving all existing session, demo mode, guardrail, and streaming behaviors.

## Impact

- **Static UI**: `src/static/theme.css` (new), `src/static/index.html`, `src/static/architecture.html`
- **Voice UI script**: `src/voice/ui.js` (CSS class/state alignment only; audio/WebSocket protocol unchanged)
- **Web server**: `src/api/web.py` (new `GET /theme.css` route serving from `src/static/`)
- **Tests**: `tests/unit/test_design_system_ui.py` (new) plus existing `tests/unit/test_demo_mode.py`, `tests/unit/test_session_refresh.py`, and `tests/unit/test_voice.py`

