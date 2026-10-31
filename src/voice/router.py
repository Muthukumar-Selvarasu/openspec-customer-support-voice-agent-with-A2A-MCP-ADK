"""WebSocket voice cascade. The text pipeline is injected at mount time."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from src.core.telemetry import ATTR, get_tracer
from src.voice import cost
from src.voice.stt import STT_MODEL, transcribe
from src.voice.tts import TTS_MODEL, TTS_SAMPLE_RATE, TTS_VOICE, synthesize_stream

_UI_JS = Path(__file__).resolve().parent / "ui.js"
_AUDIO_CHUNK = 48000
_SETTLE_MS = 1500
_BYTES_PER_SEC = TTS_SAMPLE_RATE * 2
_SENT_END = re.compile(r"[.!?…](?:[\"')\]]+)?(?:\s|$)")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


MASK_ENABLED = _flag("MASK", "true")
AGENT_RESPONSE_STREAM = _flag("AGENT_RESPONSE_STREAM", "false")
STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK_ENABLED


def refresh_flags() -> None:
    """Re-read MASK and AGENT_RESPONSE_STREAM. Streaming stays off while MASK is on."""
    global MASK_ENABLED, AGENT_RESPONSE_STREAM, STREAM_ENABLED
    MASK_ENABLED = _flag("MASK", "true")
    AGENT_RESPONSE_STREAM = _flag("AGENT_RESPONSE_STREAM", "false")
    STREAM_ENABLED = AGENT_RESPONSE_STREAM and not MASK_ENABLED


def _config_warnings() -> list[str]:
    """Warn when streaming is requested together with masking. Masking wins."""
    refresh_flags()
    if not (AGENT_RESPONSE_STREAM and MASK_ENABLED):
        return []
    return [
        "AGENT_RESPONSE_STREAM=true is being IGNORED because MASK=true. A reply "
        "cannot be masked while it is spoken sentence-by-sentence, so streaming is "
        "turned OFF. Set MASK=false to enable streaming."
    ]


def print_config_warnings() -> None:
    for message in _config_warnings():
        print(f"\033[1;33mWARNING (voice config):\033[0m {message}")


def _take_complete(buf: str) -> tuple[str, str]:
    matches = list(_SENT_END.finditer(buf))
    if not matches:
        return "", buf
    cut = matches[-1].end()
    return buf[:cut], buf[cut:]


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def make_voice_router(
    *,
    runners,
    pipeline,
    record=None,
    trace_url=None,
    mask_enabled=None,
) -> APIRouter:
    """Build the ``/voice/ws`` router. ``pipeline`` is the text turn generator."""
    refresh_flags()
    router = APIRouter()
    do_mask = MASK_ENABLED if mask_enabled is None else mask_enabled
    tracer = get_tracer()

    @router.get("/voice/ui.js", include_in_schema=False)
    def ui_js():
        return FileResponse(_UI_JS, media_type="application/javascript")

    @router.websocket("/voice/ws")
    async def voice_ws(ws: WebSocket):
        await ws.accept()
        user_id = ws.query_params.get("user_id", "")
        if not user_id or user_id not in runners:
            await ws.send_text(json.dumps({"type": "error", "message": "Not logged in."}))
            await ws.close()
            return

        pending = ""
        stt_acc = {"in": 0, "out": 0}
        stt_time = {"sec": 0.0}
        agent_task: asyncio.Task | None = None
        settle_task: asyncio.Task | None = None
        stt_lock = asyncio.Lock()
        ws_send_lock = asyncio.Lock()

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

        async def run_agent(text: str) -> None:
            nonlocal pending
            answer_text = ""
            timing: dict[str, float] = {}
            agent_tok = {"in": 0, "out": 0}
            judge_tok = {"in": 0, "out": 0}
            mask_tok = {"in": 0, "out": 0}
            tts_tok = {"in": 0, "out": 0}
            tool_calls: list[dict] = []
            audio_bytes = {"n": 0}

            def clock(stage: str, t0: float) -> None:
                timing[stage] = round(time.perf_counter() - t0, 2)

            def mark(name: str) -> None:
                timing[name] = round(time.perf_counter() - turn_t0, 2)

            async def send_cost() -> None:
                all_stages = {
                    "stt": {
                        **stt_acc,
                        "usd": cost.usd("stt", stt_acc["in"], stt_acc["out"]),
                        "measured": True,
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

            def tts_step(first: list, chars: int) -> dict:
                seconds = audio_bytes["n"] / _BYTES_PER_SEC
                detail = f"spoke {chars:,} characters as {seconds:.1f} s of audio"
                if first:
                    detail += f", first audio after {first[0]:,} ms"
                else:
                    detail += ", no audio produced"
                runs = f"{TTS_MODEL} · voice {TTS_VOICE} · text in, 24 kHz PCM out"
                if STREAM_ENABLED:
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
                        stream=STREAM_ENABLED,
                        turn_span=span,
                        mask=do_mask,
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
                            if event["key"] == "judge" and judge_t0:
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
                            if "agent_end" not in timing and not display:
                                pending = ""
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
                        elif kind == "final":
                            if event["blocked"]:
                                blocked = event
                            else:
                                display = event["response"]
                            mark("agent_end")
                        await send_json(event)

                    if blocked:
                        await send_json(
                            {
                                "type": "blocked",
                                "stage": blocked["stage"],
                                "response": blocked["response"],
                            }
                        )
                        await send_json({"type": "turn_end"})
                        reset_query()
                        return

                    if STREAM_ENABLED and tts_queue is not None:
                        if tts_buffer.strip():
                            tts_queue.put_nowait(tts_buffer)
                        tts_queue.put_nowait(None)
                        await worker
                        await send_json(
                            {
                                "type": "response_text",
                                "text": display.strip(),
                                "tool_calls": tool_calls,
                            }
                        )
                        await send_json(tts_step(first_audio, len(display)))
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
                    answer_text = display.strip()
                finally:
                    if worker is not None and not worker.done():
                        worker.cancel()
                        try:
                            await worker
                        except asyncio.CancelledError:
                            pass

                answer_sec = time.perf_counter() - turn_t0
                timing["stt"] = round(stt_time["sec"], 2)
                timing["total_response"] = round(stt_time["sec"] + answer_sec, 2)
                await send_json({"type": "timing", "stages": timing})
                await send_cost()
                if record and answer_text:
                    record(user_id, "user", text)
                    record(user_id, "assistant", answer_text)
                await send_json({"type": "turn_end"})
                reset_query()
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None:
                    while current.uncancel():
                        pass
                span.set_attribute("turn.interrupted", True)
                await send_json({"type": "turn_end", "reason": "interrupted"})
                raise
            except Exception as exc:
                message = str(exc)[:300]
                await send_json({"type": "error", "message": message, "error": message})
                await send_json({"type": "turn_end"})
                reset_query()
            finally:
                turn.__exit__(None, None, None)

        async def settle_then_run() -> None:
            nonlocal agent_task
            try:
                await asyncio.sleep(_SETTLE_MS / 1000)
            except asyncio.CancelledError:
                return
            query = pending.strip()
            if query:
                agent_task = asyncio.create_task(run_agent(query))

        def restart_settle() -> None:
            nonlocal settle_task
            if settle_task and not settle_task.done():
                settle_task.cancel()
            settle_task = asyncio.create_task(settle_then_run())

        async def handle_burst(pcm: bytes) -> None:
            nonlocal pending
            if settle_task and not settle_task.done():
                settle_task.cancel()
            await send_json({"type": "stage", "key": "stt", "stage": "Transcribing"})
            started = time.perf_counter()
            async with stt_lock:
                text, stt_usage = await transcribe(pcm)
                stt_time["sec"] += time.perf_counter() - started
            tokens_in, tokens_out = cost.usage_tokens(stt_usage)
            audio_sec = len(pcm) / 32000
            if text:
                detail = f"transcribed {audio_sec:.1f} s of speech → “{text}”"
            else:
                detail = f"heard {audio_sec:.1f} s of audio but recognized no speech"
            extra = f"{tokens_in:,} in / {tokens_out:,} out tokens" if tokens_in or tokens_out else None
            await send_json(
                {
                    "type": "step",
                    "key": "stt",
                    "title": "Speech to text",
                    "status": "passed",
                    "detail": detail,
                    "span": "stt",
                    "ms": _ms(started),
                    "kind": "Voice",
                    "runs": f"{STT_MODEL} · audio in, text out",
                    "extra": extra,
                }
            )
            if text:
                pending = f"{pending} {text}".strip() if pending else text
                stt_acc["in"] += tokens_in
                stt_acc["out"] += tokens_out
                await send_json({"type": "partial_transcript", "text": pending})
            restart_settle()

        def stop_answer() -> None:
            nonlocal agent_task
            if agent_task and not agent_task.done():
                agent_task.cancel()

        try:
            while True:
                message = await ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    stop_answer()
                    asyncio.create_task(handle_burst(message["bytes"]))
                elif message.get("text"):
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "interrupt":
                        stop_answer()
        except WebSocketDisconnect:
            pass
        finally:
            for task in (agent_task, settle_task):
                if task and not task.done():
                    task.cancel()

    return router
