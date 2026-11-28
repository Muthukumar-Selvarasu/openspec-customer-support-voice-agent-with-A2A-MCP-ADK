"""Shopper FastAPI app: chat, inspector pages, and the voice WebSocket mount.

``src/api/web.py`` is two levels under the repo root. Static pages live in
``src/static``. The MCP Toolbox client is created on first use so importing
``app`` does not need a running Toolbox process.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.a2a.client import call_a2a_agent
from src.core.greet import authenticate_user
from src.core.memory import make_memory_search_tool, save_memory, search_memory
from src.core.prompts import SQL_PROMPT_INSTRUCTION
from src.core.telemetry import ATTR, get_tracer, telemetry_enabled
from src.security.blocker import OFF_TOPIC_REDIRECT, evaluate_prompt, parse_judge_verdict
from src.security.masker import mask_sensitive_data
from src.security.sanitizer import sanitize_input
from src.voice.router import make_voice_router, print_config_warnings

AGENT_MODEL = "gemini-3.8-flash"
APP_NAME = "agents"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC = Path(__file__).resolve().parents[1] / "static"
_TOOLS_YAML = _REPO_ROOT / "mcp_toolbox" / "tools.yaml"

load_dotenv(_REPO_ROOT / ".env")
os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)

DEFAULT_TOOLBOX_URL = "http://127.0.0.1:5000"
DEFAULT_JUDGE_HOST = "localhost"
DEFAULT_JUDGE_PORT = 10002
DEFAULT_MASK_HOST = "localhost"
DEFAULT_MASK_PORT = 10003
DEFAULT_PHOENIX_URL = "http://localhost:6006"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

_IDENTITY_ARG_NAMES = ("user_id", "email", "customer_email", "user_email")
_TOOL_IDENTITY_ARG: dict[str, str] = {
    "get-order-status": "customer_email",
    "find-customer-orders": "email",
    "action-log": "user_email",
    "search_memory": "user_id",
}
_ALLOWED_ACTION_TYPES = frozenset(
    {
        "UPDATE_ORDER_STATUS",
        "RETURN_ITEM",
        "UPDATE_DELIVERY_ADDRESS",
        "UPDATE_PROFILE_DETAILS",
        "CANCEL_ORDER",
        "RETURN_ORDER",
        "UPDATE_ADDRESS",
        "UPDATE_PROFILE",
    }
)
_BLOCKED_TOOL = "update-order-status"


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_port(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


@dataclass(frozen=True)
class ServiceSettings:
    toolbox_url: str
    judge_host: str
    judge_port: int
    mask_host: str
    mask_port: int
    phoenix_url: str
    phoenix_public_url: str
    host: str
    port: int


def resolve_service_settings() -> ServiceSettings:
    """Read service URLs from the environment. Blank values use localhost defaults.

    ``WEB_PORT`` is an alias of ``PORT`` and is used only when ``PORT`` is unset.
    """
    phoenix_url = _env_text("PHOENIX_URL", DEFAULT_PHOENIX_URL).rstrip("/")
    public = _env_text("PHOENIX_PUBLIC_URL", phoenix_url).rstrip("/")
    port_raw = os.getenv("PORT")
    if port_raw is None or not port_raw.strip():
        port_raw = os.getenv("WEB_PORT", str(DEFAULT_PORT))
    return ServiceSettings(
        toolbox_url=_env_text("TOOLBOX_URL", DEFAULT_TOOLBOX_URL),
        judge_host=_env_text("A2A_JUDGE_HOST", DEFAULT_JUDGE_HOST),
        judge_port=_env_port("A2A_JUDGE_PORT", DEFAULT_JUDGE_PORT),
        mask_host=_env_text("A2A_MASK_HOST", DEFAULT_MASK_HOST),
        mask_port=_env_port("A2A_MASK_PORT", DEFAULT_MASK_PORT),
        phoenix_url=phoenix_url,
        phoenix_public_url=public,
        host=_env_text("HOST", DEFAULT_HOST),
        port=int(str(port_raw).strip()),
    )


def mask_enabled() -> bool:
    return os.getenv("MASK", "true").strip().lower() in ("1", "true", "yes", "on")


def resolve_demo_mode(mode: str | None) -> str:
    """Missing or unrecognized values stay on the full cascade."""
    if isinstance(mode, str) and mode.strip().lower() == "quick":
        return "quick"
    return "explain"


_guardrails: dict[str, dict[str, bool]] = {}


def demo_pipeline_kwargs(
    mode: str | None,
    *,
    stream_endpoint: bool,
    judge: bool | None = None,
    mask: bool | None = None,
    user_id: str | None = None,
) -> dict[str, bool]:
    """Per-turn flags. Quick skips Judge and Masker by default unless overridden."""
    quick = resolve_demo_mode(mode) == "quick"
    saved = _guardrails.get(user_id or "") or {}
    if judge is None and "judge" in saved:
        judge = saved["judge"]
    if mask is None and "mask" in saved:
        mask = saved["mask"]
    do_judge = bool(judge) if judge is not None else (not quick)
    do_mask = (
        (bool(mask) and mask_enabled())
        if mask is not None
        else (False if quick else mask_enabled())
    )
    if quick and judge is None and mask is None:
        return {"judge": False, "mask": False, "stream": stream_endpoint}
    return {
        "judge": do_judge,
        "mask": do_mask,
        "stream": (not do_mask) if stream_endpoint else False,
    }


_toolbox_client = None
_database_tools = None


def get_database_tools():
    """Load the ``cs_agent_tools`` toolset. Connects to Toolbox on first call."""
    global _toolbox_client, _database_tools
    if _database_tools is None:
        from toolbox_core import ToolboxSyncClient

        settings = resolve_service_settings()
        _toolbox_client = ToolboxSyncClient(url=settings.toolbox_url)
        _database_tools = _toolbox_client.load_toolset("cs_agent_tools")
    return _database_tools


def _load_tool_catalogue() -> dict:
    """Describe MCP tools from ``mcp_toolbox/tools.yaml`` for the inspector UI."""
    try:
        cfg = yaml.safe_load(_TOOLS_YAML.read_text(encoding="utf-8"))
    except OSError:
        return {}
    tools = (cfg or {}).get("tools") or {}
    catalogue = {}
    for name, tool in tools.items():
        statement = str(tool.get("statement", "")).strip()
        access = "READ" if statement.upper().startswith("SELECT") else "WRITE"
        catalogue[name] = {
            "kind": "MCP",
            "access": access,
            "path": [
                "Gemini function call",
                "ADK",
                "toolbox-core",
                "MCP tools/call",
                "MCP Toolbox",
                "PostgreSQL",
            ],
            "runs": f"{tool.get('kind', 'tool')} on {tool.get('source', 'postgres')}",
            "statement": statement,
            "params": [param["name"] for param in tool.get("parameters", [])],
        }
    return catalogue


TOOLS = _load_tool_catalogue()
TOOLS["search_memory"] = {
    "kind": "Python fn",
    "access": "READ",
    "path": [
        "Gemini function call",
        "ADK",
        "search_memory()",
        "mem0.search()",
        "Mem0 cloud API",
    ],
    "runs": "src/core/memory.py — the agent decides when to recall",
}


def tool_info(name: str) -> dict:
    return TOOLS.get(name, {"kind": "tool"})


def _session_identity(tool_context) -> str:
    """Shopper email stored as the ADK session user id."""
    session = getattr(tool_context, "session", None)
    if session is not None and getattr(session, "user_id", None):
        return str(session.user_id)
    user_id = getattr(tool_context, "user_id", None)
    return str(user_id) if user_id else ""


def _enforce_tenant_tool_callback(tool, args, tool_context):
    """Force tool identity args to the logged-in shopper and block direct writes.

    Returning a dict skips the tool call. Returning ``None`` lets ADK invoke
    the tool with the mutated ``args``.
    """
    name = getattr(tool, "name", "") or ""
    if name == _BLOCKED_TOOL:
        return {
            "error": (
                "update-order-status is blocked. Record the intended change "
                "with action-log after the shopper confirms."
            )
        }
    identity = _session_identity(tool_context).strip()
    if not identity:
        return {"error": "Missing authenticated session identity."}

    required_key = _TOOL_IDENTITY_ARG.get(name)
    if required_key:
        args[required_key] = identity
    for key in _IDENTITY_ARG_NAMES:
        if key in args:
            args[key] = identity

    if name == "action-log":
        raw_action = args.get("action_type")
        action_type = str(raw_action).strip().upper() if raw_action is not None else ""
        if action_type not in _ALLOWED_ACTION_TYPES:
            return {
                "error": (
                    f"Unsupported action_type '{raw_action}'. Allowed types: "
                    f"{', '.join(sorted(_ALLOWED_ACTION_TYPES))}."
                )
            }
        args["action_type"] = action_type
        raw_params = args.get("parameters")
        if isinstance(raw_params, str):
            try:
                parsed = json.loads(raw_params)
            except ValueError:
                return {"error": "action-log parameters must be a valid JSON object."}
            if not isinstance(parsed, dict):
                return {"error": "action-log parameters must be a JSON object."}
        elif not isinstance(raw_params, dict):
            return {"error": "action-log parameters must be a valid JSON object."}
    return None


session_service = InMemorySessionService()
_runners: dict[str, Runner] = {}
_transcripts: dict[str, list] = {}
PAGE_LEAVE_GRACE_MS = 3000
_active_epoch: dict[str, str] = {}
_leave_tasks: dict[str, asyncio.Task] = {}


def _cancel_scheduled_flush(user_id: str) -> None:
    task = _leave_tasks.pop(user_id, None)
    if task is not None and not task.done():
        task.cancel()


def _seal_epoch(user_id: str) -> None:
    """Drop a pending leave and ignore an older epoch until a new one is adopted."""
    _cancel_scheduled_flush(user_id)
    _active_epoch[user_id] = f"sealed-{time.time_ns()}"


async def _flush_shopper(user_id: str) -> None:
    _runners.pop(user_id, None)
    _guardrails.pop(user_id, None)
    messages = _transcripts.pop(user_id, None)
    if messages:
        try:
            save_memory(messages, user_id)
        except Exception:
            pass
    try:
        await session_service.delete_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=f"session_{user_id}",
        )
    except Exception:
        pass


async def _flush_after_leave(user_id: str, epoch: str) -> None:
    try:
        await asyncio.sleep(PAGE_LEAVE_GRACE_MS / 1000)
    except asyncio.CancelledError:
        return
    if _active_epoch.get(user_id) != epoch:
        if _leave_tasks.get(user_id) is asyncio.current_task():
            _leave_tasks.pop(user_id, None)
        return
    _active_epoch.pop(user_id, None)
    if _leave_tasks.get(user_id) is asyncio.current_task():
        _leave_tasks.pop(user_id, None)
    await _flush_shopper(user_id)


def _build_runner(user_id: str) -> Runner:
    agent = LlmAgent(
        model=AGENT_MODEL,
        name="customer_support_assistant",
        description="Customer support agent for order questions and requests.",
        instruction=SQL_PROMPT_INSTRUCTION.format(USER_ID=user_id),
        tools=[*get_database_tools(), make_memory_search_tool(user_id)],
        before_tool_callback=_enforce_tenant_tool_callback,
        generate_content_config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )
    return Runner(agent=agent, app_name=APP_NAME, session_service=session_service)


def _record(user_id: str, role: str, content: str) -> None:
    if user_id and content:
        _transcripts.setdefault(user_id, []).append({"role": role, "content": content})


app = FastAPI(title="Customer Support Agent")


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _decode(value):
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _unwrap(resp):
    if isinstance(resp, dict) and set(resp) == {"result"}:
        resp = resp["result"]
    if isinstance(resp, str):
        try:
            return json.loads(resp)
        except ValueError:
            return resp
    return resp


def _step(key, title, ok, detail, span, t0, **extra):
    return {
        "type": "step",
        "key": key,
        "title": title,
        "status": "passed" if ok else "blocked",
        "detail": detail,
        "span": span,
        "ms": _ms(t0),
        **extra,
    }


async def _judge(text: str) -> tuple[bool, str]:
    settings = resolve_service_settings()
    raw = await call_a2a_agent(
        query=text, host=settings.judge_host, port=settings.judge_port
    )
    decision = parse_judge_verdict(raw)
    return decision == "ALLOW", decision


async def _mask(text: str) -> tuple[str, str]:
    settings = resolve_service_settings()
    try:
        masked = await call_a2a_agent(
            query=text, host=settings.mask_host, port=settings.mask_port
        )
    except Exception as exc:
        local_masked = mask_sensitive_data(text)
        return local_masked, f"Masker unreachable; applied local regex fallback ({exc})"
    out = masked or mask_sensitive_data(text)
    note = (
        "no PII found, response unchanged"
        if out.strip() == text.strip()
        else "PII masked in the response"
    )
    return out, note


_phoenix_project: str | None = None
_phoenix_failed_until: float = 0.0
_PHOENIX_FAIL_COOLDOWN_SEC = 30.0


def _fetch_phoenix_project_id(phoenix_url: str) -> str | None:
    global _phoenix_project, _phoenix_failed_until
    if _phoenix_project is not None:
        return _phoenix_project
    if time.monotonic() < _phoenix_failed_until:
        return None
    headers: dict[str, str] = {}
    api_key = os.getenv("PHOENIX_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{phoenix_url}/v1/projects", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            projects = json.load(response)["data"]
        _phoenix_project = next(item["id"] for item in projects if item["name"] == "default")
        return _phoenix_project
    except Exception:
        _phoenix_failed_until = time.monotonic() + _PHOENIX_FAIL_COOLDOWN_SEC
        return None


def trace_url(span) -> dict | None:
    """Phoenix deep link for a real span. None when telemetry is off."""
    if not telemetry_enabled() or not hasattr(span, "get_span_context"):
        return None
    settings = resolve_service_settings()
    trace_id = format(span.get_span_context().trace_id, "032x")
    public = settings.phoenix_public_url
    project_id = _fetch_phoenix_project_id(settings.phoenix_url)
    if project_id is None:
        return {"trace_id": trace_id, "url": f"{public}/projects"}
    return {
        "trace_id": trace_id,
        "url": f"{public}/projects/{project_id}/traces/{trace_id}",
    }


async def resolve_trace_url(span) -> dict | None:
    """Async Phoenix deep-link lookup that never blocks the asyncio event loop."""
    if not telemetry_enabled() or not hasattr(span, "get_span_context"):
        return None
    settings = resolve_service_settings()
    trace_id = format(span.get_span_context().trace_id, "032x")
    public = settings.phoenix_public_url
    if _phoenix_project is not None:
        return {
            "trace_id": trace_id,
            "url": f"{public}/projects/{_phoenix_project}/traces/{trace_id}",
        }
    if time.monotonic() < _phoenix_failed_until:
        return {"trace_id": trace_id, "url": f"{public}/projects"}
    project_id = await asyncio.to_thread(_fetch_phoenix_project_id, settings.phoenix_url)
    if project_id is None:
        return {"trace_id": trace_id, "url": f"{public}/projects"}
    return {
        "trace_id": trace_id,
        "url": f"{public}/projects/{project_id}/traces/{trace_id}",
    }


async def text_pipeline(
    runner,
    user_id: str,
    text: str,
    *,
    stream: bool = False,
    turn_span=None,
    mask: bool | None = None,
    judge: bool = True,
    judge_if_flagged: bool = False,
):
    """Run one turn and yield inspector events for chat and voice."""
    do_mask = mask_enabled() if mask is None else mask
    tracer = get_tracer()
    settings = resolve_service_settings()

    def blocked(stage, msg, *, reason: str | None = None):
        if turn_span is not None:
            turn_span.set_attribute("turn.blocked", True)
            turn_span.set_attribute("turn.block_reason", reason or stage)
            turn_span.set_attribute(ATTR.OUTPUT_VALUE, f"BLOCKED: {reason or stage}")
        payload = {"type": "final", "blocked": True, "stage": stage, "response": msg}
        if reason is not None:
            payload["reason"] = reason
        return payload

    yield {"type": "stage", "key": "sanitize", "stage": "Sanitizing input"}
    t0 = time.perf_counter()
    with tracer.start_as_current_span("security.sanitize") as span:
        span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
        span.set_attribute(ATTR.INPUT_VALUE, text[:500])
        try:
            clean = sanitize_input(text)
            span.set_attribute(ATTR.OUTPUT_VALUE, "passed")
            reason = "length and character checks passed, no blocked patterns"
        except ValueError as exc:
            reason = str(exc)
            span.set_attribute(ATTR.OUTPUT_VALUE, f"blocked: {reason}")
            clean = None
    yield _step(
        "sanitize",
        "Sanitizer",
        clean is not None,
        reason,
        "security.sanitize",
        t0,
        kind="in-process",
        runs="length and character whitelist in src/security/sanitizer.py",
        **({"clean_text": clean} if clean is not None else {}),
    )
    if clean is None:
        yield blocked("sanitizer", f"Input rejected by sanitizer: {reason}")
        return

    t0_blocker = time.perf_counter()
    flagged_by_blocker = (
        evaluate_prompt(text) == "BLOCKED" or evaluate_prompt(clean) == "BLOCKED"
    )
    run_judge = judge
    if run_judge and judge_if_flagged:
        run_judge = flagged_by_blocker

    if flagged_by_blocker and not run_judge:
        with tracer.start_as_current_span("security.blocker") as span:
            span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
            span.set_attribute(ATTR.INPUT_VALUE, text[:500])
            span.set_attribute(ATTR.OUTPUT_VALUE, "blocked")
        yield _step(
            "blocker",
            "Security Blocker",
            False,
            "flagged by local SecurityBlocker",
            "security.blocker",
            t0_blocker,
            kind="in-process",
            runs="local regex blocker in src/security/blocker.py",
        )
        yield blocked(
            "sanitizer",
            "Blocked by the local SecurityBlocker (possible injection/unsafe input).",
        )
        return

    if run_judge:
        yield {"type": "stage", "key": "judge", "stage": "A2A Security Judge"}
        t0 = time.perf_counter()
        with tracer.start_as_current_span("security.a2a_judge") as span:
            span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
            span.set_attribute(ATTR.INPUT_VALUE, text[:500])
            try:
                ok, verdict = await _judge(text)
            except Exception as exc:
                span.set_attribute(ATTR.OUTPUT_VALUE, f"error: {exc}")
                yield {"type": "error", "error": f"Security Judge unreachable: {exc}"}
                return
            if flagged_by_blocker:
                ok = False
                verdict = "BLOCKED"
            is_off_topic = (
                (not ok)
                and (not flagged_by_blocker)
                and parse_judge_verdict(verdict) == "OFF_TOPIC"
            )
            if ok:
                span.set_attribute(ATTR.OUTPUT_VALUE, "passed")
            elif is_off_topic:
                span.set_attribute(ATTR.OUTPUT_VALUE, "off_topic")
            else:
                span.set_attribute(ATTR.OUTPUT_VALUE, "blocked")
        if ok:
            judged = "cleared: allowed by A2A Security Judge"
        elif is_off_topic:
            judged = "declined: outside customer-support scope (OFF_TOPIC)"
        else:
            judged = f"returned BLOCKED: {verdict.strip()[:200]}"
        step_extra = {"reason": "off_topic"} if is_off_topic else {}
        yield _step(
            "judge",
            "Security Judge",
            ok,
            judged,
            "security.a2a_judge",
            t0,
            kind="A2A",
            runs=f"ADK agent behind an A2A server at :{settings.judge_port}",
            text_chars=len(text),
            **step_extra,
        )
        if not ok:
            if is_off_topic:
                yield blocked("judge", OFF_TOPIC_REDIRECT, reason="off_topic")
            else:
                yield blocked(
                    "judge",
                    "Blocked by the A2A Security Judge (possible injection/unsafe input).",
                )
            return

    content = types.Content(role="user", parts=[types.Part(text=clean)])
    run_config = RunConfig(streaming_mode=StreamingMode.SSE) if stream else None
    yield {"type": "stage", "key": "agent", "stage": "Agent thinking"}
    final_text, display, call_id, t0 = "", "", 0, time.perf_counter()
    pending: dict[str, list] = {}
    seen_partial = False
    async for event in runner.run_async(
        user_id=user_id,
        session_id=f"session_{user_id}",
        new_message=content,
        run_config=run_config,
    ):
        partial = bool(getattr(event, "partial", False))
        calls = [] if partial else (event.get_function_calls() or [])
        if (
            not partial
            and event.author != "user"
            and event.content
            and (calls or event.is_final_response())
        ):
            usage = event.usage_metadata
            decided = (
                f"decided to call {', '.join(call.name for call in calls)}"
                if calls
                else "wrote the final answer"
            )
            yield {
                "type": "llm",
                "title": "Gemini",
                "detail": decided,
                "span": "call_llm",
                "model": AGENT_MODEL,
                "ms": _ms(t0),
                "tokens_in": getattr(usage, "prompt_token_count", None),
                "tokens_out": getattr(usage, "candidates_token_count", None),
            }
        for call in calls:
            call_id += 1
            args = {key: _decode(value) for key, value in (call.args or {}).items()}
            pending.setdefault(call.name, []).append((call_id, time.perf_counter(), args))
            yield {
                "type": "tool_call",
                "id": call_id,
                "name": call.name,
                "span": f"tool.{call.name}",
                "info": tool_info(call.name),
                "args": args,
            }
        for response in [] if partial else (event.get_function_responses() or []):
            queued = pending.get(response.name) or [(None, time.perf_counter(), {})]
            tool_id, started, args = queued.pop(0)
            result = _unwrap(response.response)
            with tracer.start_as_current_span(f"tool.{response.name}") as span:
                span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "TOOL")
                span.set_attribute(ATTR.TOOL_NAME, response.name)
                span.set_attribute(ATTR.INPUT_VALUE, json.dumps(args, default=str))
                span.set_attribute(ATTR.OUTPUT_VALUE, json.dumps(result, default=str)[:2000])
            yield {
                "type": "tool_result",
                "id": tool_id,
                "name": response.name,
                "ms": _ms(started),
                "result": result,
            }
            yield {"type": "stage", "key": "agent", "stage": "Agent thinking"}
            t0 = time.perf_counter()
        text_part = (
            event.content.parts[0].text if (event.content and event.content.parts) else None
        )
        if stream and text_part:
            if partial:
                seen_partial = True
            elif seen_partial:
                continue
            display += text_part
            yield {"type": "delta", "text": display}
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""
    if stream:
        final_text = display or final_text

    if do_mask and not stream:
        yield {"type": "stage", "key": "mask", "stage": "A2A Data Masker"}
        t0 = time.perf_counter()
        with tracer.start_as_current_span("security.a2a_mask") as span:
            span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
            span.set_attribute(ATTR.INPUT_VALUE, final_text[:500])
            masked, note = await _mask(final_text)
            span.set_attribute(ATTR.OUTPUT_VALUE, masked[:500])
        yield _step(
            "mask",
            "Data Masker",
            True,
            note,
            "security.a2a_mask",
            t0,
            kind="A2A",
            runs=f"local regex masker behind an A2A server at :{settings.mask_port}",
            in_chars=len(final_text),
            out_chars=len(masked),
        )
        final_text = masked

    if turn_span is not None and not (do_mask and stream):
        turn_span.set_attribute(ATTR.OUTPUT_VALUE, final_text)
    yield {"type": "final", "blocked": False, "response": final_text}


class LoginReq(BaseModel):
    email: str
    password: str


class ChatReq(BaseModel):
    user_id: str
    message: str
    mode: str | None = None
    judge: bool | None = None
    mask: bool | None = None


class GuardrailsReq(BaseModel):
    user_id: str
    judge: bool | None = None
    mask: bool | None = None


class LogoutReq(BaseModel):
    user_id: str
    epoch: str | None = None


def _turn_span(user_id: str, message: str, channel: str):
    tracer = get_tracer()
    turn = tracer.start_as_current_span("agent.turn")
    span = turn.__enter__()
    span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "CHAIN")
    span.set_attribute(ATTR.INPUT_VALUE, message)
    span.set_attribute("user.id", user_id)
    span.set_attribute("turn.channel", channel)
    return turn, span


@app.post("/api/login")
async def login(req: LoginReq):
    ctx = authenticate_user(email=req.email, password=req.password)
    if not ctx:
        return JSONResponse({"ok": False, "error": "Invalid email or password."}, status_code=401)
    uid = ctx["email"]
    _seal_epoch(uid)
    _guardrails.pop(uid, None)
    _runners[uid] = _build_runner(uid)
    _transcripts[uid] = []
    session_id = f"session_{uid}"
    try:
        await session_service.delete_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
    except Exception:
        pass
    await session_service.create_session(
        app_name=APP_NAME, user_id=uid, session_id=session_id
    )
    return {
        "ok": True,
        "user_id": uid,
        "full_name": ctx.get("full_name"),
        "is_premium": bool(ctx.get("is_premium_customer")),
        "items": ctx.get("total_items_purchased", 0),
        "model": AGENT_MODEL,
    }


@app.post("/api/session")
async def session(req: LogoutReq):
    """True when this browser reload still has the in-memory shopper runner."""
    _cancel_scheduled_flush(req.user_id)
    if req.epoch:
        _active_epoch[req.user_id] = req.epoch
    if req.user_id not in _runners:
        return JSONResponse({"ok": False, "error": "Not logged in."}, status_code=401)
    return {"ok": True, "user_id": req.user_id}


@app.post("/api/page-leave")
async def page_leave(req: LogoutReq):
    """Schedule the logout flush. A newer epoch can still cancel it."""
    epoch = req.epoch or ""
    if not epoch:
        return {"ok": True}
    current = _active_epoch.get(req.user_id)
    if current is not None and current != epoch:
        return {"ok": True}
    _active_epoch[req.user_id] = epoch
    _cancel_scheduled_flush(req.user_id)
    _leave_tasks[req.user_id] = asyncio.create_task(_flush_after_leave(req.user_id, epoch))
    return {"ok": True}


@app.post("/api/logout")
async def logout(req: LogoutReq):
    _seal_epoch(req.user_id)
    _guardrails.pop(req.user_id, None)
    await _flush_shopper(req.user_id)
    return {"ok": True}


@app.post("/api/guardrails")
async def set_guardrails(req: GuardrailsReq):
    entry = dict(_guardrails.get(req.user_id) or {})
    if "judge" in req.model_fields_set:
        if req.judge is None:
            entry.pop("judge", None)
        else:
            entry["judge"] = bool(req.judge)
    if "mask" in req.model_fields_set:
        if req.mask is None:
            entry.pop("mask", None)
        else:
            entry["mask"] = bool(req.mask)
    if entry:
        _guardrails[req.user_id] = entry
    else:
        _guardrails.pop(req.user_id, None)
    return {"ok": True, **entry}


@app.post("/api/chat")
async def chat(req: ChatReq):
    runner = _runners.get(req.user_id)
    if runner is None:
        return JSONResponse({"ok": False, "error": "Not logged in."}, status_code=401)
    turn, span = _turn_span(req.user_id, req.message, "text")
    tool_calls, out, clean_message = [], None, req.message
    try:
        async for event in text_pipeline(
            runner,
            req.user_id,
            req.message,
            turn_span=span,
            **demo_pipeline_kwargs(
                req.mode,
                stream_endpoint=False,
                judge=req.judge,
                mask=req.mask,
                user_id=req.user_id,
            ),
        ):
            if event["type"] == "step" and event.get("key") == "sanitize" and event.get("clean_text"):
                clean_message = event["clean_text"]
            elif event["type"] == "tool_call":
                tool_calls.append({"name": event["name"], "args": event["args"], "result": None})
            elif event["type"] == "tool_result":
                for call in reversed(tool_calls):
                    if call["name"] == event["name"] and call["result"] is None:
                        call["result"] = json.dumps(event["result"], default=str)[:800]
                        break
            elif event["type"] == "error":
                return JSONResponse({"ok": False, "error": event["error"]}, status_code=502)
            elif event["type"] == "final":
                out = event
    finally:
        turn.__exit__(None, None, None)
    if out["blocked"]:
        resp = {
            "ok": True,
            "blocked": True,
            "stage": out["stage"],
            "response": out["response"],
            "tool_calls": [],
        }
        if "reason" in out:
            resp["reason"] = out["reason"]
        return resp
    _record(req.user_id, "user", clean_message)
    _record(req.user_id, "assistant", out["response"])
    return {
        "ok": True,
        "blocked": False,
        "response": out["response"],
        "tool_calls": tool_calls,
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatReq):
    runner = _runners.get(req.user_id)
    if runner is None:
        return JSONResponse({"ok": False, "error": "Not logged in."}, status_code=401)

    async def generate():
        turn, span = _turn_span(req.user_id, req.message, "text-stream")
        clean_message = req.message
        try:
            linked = await resolve_trace_url(span)
            if linked:
                yield json.dumps({"type": "trace", "span": "agent.turn", **linked}) + "\n"
            async for event in text_pipeline(
                runner,
                req.user_id,
                req.message,
                turn_span=span,
                **demo_pipeline_kwargs(
                    req.mode,
                    stream_endpoint=True,
                    judge=req.judge,
                    mask=req.mask,
                    user_id=req.user_id,
                ),
            ):
                if event["type"] == "step" and event.get("key") == "sanitize" and event.get("clean_text"):
                    clean_message = event["clean_text"]
                yield json.dumps(event, default=str) + "\n"
                if event["type"] == "final" and not event["blocked"]:
                    _record(req.user_id, "user", clean_message)
                    _record(req.user_id, "assistant", event["response"])
        finally:
            turn.__exit__(None, None, None)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/")
def index():
    return FileResponse(
        _STATIC / "index.html",
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/theme.css")
def theme_css():
    return FileResponse(_STATIC / "theme.css", media_type="text/css")


@app.get("/architecture")
def architecture_page():
    page = (_STATIC / "architecture.html").read_text(encoding="utf-8")
    phoenix_public_url = html.escape(
        resolve_service_settings().phoenix_public_url, quote=True
    )
    page = page.replace(
        'href="http://localhost:6006"', f'href="{phoenix_public_url}"', 1
    )
    return HTMLResponse(content=page)


@app.get("/architecture.svg")
def architecture_svg():
    return FileResponse(_STATIC / "architecture.svg", media_type="image/svg+xml")


app.include_router(
    make_voice_router(
        runners=_runners,
        pipeline=text_pipeline,
        record=_record,
        trace_url=resolve_trace_url,
        mask_enabled=mask_enabled,
        mask_text=_mask,
    )
)


def main() -> None:
    import uvicorn

    settings = resolve_service_settings()
    print(
        f"Customer Support web UI -> http://{settings.host}:{settings.port}   "
        f"(architecture: http://{settings.host}:{settings.port}/architecture)"
    )
    print_config_warnings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
