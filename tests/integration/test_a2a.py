"""Bind-address checks for the Judge and Masker A2A servers.

These tests mount ``A2AServer.app`` in-process and never open ports 10002 or 10003.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.a2a.factories import create_judge_server, create_mask_server
from src.a2a.run_servers import bind_addresses, resolve_server_binds

_RUN_SERVERS = (
    Path(__file__).resolve().parents[2] / "src" / "a2a" / "run_servers.py"
).read_text(encoding="utf-8")

_BIND_ENV = (
    "A2A_JUDGE_HOST",
    "A2A_JUDGE_PORT",
    "A2A_MASK_HOST",
    "A2A_MASK_PORT",
)


async def _echo(text: str) -> str:
    return text


def _clear_bind_env(monkeypatch) -> None:
    for name in _BIND_ENV:
        monkeypatch.delenv(name, raising=False)


def test_bind_defaults_when_a2a_env_unset(monkeypatch) -> None:
    _clear_bind_env(monkeypatch)
    assert bind_addresses() == ("localhost", 10002, "localhost", 10003)


def test_bind_blank_env_uses_cascade_defaults(monkeypatch) -> None:
    for name in _BIND_ENV:
        monkeypatch.setenv(name, "  ")
    assert bind_addresses() == ("localhost", 10002, "localhost", 10003)


def test_bind_addresses_follow_a2a_env(monkeypatch) -> None:
    monkeypatch.setenv("A2A_JUDGE_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_JUDGE_PORT", "18002")
    monkeypatch.setenv("A2A_MASK_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_MASK_PORT", "18003")
    assert bind_addresses() == ("0.0.0.0", 18002, "0.0.0.0", 18003)


def test_bind_explicit_overrides_win_over_env(monkeypatch) -> None:
    monkeypatch.setenv("A2A_JUDGE_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_JUDGE_PORT", "18002")
    monkeypatch.setenv("A2A_MASK_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_MASK_PORT", "18003")
    assert resolve_server_binds(
        judge_host="127.0.0.1",
        judge_port=19002,
        mask_host="127.0.0.1",
        mask_port=19003,
    ) == ("127.0.0.1", 19002, "127.0.0.1", 19003)


def test_bind_servers_store_env_host_and_port(monkeypatch) -> None:
    monkeypatch.setenv("A2A_JUDGE_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_JUDGE_PORT", "18002")
    monkeypatch.setenv("A2A_MASK_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_MASK_PORT", "18003")
    judge_host, judge_port, mask_host, mask_port = resolve_server_binds()
    judge = create_judge_server(host=judge_host, port=judge_port, call_judge_agent=_echo)
    mask = create_mask_server(host=mask_host, port=mask_port, call_mask_agent=_echo)
    assert (judge.host, judge.port) == ("0.0.0.0", 18002)
    assert (mask.host, mask.port) == ("0.0.0.0", 18003)
    assert judge.agent_card.url == "http://0.0.0.0:18002/"
    assert mask.agent_card.url == "http://0.0.0.0:18003/"
    assert judge.agent_card.name == "security-judge"


def test_run_servers_reads_bind_env_names() -> None:
    for name in _BIND_ENV:
        assert name in _RUN_SERVERS
    assert "def main" in _RUN_SERVERS
    assert "start_all_servers()" in _RUN_SERVERS
    assert "resolve_server_binds" in _RUN_SERVERS


_MASK_AGENT_SOURCE = (
    Path(__file__).resolve().parents[2] / "src" / "agents" / "mask_agent.py"
).read_text(encoding="utf-8")


def test_mask_agent_source_calls_local_masker() -> None:
    assert "mask_sensitive_data(text)" in _MASK_AGENT_SOURCE
    lowered = _MASK_AGENT_SOURCE.lower()
    assert "google.cloud" not in lowered
    assert "dlp" not in lowered
    assert "secretmanager" not in lowered
    assert "modelarmor" not in lowered
    assert "model_armor" not in lowered


async def test_mask_agent_delegates_to_mask_sensitive_data(monkeypatch) -> None:
    from src.agents.mask_agent import call_mask_agent, mask_text

    seen: list[str] = []

    def fake(text: str) -> str:
        seen.append(text)
        return "redacted"

    monkeypatch.setattr("src.agents.mask_agent.mask_sensitive_data", fake)
    assert await call_mask_agent("alice@example.com") == "redacted"
    assert mask_text("alice@example.com") == {"masked_text": "redacted"}
    assert seen == ["alice@example.com", "alice@example.com"]


async def test_mask_agent_redacts_email_locally() -> None:
    from src.agents.mask_agent import call_mask_agent

    masked = await call_mask_agent("Reach me at alice@example.com please")
    assert "alice@example.com" not in masked
    assert masked.startswith("Reach me at ")
    assert masked.endswith(" please")
    assert "*" in masked


def test_mask_pipeline_orders_judge_before_masker() -> None:
    from src.agents.pipeline import security_pipeline

    assert [agent.name for agent in security_pipeline.sub_agents] == [
        "security_judge",
        "data_masker",
    ]


def test_mask_rpc_send_redacts_email() -> None:
    from fastapi.testclient import TestClient

    from src.agents.mask_agent import call_mask_agent

    server = create_mask_server(call_mask_agent=call_mask_agent)
    client = TestClient(server.app)
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tasks/send",
            "params": {
                "id": "task-mask-email",
                "sessionId": "session-mask",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "email alice@example.com"}],
                },
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert "error" not in body
    text = body["result"]["artifacts"][0]["parts"][0]["text"]
    assert "alice@example.com" not in text
    assert "email " in text
    assert "*" in text
    assert body["result"]["id"] == "task-mask-email"


def _rpc(method: str, params: dict, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _user_message(text: str, task_id: str) -> dict:
    return {
        "id": task_id,
        "sessionId": f"session-{task_id}",
        "message": {"role": "user", "parts": [{"type": "text", "text": text}]},
    }


async def _stub_judge(query: str) -> str:
    return f"JUDGE:{query}"


async def _stub_mask(text: str) -> str:
    return f"MASK:{text}"


async def _failing_agent(text: str) -> str:
    raise RuntimeError(f"task failed for {text}")


def _patch_agents(monkeypatch) -> None:
    import src.agents.judge_agent as judge_mod
    import src.agents.mask_agent as mask_mod

    monkeypatch.setattr(judge_mod, "call_judge_agent", _stub_judge)
    monkeypatch.setattr(mask_mod, "call_mask_agent", _stub_mask)


def test_discovery_cards_identify_judge_and_masker(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _patch_agents(monkeypatch)
    import src.agents.judge_agent as judge_mod
    import src.agents.mask_agent as mask_mod

    judge = TestClient(
        create_judge_server(call_judge_agent=judge_mod.call_judge_agent).app
    )
    mask = TestClient(
        create_mask_server(call_mask_agent=mask_mod.call_mask_agent).app
    )
    judge_card = judge.get("/.well-known/agent.json")
    mask_card = mask.get("/.well-known/agent.json")
    assert judge_card.status_code == 200
    assert mask_card.status_code == 200
    judge_body = judge_card.json()
    mask_body = mask_card.json()
    assert judge_body["name"] == "security-judge"
    assert judge_body["url"].endswith("/")
    assert judge_body["skills"][0]["id"] == "security-judge"
    assert mask_body["name"] == "data-masker"
    assert mask_body["url"].endswith("/")
    assert mask_body["skills"]


def test_tasks_send_get_and_cancel_round_trip(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _patch_agents(monkeypatch)
    import src.agents.judge_agent as judge_mod

    client = TestClient(
        create_judge_server(call_judge_agent=judge_mod.call_judge_agent).app
    )
    sent = client.post(
        "/rpc",
        json=_rpc("tasks/send", _user_message("where is order 3?", "task-send")),
    )
    assert sent.status_code == 200
    sent_body = sent.json()
    assert sent_body["jsonrpc"] == "2.0"
    assert sent_body["id"] == 1
    assert sent_body["result"]["id"] == "task-send"
    assert sent_body["result"]["status"]["state"] == "completed"
    assert (
        sent_body["result"]["artifacts"][0]["parts"][0]["text"]
        == "JUDGE:where is order 3?"
    )

    fetched = client.post(
        "/rpc",
        json=_rpc("tasks/get", {"id": "task-send", "historyLength": 10}),
    )
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["result"]["id"] == "task-send"
    assert (
        fetched_body["result"]["artifacts"][0]["parts"][0]["text"]
        == "JUDGE:where is order 3?"
    )

    canceled = client.post("/rpc", json=_rpc("tasks/cancel", {"id": "task-send"}))
    assert canceled.status_code == 200
    assert canceled.json()["result"]["status"]["state"] == "canceled"


def test_unknown_method_returns_32601(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _patch_agents(monkeypatch)
    import src.agents.judge_agent as judge_mod

    client = TestClient(
        create_judge_server(call_judge_agent=judge_mod.call_judge_agent).app
    )
    response = client.post("/rpc", json=_rpc("tasks/unknown", {"id": "missing"}))
    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == -32601


def test_task_error_returns_32000(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _patch_agents(monkeypatch)
    import src.agents.judge_agent as judge_mod
    import src.agents.mask_agent as mask_mod

    judge = TestClient(
        create_judge_server(call_judge_agent=judge_mod.call_judge_agent).app
    )
    missing = judge.post("/rpc", json=_rpc("tasks/get", {"id": "does-not-exist"}))
    assert missing.json()["error"]["code"] == -32000
    missing_cancel = judge.post(
        "/rpc", json=_rpc("tasks/cancel", {"id": "does-not-exist"})
    )
    assert missing_cancel.json()["error"]["code"] == -32000

    monkeypatch.setattr(mask_mod, "call_mask_agent", _failing_agent)
    mask = TestClient(create_mask_server(call_mask_agent=mask_mod.call_mask_agent).app)
    failed = mask.post(
        "/rpc",
        json=_rpc("tasks/send", _user_message("alice@example.com", "task-fail")),
    )
    assert failed.json()["error"]["code"] == -32000
    assert "error" in failed.json()
    assert "result" not in failed.json()


async def test_tasks_send_subscribe_streams_stubbed_output(monkeypatch) -> None:
    import json

    import httpx

    _patch_agents(monkeypatch)
    import src.agents.mask_agent as mask_mod

    server = create_mask_server(call_mask_agent=mask_mod.call_mask_agent)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://masker") as client:
        response = await client.post(
            "/rpc",
            json=_rpc(
                "tasks/sendSubscribe",
                _user_message("order 4", "task-stream"),
            ),
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert len(events) >= 2
    artifact_text = ""
    final_state = ""
    for event in events:
        assert event["jsonrpc"] == "2.0"
        result = event["result"]
        if "artifact" in result:
            artifact_text = result["artifact"]["parts"][0]["text"]
        if result.get("final") is True:
            final_state = result["status"]["state"]
    assert artifact_text == "MASK:order 4"
    assert final_state == "completed"

    fetched = await _get_task_async(server, "task-stream")
    assert fetched["result"]["artifacts"][0]["parts"][0]["text"] == "MASK:order 4"


async def _get_task_async(server, task_id: str) -> dict:
    import httpx

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://masker") as client:
        response = await client.post("/rpc", json=_rpc("tasks/get", {"id": task_id}))
    assert response.status_code == 200
    return response.json()


@pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY is not set",
)
async def test_live_judge_gemini() -> None:
    from src.agents.judge_agent import call_judge_agent

    result = await call_judge_agent("Where is order 3?")
    assert isinstance(result, str)
    assert result.strip()
