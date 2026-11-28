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


async def test_voice_explain_calls_judge_only_when_the_blocker_flags(web, monkeypatch) -> None:
    counts = {"judge": 0}

    async def judge(text: str) -> tuple[bool, str]:
        counts["judge"] += 1
        return True, text

    async def mask(text: str) -> tuple[str, str]:
        return text, "no PII found, response unchanged"

    monkeypatch.setattr(web, "_judge", judge)
    monkeypatch.setattr(web, "_mask", mask)

    clean = [
        event
        async for event in web.text_pipeline(
            _FakeRunner(),
            USER,
            "What is my last order?",
            judge=True,
            mask=True,
            stream=True,
            judge_if_flagged=True,
        )
    ]
    assert ("step", "sanitize") in _keys(clean)
    assert not any(event.get("key") == "judge" for event in clean)
    assert counts["judge"] == 0
    assert clean[-1]["type"] == "final"

    flagged = [
        event
        async for event in web.text_pipeline(
            _FakeRunner(),
            USER,
            "'; DROP TABLE users; --",
            judge=True,
            mask=False,
            stream=True,
            judge_if_flagged=True,
        )
    ]
    assert any(event.get("key") == "judge" for event in flagged)
    assert counts["judge"] == 1

    typed = [
        event
        async for event in web.text_pipeline(
            _FakeRunner(),
            USER,
            "What is my last order?",
            **web.demo_pipeline_kwargs("explain", stream_endpoint=True),
        )
    ]
    assert any(event.get("key") == "judge" for event in typed)
    assert counts["judge"] == 2


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
    assert 'id="demoMode"' in header and 'style="display:none"' in header.split('id="demoMode"', 1)[1].split(">", 1)[0]
    assert 'id="guardrailToggles"' in header and 'style="display:none"' in header.split('id="guardrailToggles"', 1)[1].split(">", 1)[0]
    assert "display:none" not in header.split('id="archLink"', 1)[1].split(">", 1)[0]
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


def test_guardrails_toggles_override_judge_and_mask_in_both_explain_and_quick(web) -> None:
    from fastapi.testclient import TestClient

    html = INDEX.read_text(encoding="utf-8")
    voice = VOICE_UI.read_text(encoding="utf-8")
    assert 'id="toggleJudge"' in html
    assert 'id="toggleMask"' in html
    assert "window.csSendGuardrails = sendGuardrails" in voice

    web._guardrails.clear()
    client = TestClient(web.app)
    resp = client.post(
        "/api/guardrails",
        json={"user_id": USER, "judge": True, "mask": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "judge": True, "mask": True}
    # In Quick mode, explicit user guardrails enable Judge & Masker
    assert web.demo_pipeline_kwargs("quick", stream_endpoint=True, user_id=USER) == {
        "judge": True,
        "mask": True,
        "stream": False,
    }
    # In Explain mode, explicit user guardrails can disable Judge & Masker
    client.post(
        "/api/guardrails",
        json={"user_id": USER, "judge": False, "mask": False},
    )
    assert web.demo_pipeline_kwargs("explain", stream_endpoint=True, user_id=USER) == {
        "judge": False,
        "mask": False,
        "stream": True,
    }
    # Quick mode respects stream_endpoint=False (non-streaming /api/chat)
    web._guardrails.clear()
    assert web.demo_pipeline_kwargs("quick", stream_endpoint=False, user_id=USER) == {
        "judge": False,
        "mask": False,
        "stream": False,
    }

    # Partial update preserves omitted field; explicit null clears override
    client.post("/api/guardrails", json={"user_id": USER, "judge": True, "mask": True})
    r_partial = client.post("/api/guardrails", json={"user_id": USER, "judge": False})
    assert r_partial.json() == {"ok": True, "judge": False, "mask": True}
    r_clear_one = client.post("/api/guardrails", json={"user_id": USER, "judge": None})
    assert r_clear_one.json() == {"ok": True, "mask": True}
    assert web._guardrails[USER] == {"mask": True}
    r_clear_all = client.post("/api/guardrails", json={"user_id": USER, "mask": None})
    assert r_clear_all.json() == {"ok": True}
    assert USER not in web._guardrails
    web._guardrails.clear()


def test_guardrails_cleared_on_login_and_flush_and_not_pushed_by_default(web, monkeypatch) -> None:
    import asyncio
    from fastapi.testclient import TestClient

    web._guardrails[USER] = {"judge": True, "mask": True}
    asyncio.run(web._flush_shopper(USER))
    assert USER not in web._guardrails

    web._guardrails[USER] = {"judge": True, "mask": True}
    monkeypatch.setattr(
        web,
        "authenticate_user",
        lambda email, password: {
            "user_id": 1,
            "email": USER,
            "full_name": "Alice Jones",
            "is_premium_customer": True,
            "total_items_purchased": 5,
        },
    )
    monkeypatch.setattr(web, "get_database_tools", lambda: [])
    client = TestClient(web.app)
    resp = client.post("/api/login", json={"email": USER, "password": "alice"})
    assert resp.status_code == 200
    assert USER not in web._guardrails

    # Client-side JS: fresh login & WS open do NOT push overrides; reload with explicit choice DOES;
    # setDemoMode resets explicit overrides cleanly.
    html = INDEX.read_text(encoding="utf-8")
    voice = VOICE_UI.read_text(encoding="utf-8")
    script = "\n".join(
        [
            "const bag = {};",
            "globalThis.localStorage = new Proxy(bag, {",
            "  get(target, prop) { return target[prop]; },",
            "  set(target, prop, value) { target[prop] = value; return true; },",
            "  deleteProperty(target, prop) { delete target[prop]; return true; },",
            "});",
            "function button(){ const classes = new Set(); return { classes, attrs: {}, textContent: '',",
            "  classList: { toggle(name, on){ if(on) classes.add(name); else classes.delete(name); } },",
            "  setAttribute(key, value){ this.attrs[key] = value; } }; }",
            "const buttons = { modeExplain: button(), modeQuick: button(), toggleJudge: button(), toggleMask: button() };",
            "globalThis.document = { getElementById(id){ return buttons[id]; } };",
            "globalThis.window = globalThis;",
            "var USER = 'alice.jones@example.com';",
            "const fetches = [];",
            "globalThis.fetch = (url, opts) => { fetches.push({ url, body: JSON.parse(opts.body) }); return Promise.resolve({ ok: true }); };",
            "const wsSent = [];",
            "let ws = { readyState: 1, send(body) { wsSent.push(JSON.parse(body)); } };",
            _extract_function(html, "function demoMode("),
            _extract_function(html, "function applyDemoMode("),
            _extract_function(html, "function setDemoMode("),
            _extract_function(html, "function explicitGuardrails("),
            _extract_function(html, "function judgeEnabled("),
            _extract_function(html, "function maskEnabled("),
            _extract_function(html, "function applyGuardrails("),
            _extract_function(html, "function syncGuardrails("),
            _extract_function(voice, "function sendDemoMode("),
            _extract_function(voice, "function sendGuardrails("),
            "window.csSendDemoMode = sendDemoMode;",
            "window.csSendGuardrails = sendGuardrails;",
            "// 1. Fresh login + WS open with no explicit overrides sends nothing",
            "syncGuardrails();",
            "sendGuardrails();",
            "const freshFetches = fetches.slice();",
            "const freshWs = wsSent.slice();",
            "// 2. Explicit user override persists and syncs on reload / WS open",
            "localStorage['cs-judge'] = 'off';",
            "syncGuardrails();",
            "const afterExplicitFetches = fetches.slice();",
            "const afterExplicitWs = wsSent.slice();",
            "// 3. Switching to quick clears overrides and updates visuals to OFF",
            "fetches.length = 0; wsSent.length = 0;",
            "setDemoMode('quick');",
            "const afterSwitch = {",
            "  csJudge: localStorage['cs-judge'] ?? null,",
            "  csMask: localStorage['cs-mask'] ?? null,",
            "  judgeText: buttons.toggleJudge.textContent,",
            "  maskText: buttons.toggleMask.textContent,",
            "  fetches: fetches.slice(),",
            "  ws: wsSent.slice(),",
            "};",
            "console.log(JSON.stringify({ freshFetches, freshWs, afterExplicitFetches, afterExplicitWs, afterSwitch }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["freshFetches"] == []
    assert result["freshWs"] == []
    assert result["afterExplicitFetches"] == [
        {"url": "/api/guardrails", "body": {"user_id": USER, "judge": False}}
    ]
    assert result["afterExplicitWs"] == [{"type": "guardrails", "judge": False}]
    assert result["afterSwitch"]["csJudge"] is None
    assert result["afterSwitch"]["csMask"] is None
    assert result["afterSwitch"]["judgeText"] == "Judge: OFF"
    assert result["afterSwitch"]["maskText"] == "Masker: OFF"
    assert result["afterSwitch"]["fetches"] == [
        {"url": "/api/guardrails", "body": {"user_id": USER, "judge": None, "mask": None}}
    ]
    assert result["afterSwitch"]["ws"] == [
        {"type": "mode", "mode": "quick", "judge": None, "mask": None}
    ]


async def test_parallel_judge_and_agent_cancels_agent_on_block(web, monkeypatch) -> None:
    """Strict pre-agent gating: Judge must complete before runner.run_async starts."""
    timeline: list[str] = []

    class _GatedRunner:
        def __init__(self) -> None:
            self.calls = 0

        async def run_async(self, **kwargs):
            self.calls += 1
            timeline.append("agent_start")
            yield _FinalEvent()

    async def judge_pass(text: str) -> tuple[bool, str]:
        timeline.append("judge_start")
        timeline.append("judge_end")
        return True, "ALLOW"

    async def judge_block(text: str) -> tuple[bool, str]:
        timeline.append("judge_block")
        return False, "BLOCKED"

    runner_pass = _GatedRunner()
    monkeypatch.setattr(web, "_judge", judge_pass)
    passed_events = [
        ev
        async for ev in web.text_pipeline(
            runner_pass,
            USER,
            "Where is order 4?",
            judge=True,
            mask=False,
            stream=True,
        )
    ]
    assert passed_events[-1] == {"type": "final", "blocked": False, "response": ANSWER}
    assert runner_pass.calls == 1
    assert timeline == ["judge_start", "judge_end", "agent_start"]

    timeline.clear()
    runner_block = _GatedRunner()
    monkeypatch.setattr(web, "_judge", judge_block)
    blocked_events = [
        ev
        async for ev in web.text_pipeline(
            runner_block,
            USER,
            "Where is order 4?",
            judge=True,
            mask=False,
            stream=True,
        )
    ]
    assert blocked_events[-1]["type"] == "final"
    assert blocked_events[-1]["blocked"] is True
    assert blocked_events[-1]["stage"] == "judge"
    assert runner_block.calls == 0
    assert timeline == ["judge_block"]
    assert not any(ev["type"] in ("llm", "delta") for ev in blocked_events)


def test_what_happened_orders_stt_first_and_llm_before_tts() -> None:
    html = INDEX.read_text(encoding="utf-8")
    voice = VOICE_UI.read_text(encoding="utf-8")
    assert '(data.type === "stage" || data.type === "step") && data.key === "stt"' in voice
    script = "\n".join(
        [
            "const rows = [];",
            "const pill = { textContent: '0' };",
            "const panel = {",
            "  querySelector(sel) {",
            "    if (sel === '.pill') return pill;",
            "    if (sel === '.step:not([data-key=\"stt\"])') return rows.find(r => r.key !== 'stt') || null;",
            "    if (sel === '.step[data-key=\"mask\"],.step[data-key=\"tts\"]') return rows.find(r => r.key === 'mask' || r.key === 'tts') || null;",
            "    if (sel === '.step[data-key=\"tts\"]') return rows.find(r => r.key === 'tts') || null;",
            "    return null;",
            "  },",
            "  querySelectorAll() { return rows; },",
            "  appendChild(row) { rows.push(row); },",
            "  insertBefore(row, before) {",
            "    const idx = rows.indexOf(before);",
            "    if (idx >= 0) rows.splice(idx, 0, row);",
            "    else rows.push(row);",
            "  },",
            "};",
            "function stepsPanel() { return panel; }",
            "function el(html) {",
            "  const m = html.match(/data-key=\"([^\"]+)\"/);",
            "  return { html, key: m ? m[1] : null };",
            "}",
            "function scroll() {}",
            _extract_function(html, "function addRow("),
            "addRow({}, 'sanitize', 'sanitize');",
            "addRow({}, 'tts-start', 'tts');",
            "addRow({}, 'gemini-llm', undefined);",
            "addRow({}, 'mask-step', 'mask');",
            "addRow({}, 'stt-step', 'stt');",
            "console.log(JSON.stringify(rows.map(r => r.key || 'llm')));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ["stt", "sanitize", "llm", "mask", "tts"]


def test_chat_and_chat_stream_record_sanitized_user_text(web, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    async def judge(text: str) -> tuple[bool, str]:
        return True, "ALLOW"

    async def mask(text: str) -> tuple[str, str]:
        return text, "no PII found, response unchanged"

    monkeypatch.setattr(web, "_judge", judge)
    monkeypatch.setattr(web, "_mask", mask)
    web._runners.clear()
    web._transcripts.clear()
    web._runners[USER] = _FakeRunner()
    client = TestClient(web.app)

    r_chat = client.post(
        "/api/chat",
        json={"user_id": USER, "message": "Status of order #5?", "mode": "quick"},
    )
    assert r_chat.status_code == 200
    assert web._transcripts[USER][0] == {"role": "user", "content": "Status of order 5?"}

    web._transcripts.clear()
    r_stream = client.post(
        "/api/chat/stream",
        json={"user_id": USER, "message": "Status of order #7?", "mode": "quick"},
    )
    assert r_stream.status_code == 200
    assert web._transcripts[USER][0] == {"role": "user", "content": "Status of order 7?"}


async def test_resolve_trace_url_uses_cooldown_fallback_and_passes_api_key(web, monkeypatch) -> None:
    import io
    import threading
    from types import SimpleNamespace

    monkeypatch.setenv("TELEMETRY", "true")
    monkeypatch.setenv("PHOENIX_URL", "http://phoenix.internal:6006")
    monkeypatch.setenv("PHOENIX_PUBLIC_URL", "https://phoenix.public")
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.setattr(web, "_phoenix_project", None)
    monkeypatch.setattr(web, "_phoenix_failed_until", 0.0)

    span = SimpleNamespace(get_span_context=lambda: SimpleNamespace(trace_id=0xABC))
    calls: list[dict] = []
    main_tid = threading.get_ident()

    def failing_urlopen(req, timeout=2):
        calls.append({"thread": threading.get_ident(), "headers": dict(req.header_items())})
        raise OSError("phoenix down")

    monkeypatch.setattr(web.urllib.request, "urlopen", failing_urlopen)

    first = await web.resolve_trace_url(span)
    second = await web.resolve_trace_url(span)
    assert first == {"trace_id": f"{0xABC:032x}", "url": "https://phoenix.public/projects"}
    assert second == first
    # Offloaded to a worker thread and second call hit the cooldown without another HTTP call
    assert len(calls) == 1
    assert calls[0]["thread"] != main_tid

    # Reset cooldown and verify Authorization: Bearer <PHOENIX_API_KEY> header is sent when set
    monkeypatch.setattr(web, "_phoenix_project", None)
    monkeypatch.setattr(web, "_phoenix_failed_until", 0.0)
    monkeypatch.setenv("PHOENIX_API_KEY", "phx-secret-key")
    auth_seen: list[str | None] = []

    class _Resp:
        def __enter__(self):
            return io.StringIO('{"data": [{"id": "proj-42", "name": "default"}]}')

        def __exit__(self, *args):
            return False

    def ok_urlopen(req, timeout=2):
        auth_seen.append(req.get_header("Authorization"))
        return _Resp()

    monkeypatch.setattr(web.urllib.request, "urlopen", ok_urlopen)
    linked = await web.resolve_trace_url(span)
    assert auth_seen == ["Bearer phx-secret-key"]
    assert linked == {
        "trace_id": f"{0xABC:032x}",
        "url": f"https://phoenix.public/projects/proj-42/traces/{0xABC:032x}",
    }
    # Clean up cached module global for subsequent tests
    monkeypatch.setattr(web, "_phoenix_project", None)
    monkeypatch.setattr(web, "_phoenix_failed_until", 0.0)
