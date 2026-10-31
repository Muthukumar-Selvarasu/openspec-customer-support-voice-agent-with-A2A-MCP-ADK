"""Unit tests for auth, memory, prompt contract, and optional tracing."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from src.core import memory as memory_mod
from src.core import telemetry as telemetry_mod
from src.core.greet import (
    DEFAULT_PGDATABASE,
    DEFAULT_PGHOST,
    DEFAULT_PGPASSWORD,
    DEFAULT_PGPORT,
    DEFAULT_PGUSER,
    authenticate_user,
    get_user_actions,
    greet_user,
    resolve_postgres_dsn,
)

PG_ENV_KEYS = (
    "DATABASE_URL",
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
)


def _clear_pg_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in PG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_greet_prefers_database_url_over_pg_and_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pg_env(monkeypatch)
    neon = "postgresql://neondb_owner:secret@ep-example.us-east-1.aws.neon.tech/neondb?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", neon)
    monkeypatch.setenv("PGHOST", DEFAULT_PGHOST)
    monkeypatch.setenv("PGUSER", "stray_user")
    dsn = resolve_postgres_dsn()
    assert dsn == neon
    host = urlparse(dsn).hostname
    assert host == "ep-example.us-east-1.aws.neon.tech"
    assert host != DEFAULT_PGHOST


def test_greet_uses_pg_env_when_database_url_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pg_env(monkeypatch)
    monkeypatch.setenv("PGHOST", "db.internal")
    monkeypatch.setenv("PGPORT", "6543")
    monkeypatch.setenv("PGDATABASE", "shoppers")
    monkeypatch.setenv("PGUSER", "app_user")
    monkeypatch.setenv("PGPASSWORD", "app_secret")
    dsn = resolve_postgres_dsn()
    parsed = urlparse(dsn)
    assert parsed.hostname == "db.internal"
    assert parsed.port == 6543
    assert parsed.path == "/shoppers"
    assert parsed.username == "app_user"
    assert parsed.password == "app_secret"


def test_greet_falls_back_to_local_podman_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pg_env(monkeypatch)
    dsn = resolve_postgres_dsn()
    parsed = urlparse(dsn)
    assert parsed.hostname == DEFAULT_PGHOST
    assert parsed.port == int(DEFAULT_PGPORT)
    assert parsed.path == f"/{DEFAULT_PGDATABASE}"
    assert parsed.username == DEFAULT_PGUSER
    assert parsed.password == DEFAULT_PGPASSWORD


def _postgres_ready() -> bool:
    try:
        import psycopg2

        conn = psycopg2.connect(resolve_postgres_dsn())
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _postgres_ready(), reason="local Podman Postgres is not reachable")
def test_greet_authenticate_unknown_credentials_fail_closed() -> None:
    assert authenticate_user("nobody@example.com", "wrong") is None
    assert authenticate_user("hannah.m@school.edu", "not-hannah") is None


@pytest.mark.skipif(not _postgres_ready(), reason="local Podman Postgres is not reachable")
def test_greet_premium_shopper_is_recognized() -> None:
    user = authenticate_user("hannah.m@school.edu", "hannah")
    assert user is not None
    assert user["is_premium_customer"] is True
    assert user["full_name"] == "Hannah M"
    greeting = greet_user(user["user_id"])
    assert "Hannah M" in greeting
    assert "premium" in greeting.lower()
    assert "94" in greeting


@pytest.mark.skipif(not _postgres_ready(), reason="local Podman Postgres is not reachable")
def test_greet_get_user_actions_returns_list() -> None:
    actions = get_user_actions("hannah.m@school.edu")
    assert isinstance(actions, list)


def test_memory_imports_without_mem0_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEM0_API_KEY", raising=False)
    memory_mod._client = None
    import importlib

    reloaded = importlib.reload(memory_mod)
    assert reloaded.search_memory is not None
    assert reloaded._client is None


def test_memory_search_filters_by_session_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.search.return_value = {
        "results": [{"memory": "prefers morning delivery"}],
    }
    monkeypatch.setattr(memory_mod, "_get_client", lambda: client)
    result = memory_mod.search_memory("delivery preference", "shopper-42")
    client.search.assert_called_once_with(
        "delivery preference",
        filters={"user_id": "shopper-42"},
    )
    assert result["status"] == "success"
    assert "prefers morning delivery" in result["memories"]


def test_memory_search_does_not_take_a_second_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.search.return_value = {"results": []}
    monkeypatch.setattr(memory_mod, "_get_client", lambda: client)
    memory_mod.search_memory("orders", user_id="alice.jones@example.com")
    _args, kwargs = client.search.call_args
    assert kwargs["filters"] == {"user_id": "alice.jones@example.com"}
    assert "alice.jones@example.com" in str(kwargs["filters"])
    assert memory_mod.search_memory.__code__.co_varnames[:2] == ("query", "user_id")


def test_memory_save_scopes_add_to_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.add.return_value = {"id": "mem-1"}
    monkeypatch.setattr(memory_mod, "_get_client", lambda: client)
    messages = [{"role": "user", "content": "I want order 4 cancelled"}]
    result = memory_mod.save_memory(messages, "shopper-42")
    client.add.assert_called_once_with(messages, user_id="shopper-42")
    assert result["status"] == "success"


def test_memory_save_returns_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.add.side_effect = RuntimeError("quota")
    monkeypatch.setattr(memory_mod, "_get_client", lambda: client)
    result = memory_mod.save_memory([], "shopper-42")
    assert result["status"] == "error"
    assert "quota" in result["message"]


def test_prompt_matches_tools_yaml_parameter_names() -> None:
    from src.core.prompts import SQL_PROMPT_INSTRUCTION

    text = SQL_PROMPT_INSTRUCTION.format(USER_ID="hannah.m@school.edu")
    assert "hannah.m@school.edu" in text
    assert "parameters" in text
    assert "parameters_json" not in text
    assert "action-log" in text
    assert "update-order-status" in text
    assert "MUST NEVER" in text or "never call" in text.lower()
    assert "customer_email" in text
    assert "authenticated shopper" in text
    assert "confirm" in text.lower()
    assert "read tools first" in text.lower() or "use read tools first" in text.lower()


def test_telemetry_false_is_noop_and_does_not_import_phoenix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEMETRY", "false")
    telemetry_mod.reset_telemetry_state()
    sys_modules_before = set(sys.modules)
    tracer = telemetry_mod.get_tracer()
    assert isinstance(tracer, telemetry_mod._NoopTracer)
    with tracer.start_as_current_span("turn") as span:
        span.set_attribute("input.value", "hello")
        span.record_exception(RuntimeError("ignored"))
        span.set_status("ok")
    imported = set(sys.modules) - sys_modules_before
    assert not any(name == "phoenix" or name.startswith("phoenix.") for name in imported)


def test_telemetry_unset_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    telemetry_mod.reset_telemetry_state()
    tracer = telemetry_mod.get_tracer()
    assert isinstance(tracer, telemetry_mod._NoopTracer)
    with tracer.start_as_current_span("turn"):
        pass


def test_telemetry_resolves_phoenix_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHOENIX_URL", raising=False)
    monkeypatch.delenv("PHOENIX_PUBLIC_URL", raising=False)
    assert telemetry_mod.resolve_phoenix_urls() == (
        "http://localhost:6006",
        "http://localhost:6006",
    )
    monkeypatch.setenv("PHOENIX_URL", "http://phoenix.internal:6006/")
    monkeypatch.setenv("PHOENIX_PUBLIC_URL", "https://phoenix.example.com")
    assert telemetry_mod.resolve_phoenix_urls() == (
        "http://phoenix.internal:6006",
        "https://phoenix.example.com",
    )


def test_telemetry_skips_browser_open_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEMETRY", "true")
    monkeypatch.setenv("PHOENIX_OPEN_BROWSER", "false")
    monkeypatch.setenv("PHOENIX_URL", "http://phoenix.internal:6006")
    monkeypatch.setenv("PHOENIX_PUBLIC_URL", "http://phoenix.public:6006")
    telemetry_mod.reset_telemetry_state()

    opened: list[str] = []
    fake_px = MagicMock()
    fake_trace = MagicMock()
    fake_trace.get_tracer.return_value = object()

    monkeypatch.setitem(sys.modules, "phoenix", fake_px)
    monkeypatch.setitem(sys.modules, "webbrowser", MagicMock(open=opened.append))
    monkeypatch.setitem(sys.modules, "opentelemetry", MagicMock(trace=fake_trace))
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", fake_trace)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.trace",
        MagicMock(TracerProvider=MagicMock()),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.trace.export",
        MagicMock(BatchSpanProcessor=MagicMock()),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        MagicMock(OTLPSpanExporter=MagicMock()),
    )
    monkeypatch.setitem(
        sys.modules,
        "openinference.instrumentation.google_genai",
        MagicMock(GoogleGenAIInstrumentor=MagicMock()),
    )

    tracer = telemetry_mod.get_tracer()
    assert tracer is fake_trace.get_tracer.return_value
    fake_px.launch_app.assert_called_once()
    assert opened == []
