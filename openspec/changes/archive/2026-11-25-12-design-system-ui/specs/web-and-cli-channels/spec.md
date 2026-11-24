# Spec Delta

## ADDED Requirements

### Requirement: Shared Design System Stylesheet Delivery
The web app SHALL serve a shared design-system stylesheet at `/theme.css` from `src/static/`, defining the light-only color, typography, radius, shadow, glass, and motion tokens from `docs/DESIGN.md`.

#### Scenario: Stylesheet is served from src/static
- **WHEN** a client requests `GET /theme.css`
- **THEN** the response is `200` with `text/css` content type and contains the `:root` design tokens (`--paper`, `--ink`, `--teal`, `--gold`, `--coral`, `--green`, `--ease`)

### Requirement: Light-Only Design System Surfaces and Typography
The shopper page and architecture inspector SHALL default to a pure-white (`#ffffff`) light surface using the shared design-system tokens, sticky white-glass headers, pill-shaped controls, and `Inter Tight` / `Instrument Serif` (italic teal headline accent) with system font fallbacks, and SHALL support an optional user-selected dark theme (`data-theme="dark"`).

#### Scenario: Shopper page loads shared theme and light surface by default
- **WHEN** a client loads `/` with no saved theme preference
- **THEN** the HTML links `/theme.css`, defaults to the pure-white `--paper` light theme, and restricts the drifting aurora backdrop to the sign-in view

#### Scenario: Architecture inspector shares the design system
- **WHEN** a client loads `/architecture`
- **THEN** the HTML links `/theme.css`, uses the sticky glass header, and renders the diagram card with `--lift` shadow and semantic status swatches

### Requirement: Light and Dark Theme Toggle
The shopper page and architecture inspector SHALL provide a header theme toggle (`#themeToggle`) that switches between `light` (preserving the pure-white default theme) and `dark` (`data-theme="dark"` on `<html>`), persisting the choice in `localStorage["cs-theme"]`.

#### Scenario: Switching to dark theme persists across pages
- **WHEN** a user clicks `#themeToggle` to switch to dark mode
- **THEN** `document.documentElement` receives `data-theme="dark"`, `localStorage["cs-theme"]` stores `"dark"`, and both `/` and `/architecture` honor the dark palette on load

### Requirement: Semantic Status and Voice Control Styling
Chat bubbles, pipeline step cards, order status badges, and voice controls SHALL use the semantic palette (`--teal` for primary actions and active voice, `--coral` / `--coral-ink` for active recording warnings and blocked states, `--green` / `--green-soft` for completion, `--gold-ink` for eyebrows/LLM steps) and meet WCAG AA contrast on small text.

#### Scenario: Voice mic states map to semantic tokens
- **WHEN** the voice session is live or actively capturing push-to-talk audio
- **THEN** `.vbtn.live` uses `--teal` and `.vbtn.on` uses coral warning styling without hard-coded off-palette colors

### Requirement: Keyboard Focus and Reduced-Motion Accessibility
All interactive buttons, links, inputs, and chips SHALL display a visible keyboard focus ring (`--teal` outline or `--teal-bright` border with `--teal-glow`), and all entrance or ambient animations SHALL be disabled under `@media (prefers-reduced-motion: reduce)`.

#### Scenario: Reduced motion disables animations
- **WHEN** the browser prefers reduced motion (`prefers-reduced-motion: reduce`)
- **THEN** aurora drift, card lift transitions, and message entrance animations are disabled

