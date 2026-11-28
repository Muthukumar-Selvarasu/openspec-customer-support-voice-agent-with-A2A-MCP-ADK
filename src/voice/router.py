"""WebSocket voice cascade. The text pipeline is injected at mount time."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from src.core.telemetry import ATTR, get_tracer
from src.voice import cost
from src.voice.stt import live_model, open_utterance
from src.voice.tts import TTS_MODEL, TTS_SAMPLE_RATE, TTS_VOICE, synthesize_stream

_UI_JS = Path(__file__).resolve().parent / "ui.js"
_AUDIO_CHUNK = 48000
_SETTLE_MS = 1500
_QUICK_SETTLE_MS = 400
_BYTES_PER_SEC = TTS_SAMPLE_RATE * 2
_SENT_END = re.compile(r"[.!?…](?:[\"')\]]+)?(?:\s|$)")
_CLAUSE_END = re.compile(r"[:;]\s+|\n+")
_MIN_CLAUSE_CHARS = 24
_REDIRECT_PCM_CACHE: dict[tuple[int, str, str, str], bytes] = {}


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


MASK_ENABLED = _flag("MASK", "true")
AGENT_RESPONSE_STREAM = _flag("AGENT_RESPONSE_STREAM", "false")
STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK_ENABLED


def normalize_demo_mode(mode: str | None) -> str:
    """Missing or unrecognized values stay on Explain."""
    if isinstance(mode, str) and mode.strip().lower() == "quick":
        return "quick"
    return "explain"


def settle_ms(mode: str | None) -> int:
    """Quiet window before a voice turn. Quick is 400 ms; Explain is 1500 ms."""
    if normalize_demo_mode(mode) == "quick":
        return _QUICK_SETTLE_MS
    return _SETTLE_MS


def refresh_flags() -> None:
    """Re-read MASK and AGENT_RESPONSE_STREAM. Streaming stays off while MASK is on."""
    global MASK_ENABLED, AGENT_RESPONSE_STREAM, STREAM_ENABLED
    MASK_ENABLED = _flag("MASK", "true")
    AGENT_RESPONSE_STREAM = _flag("AGENT_RESPONSE_STREAM", "false")
    STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK_ENABLED


def _config_warnings() -> list[str]:
    """Warn when raw streaming is requested together with masking. Masking wins."""
    refresh_flags()
    if not (AGENT_RESPONSE_STREAM and MASK_ENABLED):
        return []
    return [
        "AGENT_RESPONSE_STREAM=true is being IGNORED because MASK=true. Raw "
        "streaming without masking is turned OFF while MASK=true (Explain voice "
        "turns still mask each finished sentence via A2A before speaking). Set "
        "MASK=false to enable raw streaming."
    ]


def print_config_warnings() -> None:
    for message in _config_warnings():
        print(f"\033[1;33mWARNING (voice config):\033[0m {message}")


def _take_complete(buf: str, *, mask: bool = False) -> tuple[str, str]:
    matches = list(_SENT_END.finditer(buf))
    if matches:
        cut = matches[-1].end()
        return buf[:cut], buf[cut:]
    for match in reversed(list(_CLAUSE_END.finditer(buf))):
        if match.end() >= _MIN_CLAUSE_CHARS:
            if (
                mask
                and match.group(0).startswith("\n")
                and buf[: match.start()].rstrip(" \t").endswith(",")
            ):
                continue
            cut = match.end()
            return buf[:cut], buf[cut:]
    return "", buf


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def make_voice_router(
    *,
    runners,
    pipeline,
    record=None,
    trace_url=None,
    mask_enabled=None,
    mask_text=None,
) -> APIRouter:
    """Build the ``/voice/ws`` router. ``pipeline`` is the text turn generator."""
    refresh_flags()
    router = APIRouter()
    tracer = get_tracer()

    def _is_mask_enabled() -> bool:
        if mask_enabled is None:
            return _flag("MASK", "true")
        if callable(mask_enabled):
            return bool(mask_enabled())
        return bool(mask_enabled)

    @router.get("/voice/ui.js", include_in_schema=False)
    def ui_js():
        return FileResponse(
            _UI_JS,
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @router.websocket("/voice/ws")
    async def voice_ws(ws: WebSocket):
        await ws.accept()
        user_id = ws.query_params.get("user_id", "")
        if not user_id or user_id not in runners:
            await ws.send_text(json.dumps({"type": "error", "message": "Not logged in."}))
            await ws.close()
            return

        pending = ""
        connection_mode = "explain"
        judge_override: bool | None = None
        mask_override: bool | None = None
        stt_acc = {"in": 0, "out": 0}
        stt_time = {"sec": 0.0}
        stt_measured = {"val": True}
        agent_task: asyncio.Task | None = None
        settle_task: asyncio.Task | None = None
        stt_lock = asyncio.Lock()
        ws_send_lock = asyncio.Lock()
        live = None
        live_reader: asyncio.Task | None = None
        live_text = ""
        live_started = 0.0

        async def send_json(obj: dict) -> None:
            async with ws_send_lock:
                await ws.send_text(json.dumps(obj, default=str))

        async def send_bytes(data: bytes) -> None:
            async with ws_send_lock:
                await ws.send_bytes(data)

        def reset_query() -> None:
            nonlocal pending
            pending = ""
            stt_acc["in"] = stt_acc["out"] = 0
            stt_time["sec"] = 0.0
            stt_measured["val"] = True

        async def run_agent(text: str, turn_mode: str) -> None:
            nonlocal pending
            quick = turn_mode == "quick"
            do_mask = _is_mask_enabled()
            turn_stream = True
            turn_mask = (
                (bool(mask_override) and do_mask)
                if mask_override is not None
                else (False if quick else do_mask)
            )
            turn_judge = bool(judge_override) if judge_override is not None else (not quick)
            answer_text = ""
            clean_text = text
            timing: dict[str, float] = {}
            agent_tok = {"in": 0, "out": 0}
            judge_tok = {"in": 0, "out": 0}
            mask_tok = {"in": 0, "out": 0}
            tts_tok = {"in": 0, "out": 0}
            tool_calls: list[dict] = []
            audio_bytes = {"n": 0}

            def clock(stage: str, t0: float) -> None:
                timing[stage] = round(time.perf_counter() - t0, 3)

            def mark(name: str) -> None:
                timing[name] = round(time.perf_counter() - turn_t0, 3)

            async def send_cost() -> None:
                all_stages = {
                    "stt": {
                        **stt_acc,
                        "usd": cost.usd("stt", stt_acc["in"], stt_acc["out"]),
                        "measured": stt_measured["val"],
                    },
                    "judge": {
                        **judge_tok,
                        "usd": cost.usd("llm", judge_tok["in"], judge_tok["out"]),
                        "measured": False,
                    },
                    "agent": {
                        **agent_tok,
                        "usd": cost.usd("llm", agent_tok["in"], agent_tok["out"]),
                        "measured": True,
                    },
                    "mask": {
                        **mask_tok,
                        "usd": cost.usd("llm", mask_tok["in"], mask_tok["out"]),
                        "measured": False,
                    },
                    "tts": {
                        **tts_tok,
                        "usd": cost.usd("tts", tts_tok["in"], tts_tok["out"]),
                        "measured": True,
                    },
                }
                stages = {key: value for key, value in all_stages.items() if value["in"] or value["out"]}
                total = round(sum(stage["usd"] for stage in stages.values()), 6)
                for stage in stages.values():
                    stage["usd"] = round(stage["usd"], 6)
                await send_json({"type": "cost", "total": total, "stages": stages})

            async def speak(segment: str, first: list) -> None:
                async for chunk in synthesize_stream(segment, usage_out=tts_tok):
                    if not first:
                        first.append(_ms(tts_t0))
                        mark("tts_start")
                    audio_bytes["n"] += len(chunk)
                    for offset in range(0, len(chunk), _AUDIO_CHUNK):
                        await send_bytes(chunk[offset : offset + _AUDIO_CHUNK])
                    mark("tts_end")

            async def speak_redirect(redirect_text: str, first: list) -> None:
                cache_key = (id(synthesize_stream), TTS_MODEL, TTS_VOICE, redirect_text)
                cached = _REDIRECT_PCM_CACHE.get(cache_key)
                if cached:
                    if not first:
                        first.append(_ms(tts_t0))
                        mark("tts_start")
                    audio_bytes["n"] += len(cached)
                    for offset in range(0, len(cached), _AUDIO_CHUNK):
                        await send_bytes(cached[offset : offset + _AUDIO_CHUNK])
                    mark("tts_end")
                    return
                chunks: list[bytes] = []
                async for chunk in synthesize_stream(redirect_text, usage_out=tts_tok):
                    if not first:
                        first.append(_ms(tts_t0))
                        mark("tts_start")
                    chunks.append(chunk)
                    audio_bytes["n"] += len(chunk)
                    for offset in range(0, len(chunk), _AUDIO_CHUNK):
                        await send_bytes(chunk[offset : offset + _AUDIO_CHUNK])
                    mark("tts_end")
                if chunks:
                    _REDIRECT_PCM_CACHE[cache_key] = b"".join(chunks)

            def tts_step(first: list, chars: int) -> dict:
                seconds = audio_bytes["n"] / _BYTES_PER_SEC
                detail = f"spoke {chars:,} characters as {seconds:.1f} s of audio"
                if first:
                    detail += f", first audio after {first[0]:,} ms"
                else:
                    detail += ", no audio produced"
                runs = f"{TTS_MODEL} · voice {TTS_VOICE} · text in, 24 kHz PCM out"
                if turn_stream:
                    runs += " · sentence by sentence, concurrent with the agent"
                return {
                    "type": "step",
                    "key": "tts",
                    "title": "Text to speech",
                    "status": "passed",
                    "detail": detail,
                    "span": "tts",
                    "ms": _ms(tts_t0),
                    "kind": "Voice",
                    "runs": runs,
                }

            turn = tracer.start_as_current_span("voice.turn")
            span = turn.__enter__()
            span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "CHAIN")
            span.set_attribute(ATTR.INPUT_VALUE, text)
            span.set_attribute("user.id", user_id)
            span.set_attribute("turn.channel", "voice")
            try:
                await send_json({"type": "processing"})
                turn_t0 = time.perf_counter()
                trace = trace_url(span) if trace_url else None
                if inspect.isawaitable(trace):
                    trace = await trace
                if trace:
                    await send_json({"type": "trace", "span": "voice.turn", **trace})

                runner = runners[user_id]
                display, blocked = "", None
                judge_t0 = mask_t0 = None
                tts_t0 = None
                first_audio: list = []
                tts_queue: asyncio.Queue | None = None
                worker = None
                tts_buffer = ""
                raw_seen = ""
                sentence_buf = ""
                shown = ""
                masked_once = False
                mask_any_redacted = False
                mask_last_note = "no PII found, response unchanged"
                mask_elapsed_sec = 0.0
                mask_in_chars = 0
                mask_out_chars = 0

                async def speak_masked(segment: str) -> None:
                    nonlocal shown, masked_once, mask_any_redacted, mask_last_note
                    nonlocal tts_t0, tts_queue, worker, pending
                    nonlocal mask_elapsed_sec, mask_in_chars, mask_out_chars
                    seg = segment.strip()
                    if not seg:
                        return
                    if not masked_once:
                        masked_once = True
                        await send_json({"type": "stage", "key": "mask", "stage": "A2A Data Masker"})
                    seg_t0 = time.perf_counter()
                    with tracer.start_as_current_span("security.a2a_mask") as mspan:
                        mspan.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
                        mspan.set_attribute(ATTR.INPUT_VALUE, seg[:500])
                        if mask_text is None:
                            spoken, note = seg, "response unchanged"
                        else:
                            spoken, note = await mask_text(seg)
                            spoken = spoken or seg
                        mspan.set_attribute(ATTR.OUTPUT_VALUE, spoken[:500])
                    mask_elapsed_sec += time.perf_counter() - seg_t0
                    mask_in_chars += len(seg)
                    mask_out_chars += len(spoken)
                    if spoken.strip() != seg.strip():
                        mask_any_redacted = True
                        mask_last_note = note
                    elif not mask_any_redacted:
                        mask_last_note = note
                    timing["mask"] = round(mask_elapsed_sec, 3)
                    mask_tok["in"] = max(1, mask_in_chars // 4)
                    mask_tok["out"] = max(1, mask_out_chars // 4)
                    shown = f"{shown} {spoken}".strip() if shown else spoken
                    if tts_queue is None:
                        pending = ""
                        tts_t0 = time.perf_counter()
                        tts_queue = asyncio.Queue()
                        worker = asyncio.create_task(tts_worker())
                        await send_json({"type": "stage", "key": "tts", "stage": "Speaking"})
                    await send_json(
                        {"type": "response_text", "text": shown, "tool_calls": tool_calls}
                    )
                    tts_queue.put_nowait(spoken)

                async def absorb_masked(full: str) -> None:
                    nonlocal raw_seen, sentence_buf
                    if not full:
                        return
                    added = full[len(raw_seen) :] if full.startswith(raw_seen) else full
                    raw_seen = full
                    sentence_buf += added
                    head, sentence_buf = _take_complete(sentence_buf, mask=True)
                    if head.strip():
                        await speak_masked(head)

                async def tts_worker() -> None:
                    while True:
                        segment = await tts_queue.get()
                        if segment is None:
                            break
                        try:
                            await speak(segment, first_audio)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass

                try:
                    async for event in pipeline(
                        runner,
                        user_id,
                        text,
                        stream=turn_stream,
                        turn_span=span,
                        mask=turn_mask,
                        judge=turn_judge,
                        judge_if_flagged=False,
                    ):
                        kind = event["type"]
                        if kind == "stage":
                            if event["key"] == "judge":
                                judge_t0 = time.perf_counter()
                            elif event["key"] == "mask":
                                mask_t0 = time.perf_counter()
                            elif event["key"] == "agent" and "agent_start" not in timing:
                                mark("agent_start")
                        elif kind == "step":
                            if event["key"] == "sanitize" and event.get("clean_text"):
                                clean_text = event["clean_text"]
                            elif event["key"] == "judge" and judge_t0:
                                clock("judge", judge_t0)
                                judge_tok["in"] = max(1, event.get("text_chars", len(text)) // 4)
                                judge_tok["out"] = 4
                            elif event["key"] == "mask" and mask_t0:
                                clock("mask", mask_t0)
                                mask_tok["in"] = max(1, event.get("in_chars", 0) // 4)
                                mask_tok["out"] = max(1, event.get("out_chars", 0) // 4)
                        elif kind == "llm":
                            agent_tok["in"] += event.get("tokens_in") or 0
                            agent_tok["out"] += event.get("tokens_out") or 0
                        elif kind == "tool_call":
                            tool_calls.append(
                                {"name": event["name"], "args": event["args"], "result": None}
                            )
                        elif kind == "tool_result":
                            for call in reversed(tool_calls):
                                if call["name"] == event["name"] and call["result"] is None:
                                    call["result"] = json.dumps(event["result"], default=str)[:800]
                                    break
                        elif kind == "delta":
                            pending = ""
                            if turn_mask:
                                await absorb_masked(event["text"])
                            else:
                                if "agent_end" not in timing and not display:
                                    tts_t0 = time.perf_counter()
                                    tts_queue = asyncio.Queue()
                                    worker = asyncio.create_task(tts_worker())
                                    await send_json({"type": "stage", "key": "tts", "stage": "Speaking"})
                                new = event["text"][len(display) :]
                                display = event["text"]
                                tts_buffer += new
                                await send_json(
                                    {
                                        "type": "response_text",
                                        "text": display.strip(),
                                        "tool_calls": tool_calls,
                                    }
                                )
                                head, tts_buffer = _take_complete(tts_buffer)
                                if head.strip() and tts_queue is not None:
                                    tts_queue.put_nowait(head)
                        elif kind == "error":
                            msg = event.get("error") or event.get("message") or "Pipeline error."
                            await send_json({"type": "error", "message": msg, "error": msg})
                            await send_json({"type": "turn_end"})
                            reset_query()
                            return
                        elif kind == "final":
                            if event["blocked"]:
                                blocked = event
                            else:
                                pending = ""
                                display = event["response"]
                                if turn_mask:
                                    await absorb_masked(display)
                                    if sentence_buf.strip():
                                        await speak_masked(sentence_buf)
                                        sentence_buf = ""
                                    if masked_once:
                                        await send_json(
                                            {
                                                "type": "step",
                                                "key": "mask",
                                                "title": "Data Masker",
                                                "status": "passed",
                                                "detail": mask_last_note,
                                                "span": "security.a2a_mask",
                                                "ms": int(round(mask_elapsed_sec * 1000)),
                                                "kind": "A2A",
                                                "in_chars": mask_in_chars,
                                                "out_chars": mask_out_chars,
                                            }
                                        )
                                    event = {**event, "response": shown or display}
                            mark("agent_end")
                        if kind == "delta" and turn_mask:
                            continue
                        await send_json(event)

                    if blocked:
                        blocked_payload = {
                            "type": "blocked",
                            "stage": blocked["stage"],
                            "response": blocked["response"],
                        }
                        if blocked.get("reason") is not None:
                            blocked_payload["reason"] = blocked["reason"]
                        await send_json(blocked_payload)
                        if blocked.get("reason") == "off_topic" and blocked.get("response"):
                            redirect_text = str(blocked["response"])
                            pending = ""
                            tts_t0 = time.perf_counter()
                            await send_json({"type": "stage", "key": "tts", "stage": "Speaking"})
                            await speak_redirect(redirect_text, first_audio)
                            await send_json(tts_step(first_audio, len(redirect_text)))
                        await send_json({"type": "turn_end"})
                        reset_query()
                        return

                    if turn_stream and tts_queue is not None:
                        if tts_buffer.strip() and not turn_mask:
                            tts_queue.put_nowait(tts_buffer)
                        tts_queue.put_nowait(None)
                        await worker
                        await send_json(
                            {
                                "type": "response_text",
                                "text": (shown or display).strip(),
                                "tool_calls": tool_calls,
                            }
                        )
                        await send_json(tts_step(first_audio, len(shown or display)))
                    else:
                        await send_json(
                            {
                                "type": "response_text",
                                "text": display,
                                "tool_calls": tool_calls,
                            }
                        )
                        pending = ""
                        tts_t0 = time.perf_counter()
                        await send_json({"type": "stage", "key": "tts", "stage": "Speaking"})
                        await speak(display, first_audio)
                        await send_json(tts_step(first_audio, len(display)))
                    answer_text = (shown if turn_mask and shown else display).strip()
                    span.set_attribute(ATTR.OUTPUT_VALUE, answer_text)
                finally:
                    if worker is not None and not worker.done():
                        worker.cancel()
                        try:
                            await worker
                        except asyncio.CancelledError:
                            pass

                answer_sec = time.perf_counter() - turn_t0
                timing["stt"] = round(stt_time["sec"], 3)
                timing["total_response"] = round(stt_time["sec"] + answer_sec, 3)
                await send_json({"type": "timing", "stages": timing})
                await send_cost()
                if record and answer_text:
                    record(user_id, "user", clean_text)
                    record(user_id, "assistant", answer_text)
                await send_json({"type": "turn_end"})
                reset_query()
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None:
                    while current.uncancel():
                        pass
                span.set_attribute("turn.interrupted", True)
                if agent_task is None or agent_task is current:
                    try:
                        await send_json({"type": "turn_end", "reason": "interrupted"})
                    except (WebSocketDisconnect, RuntimeError):
                        return
                raise
            except Exception as exc:
                message = str(exc)[:300]
                await send_json({"type": "error", "message": message, "error": message})
                await send_json({"type": "turn_end"})
                reset_query()
            finally:
                turn.__exit__(None, None, None)

        async def settle_then_run(turn_mode: str) -> None:
            nonlocal agent_task
            try:
                await asyncio.sleep(settle_ms(turn_mode) / 1000)
            except asyncio.CancelledError:
                return
            query = pending.strip()
            if query:
                agent_task = asyncio.create_task(run_agent(query, turn_mode))

        def restart_settle() -> None:
            nonlocal settle_task
            if turn_running():
                return
            if settle_task and not settle_task.done():
                settle_task.cancel()
            turn_mode = connection_mode
            settle_task = asyncio.create_task(settle_then_run(turn_mode))

        def commit_now() -> None:
            nonlocal agent_task, settle_task
            if turn_running():
                return
            if settle_task and not settle_task.done():
                settle_task.cancel()
            query = pending.strip()
            if query:
                agent_task = asyncio.create_task(run_agent(query, connection_mode))

        async def read_live(session) -> None:
            nonlocal live_text
            try:
                async for text in session.updates():
                    live_text = text
                    shown = f"{pending} {text}".strip() if pending else text
                    try:
                        await send_json({"type": "partial_transcript", "text": shown})
                    except (WebSocketDisconnect, RuntimeError):
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if getattr(session, "_closed", False):
                    return
                message = str(exc)[:300]
                try:
                    await send_json({"type": "error", "message": message, "error": message})
                except (WebSocketDisconnect, RuntimeError):
                    return

        async def close_live() -> None:
            nonlocal live, live_reader
            session = live
            reader = live_reader
            live = None
            live_reader = None
            if reader is not None and not reader.done():
                reader.cancel()
            if session is not None:
                await session.close()
            if reader is not None:
                try:
                    await reader
                except (asyncio.CancelledError, Exception):
                    pass

        def turn_running() -> bool:
            if agent_task is None or agent_task.done():
                return False
            cancelling = getattr(agent_task, "cancelling", None)
            return not (cancelling and cancelling())

        async def _open_live_locked() -> bool:
            nonlocal live, live_reader, live_text, live_started
            session = open_utterance()
            try:
                await session.open()
            except Exception as exc:
                message = str(exc)[:300]
                await send_json({"type": "error", "message": message, "error": message})
                return False
            live = session
            live_text = ""
            live_started = time.perf_counter()
            await send_json({"type": "stage", "key": "stt", "stage": "Transcribing"})
            live_reader = asyncio.create_task(read_live(session))
            return True

        async def on_audio(pcm: bytes) -> None:
            nonlocal live, live_reader, live_text, live_started
            if turn_running():
                return
            if settle_task and not settle_task.done():
                settle_task.cancel()
            async with stt_lock:
                if live is not None and live_reader is not None and live_reader.done():
                    await close_live()
                if live is None:
                    if not await _open_live_locked():
                        return
                elif live_started == 0.0:
                    live_started = time.perf_counter()
                try:
                    await live.send(pcm)
                except Exception:
                    await close_live()
                    if not await _open_live_locked():
                        return
                    try:
                        await live.send(pcm)
                    except Exception as exc:
                        message = str(exc)[:300]
                        await send_json({"type": "error", "message": message, "error": message})
                        return
                await asyncio.sleep(0)

        async def on_utterance_end(commit: bool = False) -> None:
            nonlocal pending, live_text, live_started
            async with stt_lock:
                session = live
                reader = live_reader
                started = live_started or time.perf_counter()
                if session is None:
                    if commit and pending.strip():
                        commit_now()
                    elif commit:
                        await send_json({"type": "turn_end", "reason": "empty"})
                    return
                try:
                    text, stt_usage, pcm_bytes = await session.flush(reader)
                except Exception as exc:
                    message = str(exc)[:300]
                    await send_json({"type": "error", "message": message, "error": message})
                    return
                text = (text or live_text or "").strip()
                live_text = ""
                live_started = 0.0
                stt_time["sec"] += time.perf_counter() - started
            if not text:
                if commit and pending.strip():
                    commit_now()
                elif commit:
                    await send_json({"type": "turn_end", "reason": "empty"})
                return
            usage_in, usage_out = cost.usage_tokens(stt_usage)
            has_usage = bool(usage_in or usage_out)
            tokens_in, tokens_out = cost.stt_charge(stt_usage, pcm_bytes)
            if (tokens_in or tokens_out) and not has_usage:
                stt_measured["val"] = False
            audio_sec = pcm_bytes / 32000
            extra = f"{tokens_in:,} in / {tokens_out:,} out tokens" if tokens_in or tokens_out else None
            await send_json(
                {
                    "type": "step",
                    "key": "stt",
                    "title": "Speech to text",
                    "status": "passed",
                    "detail": f"transcribed {audio_sec:.1f} s of speech → “{text}”",
                    "span": "stt",
                    "ms": _ms(started),
                    "kind": "Voice",
                    "runs": f"{live_model()} · audio in, text out",
                    "extra": extra,
                }
            )
            pending = f"{pending} {text}".strip() if pending else text
            stt_acc["in"] += tokens_in
            stt_acc["out"] += tokens_out
            await send_json({"type": "partial_transcript", "text": pending})
            if commit:
                commit_now()
            else:
                restart_settle()

        def stop_answer() -> None:
            nonlocal agent_task, settle_task
            if settle_task and not settle_task.done():
                settle_task.cancel()
            if agent_task and not agent_task.done():
                agent_task.cancel()

        try:
            while True:
                message = await ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await on_audio(message["bytes"])
                elif message.get("text"):
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "mode":
                        connection_mode = normalize_demo_mode(data.get("mode"))
                        if "judge" in data:
                            judge_override = (
                                None if data["judge"] is None else bool(data["judge"])
                            )
                        if "mask" in data:
                            mask_override = (
                                None if data["mask"] is None else bool(data["mask"])
                            )
                    elif data.get("type") == "guardrails":
                        if "judge" in data:
                            judge_override = (
                                None if data["judge"] is None else bool(data["judge"])
                            )
                        if "mask" in data:
                            mask_override = (
                                None if data["mask"] is None else bool(data["mask"])
                            )
                    elif data.get("type") == "utterance_end":
                        await on_utterance_end(commit=bool(data.get("commit")))
                    elif data.get("type") == "interrupt":
                        stop_answer()
        except WebSocketDisconnect:
            pass
        finally:
            await close_live()
            for task in (agent_task, settle_task):
                if task and not task.done():
                    task.cancel()

    return router
