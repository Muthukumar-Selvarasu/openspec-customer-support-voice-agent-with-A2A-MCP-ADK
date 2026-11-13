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


def test_tab_hold_prevents_default_on_repeat():
    from pathlib import Path

    ui_js = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(encoding="utf-8")
    idx_prevent = ui_js.index("event.preventDefault();")
    idx_repeat = ui_js.index("if (event.repeat) return;")
    assert idx_prevent < idx_repeat
