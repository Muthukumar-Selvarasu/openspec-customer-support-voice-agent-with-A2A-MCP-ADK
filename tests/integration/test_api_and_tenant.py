"""Shopper HTTP app, tenant tool callback, and operator CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]

_SERVICE_ENV = (
    "TOOLBOX_URL",
    "A2A_JUDGE_HOST",
    "A2A_JUDGE_PORT",
    "A2A_MASK_HOST",
    "A2A_MASK_PORT",
    "PHOENIX_URL",
    "PHOENIX_PUBLIC_URL",
    "HOST",
    "PORT",
    "WEB_PORT",
)

_STATIC_FILES = (
    "src/static/index.html",
    "src/static/architecture.html",
    "src/static/architecture.svg",
    "diagram.png",
    "src/api/__init__.py",
)


def test_static_files_exist() -> None:
    for relative in _STATIC_FILES:
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_size > 0, relative
    assert (ROOT / "diagram.png").read_bytes().startswith(b"\x89PNG")
    index = (ROOT / "src/static/index.html").read_text(encoding="utf-8")
    assert "/api/login" in index
    assert "/api/chat/stream" in index
    assert "/voice/ui.js" in index
    architecture = (ROOT / "src/static/architecture.html").read_text(encoding="utf-8")
    assert "/architecture.svg" in architecture
    svg = (ROOT / "src/static/architecture.svg").read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<svg")


def _clear_service_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SERVICE_ENV:
        monkeypatch.delenv(name, raising=False)


def test_import_app_does_not_open_toolbox() -> None:
    import src.api.web as web

    assert web.app.title == "Customer Support Agent"
    assert web._toolbox_client is None
    assert web._database_tools is None
    assert web._REPO_ROOT == ROOT
    assert web._STATIC == ROOT / "src" / "static"
    assert web._TOOLS_YAML == ROOT / "mcp_toolbox" / "tools.yaml"
    assert "get-order-status" in web.TOOLS
    assert (ROOT / "src" / "api" / "static").exists() is False
    source = (ROOT / "src" / "api" / "web.py").read_text(encoding="utf-8")
    assert "ToolboxSyncClient(" not in source.split("def get_database_tools", 1)[0]
    assert "parents[2]" in source
    assert 'parents[1] / "static"' in source


def test_import_app_local_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.web as web

    _clear_service_env(monkeypatch)
    settings = web.resolve_service_settings()
    assert settings.toolbox_url == "http://127.0.0.1:5000"
    assert settings.judge_host == "localhost"
    assert settings.judge_port == 10002
    assert settings.mask_host == "localhost"
    assert settings.mask_port == 10003
    assert settings.phoenix_url == "http://localhost:6006"
    assert settings.phoenix_public_url == "http://localhost:6006"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_import_app_web_port_aliases_port(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.web as web

    _clear_service_env(monkeypatch)
    monkeypatch.setenv("WEB_PORT", "8000")
    assert web.resolve_service_settings().port == 8000
    monkeypatch.setenv("WEB_PORT", "9000")
    assert web.resolve_service_settings().port == 9000
    monkeypatch.setenv("PORT", "8001")
    assert web.resolve_service_settings().port == 8001


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict] = []

    def __call__(self, args: dict) -> dict:
        self.calls.append(dict(args))
        return {"customer_email": args.get("customer_email"), "status": "SHIPPED"}


class _FakeSession:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


class _FakeToolContext:
    def __init__(self, user_id: str) -> None:
        self.session = _FakeSession(user_id)


def test_tenant_callback_overwrites_cross_tenant_email() -> None:
    import src.api.web as web

    tool = _FakeTool("get-order-status")
    args = {
        "order_id": 7,
        "customer_email": "bob.smith@techmail.com",
        "user_id": "bob.smith@techmail.com",
        "email": "bob.smith@techmail.com",
        "user_email": "bob.smith@techmail.com",
    }
    result = web._enforce_tenant_tool_callback(
        tool, args, _FakeToolContext("alice.jones@example.com")
    )
    assert result is None
    assert tool.calls == []
    assert args["order_id"] == 7
    for key in ("customer_email", "user_id", "email", "user_email"):
        assert args[key] == "alice.jones@example.com"


def test_tenant_callback_blocks_update_order_status_without_calling_tool() -> None:
    import src.api.web as web

    tool = _FakeTool("update-order-status")
    args = {"order_id": 7, "status": "CANCELLED", "customer_email": "bob.smith@techmail.com"}
    result = web._enforce_tenant_tool_callback(
        tool, args, _FakeToolContext("alice.jones@example.com")
    )
    assert isinstance(result, dict)
    assert "error" in result
    assert tool.calls == []
    assert "bob.smith@techmail.com" not in str(result)


def test_tenant_callback_is_attached_to_support_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.web as web

    captured: dict = {}

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(web, "LlmAgent", fake_agent)
    monkeypatch.setattr(web, "get_database_tools", lambda: [])
    monkeypatch.setattr(web, "Runner", lambda **kwargs: kwargs["agent"])
    web._build_runner("alice.jones@example.com")
    assert captured["before_tool_callback"] is web._enforce_tenant_tool_callback
    assert "alice.jones@example.com" in captured["instruction"]
    assert captured["tools"][-1] is web.search_memory


def test_pages_served_from_src_static_and_voice_mounted() -> None:
    from fastapi.testclient import TestClient

    import src.api.web as web

    client = TestClient(web.app)
    expected = {
        "/": "src/static/index.html",
        "/architecture": "src/static/architecture.html",
        "/architecture.svg": "src/static/architecture.svg",
    }
    for path, relative in expected.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.content == (ROOT / relative).read_bytes()
    assert web._STATIC == ROOT / "src" / "static"
    assert (ROOT / "src" / "api" / "static").exists() is False

    def _paths(routes) -> set[str]:
        found: set[str] = set()
        for route in routes:
            path = getattr(route, "path", None)
            if path:
                found.add(path)
            included = getattr(route, "original_router", None)
            if included is not None:
                found |= _paths(included.routes)
        return found

    paths = _paths(web.app.routes)
    assert "/voice/ws" in paths
    assert "/voice/ui.js" in paths
    ui = client.get("/voice/ui.js")
    assert ui.status_code == 200
    assert "javascript" in ui.headers["content-type"]


ALICE = "alice.jones@example.com"


def _alice_row() -> dict:
    return {
        "user_id": 1,
        "full_name": "Alice Jones",
        "email": ALICE,
        "is_premium_customer": True,
        "total_items_purchased": 12,
    }


def _patch_login(monkeypatch: pytest.MonkeyPatch, web) -> None:
    def authenticate(email: str, password: str):
        if email == ALICE and password == "alice":
            return _alice_row()
        return None

    monkeypatch.setattr(web, "authenticate_user", authenticate)
    monkeypatch.setattr(web, "get_database_tools", lambda: [])


class _Fn:
    def __init__(self, name: str, args: dict | None = None, response=None) -> None:
        self.name = name
        self.args = args
        self.response = response


class _AgentEvent:
    def __init__(self, *, text: str = "", calls=None, responses=None, final: bool = False) -> None:
        self.partial = False
        self.author = "customer_support_assistant"
        self.content = SimpleNamespace(parts=[SimpleNamespace(text=text)])
        self.usage_metadata = SimpleNamespace(prompt_token_count=4, candidates_token_count=6)
        self._calls = calls or []
        self._responses = responses or []
        self._final = final

    def get_function_calls(self):
        return self._calls

    def get_function_responses(self):
        return self._responses

    def is_final_response(self) -> bool:
        return self._final


class _ScriptedRunner:
    def __init__(self, events: list) -> None:
        self.events = events
        self.seen: list[str] = []

    async def run_async(self, **kwargs):
        self.seen.append(kwargs["new_message"].parts[0].text)
        for event in self.events:
            yield event


def _order_events(user_id: str, web) -> list:
    """Model asks for Bob's order. The tenant callback scopes the invocation to Alice."""
    asked = {"order_id": 4, "customer_email": "bob.smith@techmail.com"}
    invoked = dict(asked)
    outcome = web._enforce_tenant_tool_callback(
        _FakeTool("get-order-status"), invoked, _FakeToolContext(user_id)
    )
    assert outcome is None
    result = {
        "order_id": invoked["order_id"],
        "customer_email": invoked["customer_email"],
        "status": "SHIPPED",
    }
    assert "bob.smith" not in json.dumps(result)
    return [
        _AgentEvent(calls=[_Fn("get-order-status", asked)]),
        _AgentEvent(responses=[_Fn("get-order-status", response={"result": json.dumps([result])})]),
        _AgentEvent(text="Your order is SHIPPED.", final=True),
    ]


async def _echo_a2a(query: str, host: str, port: int, stream: bool = False) -> str:
    if "DROP TABLE" in query.upper():
        return "BLOCKED"
    return query


def test_chat_login_profile_and_idempotent_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import src.api.web as web

    web._runners.clear()
    web._transcripts.clear()
    _patch_login(monkeypatch, web)
    client = TestClient(web.app)
    first = client.post("/api/login", json={"email": ALICE, "password": "alice"})
    second = client.post("/api/login", json={"email": ALICE, "password": "alice"})
    assert first.status_code == 200
    assert second.status_code == 200
    body = second.json()
    assert body["ok"] is True
    assert body["user_id"] == ALICE
    assert body["full_name"] == "Alice Jones"
    assert body["is_premium"] is True
    rejected = client.post("/api/login", json={"email": ALICE, "password": "nope"})
    assert rejected.status_code == 401


def test_chat_logout_flushes_mem0_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import src.api.web as web

    web._runners.clear()
    web._transcripts.clear()
    _patch_login(monkeypatch, web)
    saved: list[tuple] = []

    def save(messages, user_id):
        saved.append((list(messages), user_id))
        return {"status": "success"}

    monkeypatch.setattr(web, "save_memory", save)
    client = TestClient(web.app)
    client.post("/api/login", json={"email": ALICE, "password": "alice"})
    web._record(ALICE, "user", "Where is order 4?")
    web._record(ALICE, "assistant", "Your order is SHIPPED.")
    first = client.post("/api/logout", json={"user_id": ALICE})
    second = client.post("/api/logout", json={"user_id": ALICE})
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(saved) == 1
    assert saved[0][1] == ALICE
    assert saved[0][0][0]["content"] == "Where is order 4?"


def test_chat_returns_final_assistant_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import src.api.web as web

    web._runners.clear()
    web._transcripts.clear()
    _patch_login(monkeypatch, web)
    monkeypatch.setattr(web, "call_a2a_agent", _echo_a2a)
    monkeypatch.setenv("MASK", "true")
    client = TestClient(web.app)
    anonymous = client.post("/api/chat", json={"user_id": ALICE, "message": "Where is order 4?"})
    assert anonymous.status_code == 401
    client.post("/api/login", json={"email": ALICE, "password": "alice"})
    runner = _ScriptedRunner(_order_events(ALICE, web))
    web._runners[ALICE] = runner
    response = client.post("/api/chat", json={"user_id": ALICE, "message": "Where is order 4?"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["blocked"] is False
    assert body["response"] == "Your order is SHIPPED."
    assert runner.seen == ["Where is order 4?"]
    assert body["tool_calls"][0]["name"] == "get-order-status"
    assert "bob.smith" not in body["tool_calls"][0]["result"]


def test_chat_stream_emits_inspector_events(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import src.api.web as web

    web._runners.clear()
    web._transcripts.clear()
    _patch_login(monkeypatch, web)
    monkeypatch.setattr(web, "call_a2a_agent", _echo_a2a)
    monkeypatch.setenv("MASK", "true")
    client = TestClient(web.app)
    client.post("/api/login", json={"email": ALICE, "password": "alice"})
    web._runners[ALICE] = _ScriptedRunner(_order_events(ALICE, web))
    response = client.post(
        "/api/chat/stream",
        json={"user_id": ALICE, "message": "Where is order 4?"},
    )
    assert response.status_code == 200
    assert "ndjson" in response.headers["content-type"]
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    keys = [(event["type"], event.get("key")) for event in events]
    assert ("step", "sanitize") in keys
    assert ("step", "judge") in keys
    assert ("tool_call", None) in keys
    assert ("tool_result", None) in keys
    assert ("step", "mask") in keys
    assert ("final", None) in keys
    final = events[-1]
    assert final["blocked"] is False
    assert final["response"] == "Your order is SHIPPED."
    tool_results = [event for event in events if event["type"] == "tool_result"]
    assert "bob.smith" not in json.dumps(tool_results)


async def test_cli_validate_input_is_what_runner_receives(monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect

    import src.api.cli as cli

    settings = cli.resolve_service_settings()

    async def fake_a2a(query: str, host: str, port: int, stream: bool = False) -> str:
        if port == settings.mask_port:
            return "Hello Alice Jones"
        return query

    monkeypatch.setattr(cli, "call_a2a_agent", fake_a2a)
    raw = "Status of order #5?"
    clean = await cli.validate_input(raw)
    assert clean == "Status of order 5?"
    seen: dict[str, str] = {}

    class Runner:
        def run(self, **kwargs):
            seen["text"] = kwargs["new_message"].parts[0].text
            event = SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(text="Hello Alice Jones")]),
                usage_metadata=None,
            )
            event.get_function_calls = lambda: []
            event.get_function_responses = lambda: []
            event.is_final_response = lambda: True
            return [event]

    reply = await cli.run_turn(Runner(), ALICE, raw, [])
    assert seen["text"] == clean
    assert reply == "Hello Alice Jones"
    assert ".lower()" not in inspect.getsource(cli._mask_response)


async def test_cli_blocked_input_does_not_reach_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cli as cli

    async def fake_a2a(query: str, host: str, port: int, stream: bool = False) -> str:
        return "BLOCKED: injection"

    monkeypatch.setattr(cli, "call_a2a_agent", fake_a2a)
    called: list = []

    class Runner:
        def run(self, **kwargs):
            called.append(kwargs)
            return []

    assert await cli.validate_input("Where is order 5?") is None
    assert await cli.run_turn(Runner(), ALICE, "Where is order 5?", []) is None
    assert called == []
