# Tasks

## 1. Shared Design System & Static Route

- [x] 1.1 Create `src/static/theme.css` with `:root` color, typography (`Inter Tight`, `Instrument Serif`, system fallbacks), radius, shadow (`--lift`), glass, aurora + 5% film-grain, pill button, focus ring, and `@media (prefers-reduced-motion: reduce)` rules from `docs/DESIGN.md` (using `#6e7575` for `--ink-3` small text AA contrast); verify all required tokens and reduced-motion rules are present.
- [x] 1.2 Add `GET /theme.css` route in `src/api/web.py` serving `src/static/theme.css` with `media_type="text/css"`, and add `test_theme_css_served` in `tests/unit/test_design_system_ui.py` verified via `.venv/bin/pytest tests/unit/test_design_system_ui.py -k theme_css`.

## 2. Shopper Chat & Voice UI (`src/static/index.html`, `src/voice/ui.js`)

- [x] 2.1 Link `/theme.css` in `src/static/index.html`, switch the page canvas to `--paper` (`#ffffff`), replace the header with the sticky white-glass header and pill-shaped mode/guardrail/action controls, and restyle `#login` with the scoped aurora + film-grain backdrop, `24px` card (`--lift` shadow), `--gold-ink` eyebrow, `<em>` Instrument Serif italic teal headline accent, and primary teal gradient Sign-in pill; verify via `test_index_design_system_and_dom_ids` in `tests/unit/test_design_system_ui.py`.
- [x] 2.2 Restyle chat bubbles (teal gradient user bubble, crisp white/mist assistant prose), `.steps` / `.step` / `.rtable` / `.badge` semantic colors (`--teal`, `--green`, `--gold-ink`, `--coral-ink`), `.chip` pills, floating composer with `1.5px` teal-gold-coral gradient input ring, and `.vbtn` / `.vbtn.live` / `.vbtn.on` voice controls (verifying `src/voice/ui.js` class compatibility); verify via `.venv/bin/pytest tests/unit/test_design_system_ui.py tests/unit/test_demo_mode.py tests/unit/test_session_refresh.py tests/unit/test_voice.py`.

## 3. Architecture Inspector (`src/static/architecture.html`)

- [x] 3.1 Link `/theme.css` in `src/static/architecture.html`, apply the pure-white page canvas, sticky white-glass header with pill nav links, `24px` card with `--lift` shadow, and semantic legend/log colors (`--teal`, `--coral-ink`, `--green`); verify via `test_architecture_design_system` in `tests/unit/test_design_system_ui.py` (`GET /architecture` returns `200`, links `/theme.css`, and preserves `#svg` and `#log`).
- [x] 3.2 Add a Light/Dark theme toggle (`#themeToggle`, persisted in `localStorage["cs-theme"]`, defaulting to `light`) across `src/static/theme.css` (`:root[data-theme="dark"]` palette), `src/static/index.html`, and `src/static/architecture.html` while keeping the current light theme intact; verify via `test_theme_toggle_dark_and_light` in `tests/unit/test_design_system_ui.py`.

## 4. Full Suite Verification

- [x] 4.1 Run `.venv/bin/pytest tests/unit/test_design_system_ui.py tests/unit/test_demo_mode.py tests/unit/test_session_refresh.py tests/unit/test_voice.py` and confirm all tests pass with zero failures.
