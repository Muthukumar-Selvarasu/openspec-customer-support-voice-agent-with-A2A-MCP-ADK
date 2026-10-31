"""Per-turn Explain / Quick demo mode. No live Gemini call."""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "src" / "static" / "index.html"
VOICE_UI = ROOT / "src" / "voice" / "ui.js"

USER = "alice.jones@example.com"
ANSWER = "Your order is SHIPPED."


class _FinalEvent:
    def __init__(self, text: str = ANSWER) -> None:
        self.partial = False
        self.author = "customer_support_assistant"
        self.content = SimpleNamespace(parts=[SimpleNamespace(text=text)])
        self.usage_metadata = SimpleNamespace(prompt_token_count=2, candidates_token_count=3)

    def get_function_calls(self):
        return []

    def get_function_responses(self):
        return []

    def is_final_response(self) -> bool:
        return True


class _FakeRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run_async(self, **kwargs):
        self.calls += 1
        yield _FinalEvent()


def _keys(events: list[dict]) -> list[tuple]:
    return [(event["type"], event.get("key")) for event in events]


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):
    import src.api.web as web

    monkeypatch.setenv("MASK", "true")
    return web


async def test_pipeline_quick_yields_sanitizer_and_final_without_judge_or_masker(web, monkeypatch) -> None:
    counts = {"judge": 0, "mask": 0}

    async def judge(text: str) -> tuple[bool, str]:
        counts["judge"] += 1
        return True, text

    async def mask(text: str) -> tuple[str, str]:
        counts["mask"] += 1
        return text, "no PII found, response unchanged"

    monkeypatch.setattr(web, "_judge", judge)
    monkeypatch.setattr(web, "_mask", mask)
    flags = web.demo_pipeline_kwargs("quick", stream_endpoint=True)
    assert flags == {"judge": False, "mask": False, "stream": True}
    events = [
        event
        async for event in web.text_pipeline(
            _FakeRunner(),
            USER,
            "Where is order 4?",
            **flags,
        )
    ]
    keys = _keys(events)
    assert ("step", "sanitize") in keys
    assert ("final", None) in keys
    assert not any(key in ("judge", "mask") for _, key in keys)
    final = next(event for event in events if event["type"] == "final")
    assert final["blocked"] is False
    assert final["response"] == ANSWER
    assert counts == {"judge": 0, "mask": 0}


async def test_pipeline_explain_calls_judge_and_masker(web, monkeypatch) -> None:
    counts = {"judge": 0, "mask": 0}
    hosts: list[tuple[str, int]] = []

    async def judge(text: str) -> tuple[bool, str]:
        counts["judge"] += 1
        settings = web.resolve_service_settings()
        hosts.append((settings.judge_host, settings.judge_port))
        return True, text

    async def mask(text: str) -> tuple[str, str]:
        counts["mask"] += 1
        settings = web.resolve_service_settings()
        hosts.append((settings.mask_host, settings.mask_port))
        return text, "no PII found, response unchanged"

    monkeypatch.setattr(web, "_judge", judge)
    monkeypatch.setattr(web, "_mask", mask)
    for mode in (None, "explain", "Explain", "fast", ""):
        counts["judge"] = counts["mask"] = 0
        hosts.clear()
        flags = web.demo_pipeline_kwargs(mode, stream_endpoint=True)
        assert flags["judge"] is True
        assert flags["mask"] is True
        assert flags["stream"] is False
        events = [
            event
            async for event in web.text_pipeline(
                _FakeRunner(),
                USER,
                "Where is order 4?",
                **flags,
            )
        ]
        keys = _keys(events)
        assert ("step", "sanitize") in keys
        assert ("step", "judge") in keys
        assert ("step", "mask") in keys
        assert events[-1]["type"] == "final"
        judge_at = next(i for i, event in enumerate(events) if event.get("key") == "judge")
        mask_at = next(i for i, event in enumerate(events) if event.get("key") == "mask")
        assert judge_at < mask_at < len(events) - 1
        assert counts == {"judge": 1, "mask": 1}
        assert hosts[0][1] == web.resolve_service_settings().judge_port
        assert hosts[1][1] == web.resolve_service_settings().mask_port

    source = inspect.getsource(web.resolve_service_settings)
    assert 'A2A_JUDGE_HOST' in source
    assert 'A2A_JUDGE_PORT' in source
    assert 'A2A_MASK_HOST' in source
    assert 'A2A_MASK_PORT' in source
    assert web.DEFAULT_JUDGE_HOST == "localhost"
    assert web.DEFAULT_JUDGE_PORT == 10002
    assert web.DEFAULT_MASK_HOST == "localhost"
    assert web.DEFAULT_MASK_PORT == 10003
    assert 'os.getenv("MASK", "true")' in inspect.getsource(web.mask_enabled)


def test_pipeline_chat_endpoints_pass_mode(web, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    counts = {"judge": 0, "mask": 0}

    async def judge(text: str) -> tuple[bool, str]:
        counts["judge"] += 1
        return True, text

    async def mask(text: str) -> tuple[str, str]:
        counts["mask"] += 1
        return text, "no PII found, response unchanged"

    monkeypatch.setattr(web, "_judge", judge)
    monkeypatch.setattr(web, "_mask", mask)
    web._runners.clear()
    web._runners[USER] = _FakeRunner()
    client = TestClient(web.app)

    quick = client.post(
        "/api/chat/stream",
        json={"user_id": USER, "message": "Where is order 4?", "mode": "quick"},
    )
    assert quick.status_code == 200
    events = [json.loads(line) for line in quick.text.splitlines() if line.strip()]
    keys = _keys(events)
    assert ("step", "sanitize") in keys
    assert ("final", None) in keys
    assert not any(key in ("judge", "mask") for _, key in keys)
    assert counts == {"judge": 0, "mask": 0}

    counts["judge"] = counts["mask"] = 0
    explained = client.post(
        "/api/chat",
        json={"user_id": USER, "message": "Where is order 4?"},
    )
    assert explained.status_code == 200
    body = explained.json()
    assert body["blocked"] is False
    assert body["response"] == ANSWER
    assert counts == {"judge": 1, "mask": 1}

    counts["judge"] = counts["mask"] = 0
    unknown = client.post(
        "/api/chat/stream",
        json={"user_id": USER, "message": "Where is order 4?", "mode": "turbo"},
    )
    assert unknown.status_code == 200
    events = [json.loads(line) for line in unknown.text.splitlines() if line.strip()]
    keys = _keys(events)
    assert ("step", "judge") in keys
    assert ("step", "mask") in keys
    assert counts == {"judge": 1, "mask": 1}


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    quote = None
    escape = False
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unclosed {signature}")


def test_toggle_defaults_to_explain_persists_and_hides_the_step_list() -> None:
    html = INDEX.read_text(encoding="utf-8")
    voice = VOICE_UI.read_text(encoding="utf-8")
    header = html.split("<header>", 1)[1].split("</header>", 1)[0]
    explain = header.split('id="modeExplain"', 1)[1].split("</button>", 1)[0]
    quick = header.split('id="modeQuick"', 1)[1].split("</button>", 1)[0]
    assert ">Explain" in explain
    assert "mode-btn on" in explain
    assert 'aria-pressed="true"' in explain
    assert ">Quick" in quick
    assert "mode-btn on" not in quick
    assert 'localStorage["cs-demo-mode"]' in html
    assert "mode:demoMode()" in html
    assert "/api/chat/stream" in html
    opened = voice.index("ws.onopen = resolve")
    assert voice.index("sendDemoMode();", opened) > opened
    assert 'JSON.stringify({ type: "mode", mode: demoMode() })' in voice
    assert "window.csSendDemoMode = sendDemoMode" in voice

    chat = html.split("fetch('/api/chat/stream'", 1)[1]
    start = chat.index("body:JSON.stringify(") + len("body:JSON.stringify(")
    depth = 0
    end = None
    for index, char in enumerate(chat[start:], start):
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                end = index
                break
            depth -= 1
    assert end is not None
    payload = chat[start:end]
    script = "\n".join(
        [
            "const bag = {};",
            "globalThis.localStorage = new Proxy(bag, {",
            "  get(target, prop) { return target[prop]; },",
            "  set(target, prop, value) { target[prop] = value; return true; },",
            "});",
            "function button(){ const classes = new Set(); return { classes, attrs: {},",
            "  classList: { toggle(name, on){ if(on) classes.add(name); else classes.delete(name); } },",
            "  setAttribute(key, value){ this.attrs[key] = value; } }; }",
            "const buttons = { modeExplain: button(), modeQuick: button() };",
            "globalThis.document = { getElementById(id){ return buttons[id]; } };",
            "globalThis.window = globalThis;",
            "let ws = null;",
            "const sent = [];",
            _extract_function(html, "function demoMode("),
            _extract_function(html, "function applyDemoMode("),
            _extract_function(html, "function setDemoMode("),
            _extract_function(voice, "function sendDemoMode("),
            "window.csSendDemoMode = sendDemoMode;",
            "const posted = []; let panels = 0;",
            "function archEvent(event){ posted.push(event); }",
            "function setStatus(node, text){ node.bubble.innerHTML = text + '…'; }",
            "function stageStart(){ panels += 1; }",
            "function setTrace(){ panels += 1; }",
            "function stageDone(){ panels += 1; }",
            "function addLLM(){ panels += 1; }",
            "function addToolCall(){ panels += 1; }",
            "function addToolResult(){ panels += 1; }",
            "function md(text){ return String(text); }",
            "function scroll(){}",
            _extract_function(html, "function renderEvent("),
            "function bubbleNode(){",
            "  const bubble = { innerHTML: '<span class=\"typing\">thinking…</span>', textContent: 'thinking…' };",
            "  return { classList: { add(){} }, querySelector(sel){ return sel === '.bubble' ? bubble : null; }, bubble };",
            "}",
            "function render(mode, event){",
            "  localStorage['cs-demo-mode'] = mode;",
            "  posted.length = 0; panels = 0;",
            "  const node = bubbleNode();",
            "  renderEvent(node, event);",
            "  return { html: node.bubble.innerHTML, panels, posted: posted.length };",
            "}",
            "const result = {};",
            "result.first = demoMode();",
            "applyDemoMode(demoMode());",
            "result.explainOn = buttons.modeExplain.classes.has('on');",
            "result.quickOn = buttons.modeQuick.classes.has('on');",
            "result.explainPressed = buttons.modeExplain.attrs['aria-pressed'];",
            "ws = { readyState: 1, send(body){ sent.push(JSON.parse(body)); } };",
            "setDemoMode('quick');",
            "result.saved = localStorage['cs-demo-mode'];",
            "result.afterToggle = demoMode();",
            "result.quickOnAfter = buttons.modeQuick.classes.has('on');",
            "result.explainOnAfter = buttons.modeExplain.classes.has('on');",
            "result.voiceOnToggle = sent.slice();",
            "result.reload = demoMode();",
            "sent.length = 0;",
            "localStorage['cs-demo-mode'] = 'explain';",
            "sendDemoMode();",
            "result.voiceOnConnect = sent.slice();",
            "localStorage['cs-demo-mode'] = 'fast';",
            "result.unrecognized = demoMode();",
            "const USER = 'alice'; const text = 'Where is order 4?';",
            "localStorage['cs-demo-mode'] = 'quick';",
            f"result.quickBody = {payload};",
            "localStorage['cs-demo-mode'] = 'explain';",
            f"result.explainBody = {payload};",
            "result.quickStage = render('quick', {type:'stage', stage:'Sanitizing input', key:'sanitize'});",
            "result.explainStage = render('explain', {type:'stage', stage:'Sanitizing input', key:'sanitize'});",
            "result.quickDelta = render('quick', {type:'delta', text:'Your order is SHIPPED.'});",
            "result.quickFinal = render('quick', {type:'final', blocked:false, response:'Your order is SHIPPED.'});",
            "result.quickStep = render('quick', {type:'step', key:'sanitize', title:'Sanitizer', status:'passed'});",
            "console.log(JSON.stringify(result));",
        ]
    )
    proc = subprocess.run(
        ["node", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["first"] == "explain"
    assert result["explainOn"] is True
    assert result["quickOn"] is False
    assert result["explainPressed"] == "true"
    assert result["saved"] == "quick"
    assert result["afterToggle"] == "quick"
    assert result["reload"] == "quick"
    assert result["quickOnAfter"] is True
    assert result["explainOnAfter"] is False
    assert result["unrecognized"] == "explain"
    assert result["voiceOnToggle"] == [{"type": "mode", "mode": "quick"}]
    assert result["voiceOnConnect"] == [{"type": "mode", "mode": "explain"}]
    assert result["quickBody"] == {
        "user_id": "alice",
        "message": "Where is order 4?",
        "mode": "quick",
    }
    assert result["explainBody"] == {
        "user_id": "alice",
        "message": "Where is order 4?",
        "mode": "explain",
    }
    assert result["quickStage"]["posted"] == 1
    assert result["quickStage"]["panels"] == 0
    assert "thinking…" in result["quickStage"]["html"]
    assert result["quickStep"]["panels"] == 0
    assert "thinking…" in result["quickStep"]["html"]
    assert result["explainStage"]["panels"] == 1
    assert "Sanitizing input" in result["explainStage"]["html"]
    assert result["quickDelta"]["panels"] == 0
    assert result["quickDelta"]["html"] == "Your order is SHIPPED."
    assert "thinking…" not in result["quickDelta"]["html"]
    assert result["quickFinal"]["html"] == "Your order is SHIPPED."
    assert result["quickFinal"]["posted"] == 1
