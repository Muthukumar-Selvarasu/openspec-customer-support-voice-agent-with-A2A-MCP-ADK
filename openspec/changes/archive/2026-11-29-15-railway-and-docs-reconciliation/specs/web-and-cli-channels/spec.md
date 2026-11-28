# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Light-Only Design System Surfaces and Typography`
- TO: `### Requirement: Design System Surfaces and Typography`

## MODIFIED Requirements

### Requirement: Env-Driven Service URLs
The web app SHALL read `TOOLBOX_URL`, `A2A_*`, `PHOENIX_URL`, `PHOENIX_PUBLIC_URL`, `HOST`, and `PORT` (`WEB_PORT` alias) with localhost defaults, without requiring Toolbox at import time. `GET /architecture` SHALL inject `phoenix_public_url` into `"Open Phoenix"`, and tool inspector paths SHALL show `"MCP Toolbox"` instead of hardcoded `"Toolbox :5000"`.

#### Scenario: Local defaults work without extra env
- **WHEN** those variables are unset
- **THEN** the app targets `127.0.0.1` toolbox `:5000`, A2A `:10002`/`:10003`, Phoenix `:6006`, and web `:8000`

#### Scenario: WEB_PORT aliases PORT
- **WHEN** `PORT` is unset and `WEB_PORT=8000`
- **THEN** the web process listens on port `8000`

#### Scenario: Static pages resolve from src/static
- **WHEN** `GET /`, `GET /architecture`, or `GET /architecture.svg` is served from `src/api/web.py`
- **THEN** files are read from `src/static/`, not `src/api/static/`

#### Scenario: Architecture page resolves Open Phoenix link from PHOENIX_PUBLIC_URL
- **WHEN** `PHOENIX_PUBLIC_URL=https://phoenix.example.com` and a client GETs `/architecture`
- **THEN** the `"Open Phoenix"` anchor targets `https://phoenix.example.com` instead of `http://localhost:6006`

### Requirement: Shared Design System Stylesheet Delivery
The web app SHALL serve a shared design-system stylesheet at `/theme.css` from `src/static/`, defining the light base color, typography, radius, shadow, glass, and motion tokens adapted from `docs/DESIGN.md`, plus an app-specific dark palette (`:root[data-theme="dark"]`).

#### Scenario: Stylesheet is served from src/static
- **WHEN** a client requests `GET /theme.css`
- **THEN** the response is `200` with `text/css` content type and contains the `:root` light base tokens (`--paper`, `--ink`, `--teal`, `--gold`, `--coral`, `--green`, `--ease`) and `:root[data-theme="dark"]` overrides

### Requirement: Design System Surfaces and Typography
The shopper page and architecture inspector SHALL default to a pure-white (`#ffffff`) light surface using the shared design-system tokens, sticky white-glass headers, pill-shaped controls, and `Inter Tight` / `Instrument Serif` (italic teal headline accent) with system font fallbacks, and SHALL support an optional user-selected dark theme (`data-theme="dark"`).

#### Scenario: Shopper page loads shared theme and light surface by default
- **WHEN** a client loads `/` with no saved theme preference
- **THEN** the HTML links `/theme.css`, defaults to the pure-white `--paper` light theme, and restricts the drifting aurora backdrop to the sign-in view

#### Scenario: Architecture inspector shares the design system
- **WHEN** a client loads `/architecture` and `/architecture.svg`
- **THEN** the HTML links `/theme.css`, uses the sticky glass header, renders the diagram card with `--lift` shadow, semantic status swatches, and a `guardrail` legend entry, and `/architecture.svg` explicitly labels the three guardrail layers (`Guardrail L1` Sanitizer `length & char whitelist`, `Guardrail L2` Security & Topic Judge `security + scope`, and `Guardrail L3` Data Masker `local regex · :10003`) plus STT (`gemini-3.1-flash-live-preview`)
