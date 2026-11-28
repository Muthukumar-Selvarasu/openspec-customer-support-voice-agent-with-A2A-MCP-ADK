"""Design system UI tests for /theme.css, /, and /architecture."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.web import app

client = TestClient(app)


def test_theme_css_served():
    resp = client.get("/theme.css")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/css")
    css = resp.text
    for token in (
        "--paper:      #ffffff",
        "--ink:",
        "--teal:",
        "--gold:",
        "--coral:",
        "--green:",
        "--ease:",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert token in css
    assert "prefers-color-scheme: dark" not in css


def test_index_design_system_and_dom_ids():
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'href="/theme.css"' in html
    assert "<header>" in html
    assert "ds-aurora" in html
    assert "ds-serif-em" in html
    assert "var(--paper)" in html
    assert "var(--teal)" in html
    assert "var(--coral-ink)" in html
    for dom_id in (
        'id="login"',
        'id="col"',
        'id="footer"',
        'id="input"',
        'id="send"',
        'id="demoMode"',
        'id="guardrailToggles"',
        'id="loginBtn"',
        'id="logout"',
    ):
        assert dom_id in html
    assert "prefers-color-scheme: dark" not in html


def test_architecture_design_system():
    resp = client.get("/architecture")
    assert resp.status_code == 200
    html = resp.text
    assert 'href="/theme.css"' in html
    assert "ds-header" in html
    assert "var(--paper)" in html
    assert "var(--lift)" in html
    assert 'id="svg"' in html
    assert 'id="log"' in html
    assert "prefers-color-scheme: dark" not in html


def test_theme_toggle_dark_and_light():
    css = client.get("/theme.css").text
    assert ':root[data-theme="dark"]' in css
    assert "--paper:      #ffffff" in css
    assert "--paper:       #101415" in css

    for path in ("/", "/architecture"):
        html = client.get(path).text
        assert 'id="themeToggle"' in html
        assert "localStorage['cs-theme']" in html
        assert "applyTheme(localStorage['cs-theme']||'light')" in html
        assert "window.addEventListener('storage'" in html
        assert "e.key==='cs-theme'" in html


def test_index_pill_hover_override_and_aurora_outside_login():
    html = client.get("/").text
    assert ".steps summary .pill:hover:not(:disabled){transform:none}" in html
    assert '<div id="loginScreen">' in html
    # Aurora and grain sit inside #loginScreen BEFORE <div class="login" id="login">
    screen_idx = html.index('<div id="loginScreen">')
    aurora_idx = html.index('<div class="ds-aurora"', screen_idx)
    grain_idx = html.index('<div class="ds-grain"', screen_idx)
    login_idx = html.index('<div class="login" id="login">', screen_idx)
    assert screen_idx < aurora_idx < grain_idx < login_idx
    assert "document.getElementById('loginScreen')" in html


def test_tab_hold_prevents_default_on_repeat():
    from pathlib import Path

    ui_js = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(encoding="utf-8")
    idx_prevent = ui_js.index("event.preventDefault();")
    idx_repeat = ui_js.index("if (event.repeat) return;")
    assert idx_prevent < idx_repeat


def test_architecture_phoenix_url_injection_and_guardrail_labels(monkeypatch):
    import src.api.web as web

    monkeypatch.setenv("PHOENIX_PUBLIC_URL", "https://phoenix.example.com/")
    resp = client.get("/architecture")
    assert resp.status_code == 200
    assert 'href="https://phoenix.example.com"' in resp.text
    assert 'href="http://localhost:6006"' not in resp.text
    assert "guardrail (L1–L3)" in resp.text

    monkeypatch.delenv("PHOENIX_PUBLIC_URL", raising=False)
    monkeypatch.delenv("PHOENIX_URL", raising=False)
    default_resp = client.get("/architecture")
    assert default_resp.status_code == 200
    assert 'href="http://localhost:6006"' in default_resp.text

    for name, info in web.TOOLS.items():
        if info.get("kind") == "MCP":
            assert "MCP Toolbox" in info["path"], name
            assert "Toolbox :5000" not in info["path"], name

    svg_resp = client.get("/architecture.svg")
    assert svg_resp.status_code == 200
    svg = svg_resp.text
    assert "gemini-3.1-flash-live-preview" in svg
    assert "gemini-3.1-flash-lite" not in svg
    for token in (
        "GUARDRAIL",
        "GUARDRAIL · A2A",
        "length &amp; char whitelist",
        "Guardrail L1 · in-process",
        "Security &amp; Topic Judge",
        "Guardrail L2 · security + scope",
        "local regex · :10003",
        "Guardrail L3 · PII scrub",
    ):
        assert token in svg, token

    css = client.get("/theme.css").text
    assert "(light default)" in css
    assert "(light-only)" not in css
    assert ".ds-aurora-wrap" not in css
