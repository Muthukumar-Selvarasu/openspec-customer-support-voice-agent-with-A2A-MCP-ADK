"""Shopper FastAPI app: chat, inspector pages, and the voice WebSocket mount.

``src/api/web.py`` is two levels under the repo root. Static pages live in
``src/static``. The MCP Toolbox client is created on first use so importing
``app`` does not need a running Toolbox process.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.a2a.client import call_a2a_agent
from src.core.greet import authenticate_user
from src.core.memory import save_memory, search_memory
from src.core.prompts import SQL_PROMPT_INSTRUCTION
from src.core.telemetry import ATTR, get_tracer, telemetry_enabled
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


def demo_pipeline_kwargs(mode: str | None, *, stream_endpoint: bool) -> dict[str, bool]:
    """Per-turn flags. Quick skips Judge and Masker. Explain keeps the mask interlock."""
    if resolve_demo_mode(mode) == "quick":
        return {"judge": False, "mask": False, "stream": True}
    do_mask = mask_enabled()
    return {
        "judge": True,
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
                "Toolbox :5000",
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
    identity = _session_identity(tool_context)
    if identity:
        for key in _IDENTITY_ARG_NAMES:
            if key in args:
                args[key] = identity
    return None


session_service = InMemorySessionService()
_runners: dict[str, Runner] = {}
_transcripts: dict[str, list] = {}


def _build_runner(user_id: str) -> Runner:
    agent = LlmAgent(
        model=AGENT_MODEL,
        name="customer_support_assistant",
        description="Customer support agent for order questions and requests.",
        instruction=SQL_PROMPT_INSTRUCTION.format(USER_ID=user_id),
        tools=[*get_database_tools(), search_memory],
        before_tool_callback=_enforce_tenant_tool_callback,
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
    verdict = await call_a2a_agent(
        query=text, host=settings.judge_host, port=settings.judge_port
    ) or ""
    return "BLOCKED" not in verdict.upper(), verdict


async def _mask(text: str) -> tuple[str, str]:
    settings = resolve_service_settings()
    try:
        masked = await call_a2a_agent(
            query=text, host=settings.mask_host, port=settings.mask_port
        )
    except Exception as exc:
        return text, f"Masker unreachable, response sent unmasked ({exc})"
    out = masked or text
    note = (
        "no PII found, response unchanged"
        if out.strip() == text.strip()
        else "PII masked in the response"
    )
    return out, note


_phoenix_project = None


def trace_url(span) -> dict | None:
    """Phoenix deep link for a real span. None when telemetry is off."""
    if not telemetry_enabled() or not hasattr(span, "get_span_context"):
        return None
    global _phoenix_project
    settings = resolve_service_settings()
    trace_id = format(span.get_span_context().trace_id, "032x")
    public = settings.phoenix_public_url
    if _phoenix_project is None:
        try:
            with urllib.request.urlopen(f"{settings.phoenix_url}/v1/projects", timeout=2) as response:
                projects = json.load(response)["data"]
            _phoenix_project = next(item["id"] for item in projects if item["name"] == "default")
        except Exception:
            return {"trace_id": trace_id, "url": f"{public}/projects"}
    return {
        "trace_id": trace_id,
        "url": f"{public}/projects/{_phoenix_project}/traces/{trace_id}",
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
):
    """Run one turn and yield inspector events for chat and voice."""
    do_mask = mask_enabled() if mask is None else mask
    tracer = get_tracer()
    settings = resolve_service_settings()

    def blocked(stage, msg):
        if turn_span is not None:
            turn_span.set_attribute("turn.blocked", True)
            turn_span.set_attribute("turn.block_reason", stage)
            turn_span.set_attribute(ATTR.OUTPUT_VALUE, f"BLOCKED: {stage}")
        return {"type": "final", "blocked": True, "stage": stage, "response": msg}

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
        runs="regex blocklist in src/security/sanitizer.py",
    )
    if clean is None:
        yield blocked("sanitizer", f"Input rejected by sanitizer: {reason}")
        return

    if judge:
        yield {"type": "stage", "key": "judge", "stage": "A2A Security Judge"}
        t0 = time.perf_counter()
        with tracer.start_as_current_span("security.a2a_judge") as span:
            span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
            span.set_attribute(ATTR.INPUT_VALUE, clean)
            try:
                ok, verdict = await _judge(clean)
            except Exception as exc:
                span.set_attribute(ATTR.OUTPUT_VALUE, f"error: {exc}")
                yield {"type": "error", "error": f"Security Judge unreachable: {exc}"}
                return
            span.set_attribute(ATTR.OUTPUT_VALUE, "passed" if ok else "blocked")
        judged = (
            "cleared: echoed the input back unmodified"
            if ok
            else f"returned BLOCKED: {verdict.strip()[:200]}"
        )
        yield _step(
            "judge",
            "Security Judge",
            ok,
            judged,
            "security.a2a_judge",
            t0,
            kind="A2A",
            runs=f"ADK agent behind an A2A server at :{settings.judge_port}",
            text_chars=len(clean),
        )
        if not ok:
            yield blocked("judge", "Blocked by the A2A Security Judge (possible injection/unsafe input).")
            return

    yield {"type": "stage", "key": "agent", "stage": "Agent thinking"}
    content = types.Content(role="user", parts=[types.Part(text=clean)])
    run_config = RunConfig(streaming_mode=StreamingMode.SSE) if stream else None
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
            runs=f"ADK agent behind an A2A server at :{settings.mask_port}",
            in_chars=len(final_text),
            out_chars=len(masked),
        )
        final_text = masked

    if turn_span is not None:
        turn_span.set_attribute(ATTR.OUTPUT_VALUE, final_text)
    yield {"type": "final", "blocked": False, "response": final_text}


class LoginReq(BaseModel):
    email: str
    password: str


class ChatReq(BaseModel):
    user_id: str
    message: str
    mode: str | None = None


class LogoutReq(BaseModel):
    user_id: str


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
    }


@app.post("/api/logout")
async def logout(req: LogoutReq):
    _runners.pop(req.user_id, None)
    messages = _transcripts.pop(req.user_id, None)
    if messages:
        try:
            save_memory(messages, req.user_id)
        except Exception:
            pass
    try:
        await session_service.delete_session(
            app_name=APP_NAME,
            user_id=req.user_id,
            session_id=f"session_{req.user_id}",
        )
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatReq):
    runner = _runners.get(req.user_id)
    if runner is None:
        return JSONResponse({"ok": False, "error": "Not logged in."}, status_code=401)
    turn, span = _turn_span(req.user_id, req.message, "text")
    tool_calls, out = [], None
    try:
        async for event in text_pipeline(
            runner,
            req.user_id,
            req.message,
            turn_span=span,
            **demo_pipeline_kwargs(req.mode, stream_endpoint=False),
        ):
            if event["type"] == "tool_call":
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
        return {
            "ok": True,
            "blocked": True,
            "stage": out["stage"],
            "response": out["response"],
            "tool_calls": [],
        }
    _record(req.user_id, "user", req.message)
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
        try:
            linked = trace_url(span)
            if linked:
                yield json.dumps({"type": "trace", "span": "agent.turn", **linked}) + "\n"
            async for event in text_pipeline(
                runner,
                req.user_id,
                req.message,
                turn_span=span,
                **demo_pipeline_kwargs(req.mode, stream_endpoint=True),
            ):
                yield json.dumps(event, default=str) + "\n"
                if event["type"] == "final" and not event["blocked"]:
                    _record(req.user_id, "user", req.message)
                    _record(req.user_id, "assistant", event["response"])
        finally:
            turn.__exit__(None, None, None)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html", media_type="text/html")


@app.get("/architecture")
def architecture_page():
    return FileResponse(_STATIC / "architecture.html", media_type="text/html")


@app.get("/architecture.svg")
def architecture_svg():
    return FileResponse(_STATIC / "architecture.svg", media_type="image/svg+xml")


app.include_router(
    make_voice_router(
        runners=_runners,
        pipeline=text_pipeline,
        record=_record,
        trace_url=trace_url,
        mask_enabled=mask_enabled(),
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
