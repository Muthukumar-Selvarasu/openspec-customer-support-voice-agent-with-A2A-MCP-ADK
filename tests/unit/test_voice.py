"""Unit tests for voice framing, transcript cleanup, sentence chunking, and cost."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from src.voice.cost import estimate_tokens, usd, usage_tokens
from src.voice.stt import _clean, pcm16_to_wav
from src.voice.tts import split_sentences


def test_pcm16_to_wav_starts_with_riff_and_wave() -> None:
    wav = pcm16_to_wav(b"\x00\x01" * 16, sample_rate=16000)
    assert wav.startswith(b"RIFF")
    assert wav[8:12] == b"WAVE"


def test_clean_strips_vtt_cues_and_timecodes() -> None:
    raw = "WEBVTT\n00:00:01.093 --> 00:00:02.500\nWhere is order 3?\n00:00:03"
    assert _clean(raw) == "Where is order 3?"


def test_clean_drops_no_speech_and_punctuation_only() -> None:
    assert _clean("NO_SPEECH") == ""
    assert _clean("...") == ""
    assert _clean("  Where is order 3?  ") == "Where is order 3?"


def test_split_sentences_chunks_on_punctuation() -> None:
    assert split_sentences("") == []
    chunks = split_sentences(
        "Alpha bravo charlie delta echo. Foxtrot golf hotel india juliet."
    )
    assert len(chunks) == 2
    assert chunks[0].endswith(".")
    assert "Foxtrot" in chunks[1]


def test_split_sentences_keeps_ellipsis_boundary() -> None:
    chunks = split_sentences(
        "Hold on a moment before continuing… Then finish this longer second sentence now."
    )
    assert chunks
    assert any("…" in chunk or "Then finish" in chunk for chunk in chunks)


def test_cost_usd_is_non_negative() -> None:
    quiet = usd("tts", 0, 0)
    spoken = usd("tts", 1_000, 2_000)
    assert quiet >= 0
    assert spoken >= quiet
    assert isinstance(spoken, float)


def test_cost_estimate_tokens_uses_about_four_characters() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("12345678") == 2


def test_cost_usage_tokens_reads_metadata() -> None:
    usage = SimpleNamespace(prompt_token_count=12, candidates_token_count=3)
    assert usage_tokens(usage) == (12, 3)
    assert usage_tokens(None) == (0, 0)


def test_tts_and_stt_defaults_are_the_cascade_models() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    stt = (root / "src" / "voice" / "stt.py").read_text(encoding="utf-8")
    tts = (root / "src" / "voice" / "tts.py").read_text(encoding="utf-8")
    assert 'VOICE_STT_MODEL", "gemini-3.1-flash-lite"' in stt
    assert 'VOICE_TTS_MODEL", "gemini-3.8-flash-tts"' in tts


def test_stream_enabled_is_off_when_mask_wins(monkeypatch) -> None:
    monkeypatch.setenv("MASK", "true")
    monkeypatch.setenv("AGENT_RESPONSE_STREAM", "true")
    from src.voice import router

    router.refresh_flags()
    assert router.AGENT_RESPONSE_STREAM is True
    assert router.MASK_ENABLED is True
    assert router.STREAM_ENABLED is False
    assert router.STREAM_ENABLED == (router.AGENT_RESPONSE_STREAM and not router.MASK_ENABLED)


def test_config_warnings_keep_mask_conflict_and_skip_cloud_project(monkeypatch) -> None:
    monkeypatch.setenv("MASK", "true")
    monkeypatch.setenv("AGENT_RESPONSE_STREAM", "true")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    from src.voice.router import _config_warnings

    warnings = _config_warnings()
    joined = " ".join(warnings).lower()
    assert warnings
    assert "agent_response_stream=true" in joined
    assert "mask=true" in joined
    assert "google_cloud_project" not in joined
    assert "cloud project" not in joined
    assert "unmasked" not in joined


def test_settle_window_defaults_to_1500_ms() -> None:
    from src.voice.router import _SETTLE_MS

    assert _SETTLE_MS == 1500


def test_settle_ms_quick_is_400_and_explain_is_1500() -> None:
    from src.voice.router import settle_ms

    assert settle_ms("quick") == 400
    assert settle_ms(" QUICK ") == 400
    assert settle_ms("explain") == 1500
    assert settle_ms(None) == 1500
    assert settle_ms("nope") == 1500


def _app(pipeline, monkeypatch):
    from fastapi import FastAPI

    from src.voice import router

    monkeypatch.setattr(router, "transcribe", _scripted_transcribe)
    app = FastAPI()
    app.include_router(
        router.make_voice_router(runners={"shopper": object()}, pipeline=pipeline)
    )
    return app


_TRANSCRIPTS = ["status of my order", "and a summary"]


async def _scripted_transcribe(pcm: bytes, sample_rate: int = 16000):
    from types import SimpleNamespace

    text = _TRANSCRIPTS[_scripted_transcribe.calls]
    _scripted_transcribe.calls += 1
    return text, SimpleNamespace(prompt_token_count=10, candidates_token_count=4)


_scripted_transcribe.calls = 0


def _events(ws, limit: int = 30) -> list[dict]:
    import json

    events = []
    for _ in range(limit):
        message = ws.receive()
        if message.get("text"):
            events.append(json.loads(message["text"]))
            if events[-1].get("type") == "turn_end":
                break
        elif message.get("bytes") is not None:
            events.append({"type": "_audio", "n": len(message["bytes"])})
    return events


def test_two_bursts_combine_into_one_pipeline_query(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.voice import router

    monkeypatch.setattr(router, "_SETTLE_MS", 80)
    _scripted_transcribe.calls = 0
    queries: list[str] = []

    async def pipeline(runner, user_id, text, **kwargs):
        queries.append(text)
        yield {
            "type": "final",
            "blocked": True,
            "response": "blocked",
            "stage": "judge",
        }

    app = _app(pipeline, monkeypatch)
    pcm = b"\x00\x01" * 160
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(pcm)
            ws.send_bytes(pcm)
            events = _events(ws)

    assert queries == ["status of my order and a summary"]
    assert any(event.get("type") == "partial_transcript" for event in events)
    assert events[-1] == {"type": "turn_end"}


def test_interrupt_emits_turn_end_interrupted(monkeypatch) -> None:
    import asyncio
    import json

    from fastapi.testclient import TestClient

    from src.voice import router

    monkeypatch.setattr(router, "_SETTLE_MS", 30)

    async def transcribe(pcm: bytes, sample_rate: int = 16000):
        from types import SimpleNamespace

        return "where is my order", SimpleNamespace(prompt_token_count=8, candidates_token_count=3)

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        yield b"\x00\x01" * 200
        await asyncio.sleep(30)

    monkeypatch.setattr(router, "transcribe", transcribe)
    monkeypatch.setattr(router, "synthesize_stream", synthesize_stream)

    async def pipeline(runner, user_id, text, **kwargs):
        yield {
            "type": "final",
            "blocked": False,
            "response": "Your order has shipped.",
            "stage": "agent",
        }

    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            saw_audio = False
            interrupted = None
            for _ in range(40):
                message = ws.receive()
                if message.get("bytes") is not None:
                    saw_audio = True
                    ws.send_text(json.dumps({"type": "interrupt"}))
                    continue
                if not message.get("text"):
                    continue
                event = json.loads(message["text"])
                if event.get("type") == "turn_end":
                    interrupted = event
                    break
    assert saw_audio
    assert interrupted == {"type": "turn_end", "reason": "interrupted"}


def test_interrupt_keeps_the_assistant_reply_in_the_transcript() -> None:
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    start = source.index("function bubbleHasAnswer(")
    end = source.index("function onMessage(", start)
    script = "\n".join(
        [
            "let node = null;",
            "let userBubble = { id: 'user' };",
            source[start:end],
            "function makeBubble(text, typing) {",
            "  return {",
            "    textContent: text,",
            "    innerHTML: text,",
            "    querySelector(sel) { return sel === '.typing' && typing ? { typing: true } : null; },",
            "  };",
            "}",
            "function makeNode(bubble) {",
            "  const removed = [];",
            "  return {",
            "    bubble,",
            "    removed,",
            "    querySelector(sel) {",
            "      if (sel === '.bubble') return bubble;",
            "      if (sel === '.pill') return { textContent: '1' };",
            "      return null;",
            "    },",
            "    querySelectorAll() { return [{ remove() { removed.push(1); } }]; },",
            "  };",
            "}",
            "const answered = makeBubble('Your order has shipped.', false);",
            "const answeredNode = makeNode(answered);",
            "node = answeredNode;",
            "onTurnEnd({ reason: 'interrupted' });",
            "const kept = { nodeCleared: node === null, text: answered.innerHTML, removed: answeredNode.removed.length };",
            "const waiting = makeBubble('Listening…', true);",
            "const waitingNode = makeNode(waiting);",
            "node = waitingNode;",
            "userBubble = { id: 'user' };",
            "onTurnEnd({ reason: 'interrupted' });",
            "const reset = { sameNode: node === waitingNode, html: waiting.innerHTML, removed: waitingNode.removed.length };",
            "console.log(JSON.stringify({ kept, reset }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    import json

    result = json.loads(proc.stdout)
    assert result["kept"]["nodeCleared"] is True
    assert result["kept"]["text"] == "Your order has shipped."
    assert result["kept"]["removed"] == 0
    assert result["reset"]["sameNode"] is True
    assert "Listening…" in result["reset"]["html"]
    assert result["reset"]["removed"] == 1


def test_mic_off_removes_a_listening_placeholder() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    start = source.index("function bubbleHasAnswer(")
    end = source.index("function onTurnEnd(", start)
    script = "\n".join(
        [
            "let node = null;",
            "let userBubble = { id: 'user' };",
            source[start:end],
            "const removed = [];",
            "const bubble = {",
            "  textContent: 'Listening…',",
            "  querySelector(sel) { return sel === '.typing' ? {} : null; },",
            "};",
            "node = { querySelector(sel) { return sel === '.bubble' ? bubble : null; }, remove() { removed.push(1); } };",
            "dropUnansweredTurn();",
            "const cleared = { removed: removed.length, node: node, user: userBubble.id };",
            "const answer = { textContent: 'Your order has shipped.', querySelector() { return null; } };",
            "let answerNode = { querySelector(sel) { return sel === '.bubble' ? answer : null; }, remove() { removed.push('answer'); } };",
            "node = answerNode;",
            "dropUnansweredTurn();",
            "console.log(JSON.stringify({ cleared, kept: node === null, answerRemoved: removed.includes('answer') }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["cleared"]["removed"] == 1
    assert result["cleared"]["node"] is None
    assert result["cleared"]["user"] == "user"
    assert result["kept"] is True
    assert result["answerRemoved"] is False


def FastAPI_app(pipeline):
    from fastapi import FastAPI

    from src.voice.router import make_voice_router

    app = FastAPI()
    app.include_router(make_voice_router(runners={"shopper": object()}, pipeline=pipeline))
    return app


def test_router_does_not_import_the_shopper_app() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "router.py").read_text(
        encoding="utf-8"
    )
    assert "src.api" not in source
    assert "GOOGLE_CLOUD_PROJECT" not in source


def _patch_voice(monkeypatch, pipeline, *, mask: str = "true", stream: str = "true"):
    from fastapi import FastAPI

    from src.voice import router

    monkeypatch.setenv("MASK", mask)
    monkeypatch.setenv("AGENT_RESPONSE_STREAM", stream)
    router.refresh_flags()

    async def transcribe(pcm: bytes, sample_rate: int = 16000):
        return "where is my order", SimpleNamespace(prompt_token_count=4, candidates_token_count=2)

    monkeypatch.setattr(router, "transcribe", transcribe)
    app = FastAPI()
    app.include_router(router.make_voice_router(runners={"shopper": object()}, pipeline=pipeline))
    return router, app


def test_demo_mode_quick_skips_judge_and_speaks_first_sentence(monkeypatch) -> None:
    import asyncio
    import json
    import threading

    from fastapi.testclient import TestClient

    spoken: list[str] = []
    flags: list[dict] = []
    settled: list[str] = []
    gate = threading.Event()
    first = "First sentence is ready now. "
    full = first + "Second sentence follows after this."

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        spoken.append(text)
        yield b"\x00\x01" * 200

    async def pipeline(runner, user_id, text, **kwargs):
        flags.append(dict(kwargs))
        yield {
            "type": "step",
            "key": "sanitize",
            "title": "Sanitizer",
            "status": "passed",
            "detail": "ok",
            "span": "security.sanitize",
            "ms": 1,
        }
        yield {"type": "delta", "text": first}
        await asyncio.to_thread(gate.wait, 5)
        yield {"type": "delta", "text": full}
        yield {"type": "final", "blocked": False, "response": full}

    router, app = _patch_voice(monkeypatch, pipeline)

    def fast_settle(mode):
        settled.append(mode)
        return 20

    monkeypatch.setattr(router, "settle_ms", fast_settle)
    monkeypatch.setattr(router, "synthesize_stream", synthesize_stream)
    assert router.STREAM_ENABLED is False
    assert router.STREAM_ENABLED == (router.AGENT_RESPONSE_STREAM and not router.MASK_ENABLED)

    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_text(json.dumps({"type": "mode", "mode": "quick"}))
            ws.send_bytes(b"\x00\x01" * 160)
            saw_audio = False
            keys: list[str] = []
            for _ in range(40):
                message = ws.receive()
                if message.get("bytes") is not None:
                    saw_audio = True
                    break
                if message.get("text"):
                    event = json.loads(message["text"])
                    if event.get("key"):
                        keys.append(event["key"])
            assert saw_audio
            assert spoken
            assert spoken[0].startswith("First sentence")
            assert "Second" not in "".join(spoken)
            assert "sanitize" in keys
            assert "judge" not in keys
            assert "mask" not in keys
            gate.set()
            _events(ws)

    assert settled == ["quick"]
    assert flags[0]["judge"] is False
    assert flags[0]["mask"] is False
    assert flags[0]["stream"] is True


def test_demo_mode_explain_keeps_judge_masker_and_buffered_speech(monkeypatch) -> None:
    import json

    from fastapi.testclient import TestClient

    spoken: list[str] = []
    flags: list[dict] = []
    settled: list[str] = []
    reply = "Full answer stays buffered. Second sentence too."

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        spoken.append(text)
        yield b"\x00\x01" * 80

    async def pipeline(runner, user_id, text, **kwargs):
        flags.append(dict(kwargs))
        yield {
            "type": "step",
            "key": "sanitize",
            "title": "Sanitizer",
            "status": "passed",
            "detail": "ok",
            "span": "security.sanitize",
            "ms": 1,
        }
        yield {
            "type": "step",
            "key": "judge",
            "title": "Security Judge",
            "status": "passed",
            "detail": "ok",
            "span": "security.a2a_judge",
            "ms": 1,
        }
        yield {
            "type": "step",
            "key": "mask",
            "title": "Data Masker",
            "status": "passed",
            "detail": "ok",
            "span": "security.a2a_mask",
            "ms": 1,
        }
        yield {"type": "final", "blocked": False, "response": reply}

    router, app = _patch_voice(monkeypatch, pipeline)

    def fast_settle(mode):
        settled.append(mode)
        return 20

    monkeypatch.setattr(router, "settle_ms", fast_settle)
    monkeypatch.setattr(router, "synthesize_stream", synthesize_stream)

    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            events = _events(ws)

    assert settled == ["explain"]
    assert flags[0]["judge"] is True
    assert flags[0]["mask"] is True
    assert flags[0]["stream"] is False
    assert flags[0]["stream"] == router.STREAM_ENABLED
    assert spoken == [reply]
    assert any(event.get("key") == "judge" for event in events)
    assert any(event.get("key") == "mask" for event in events)
    assert any(event.get("type") == "_audio" for event in events)


def test_demo_mode_inflight_turn_keeps_the_mode_it_started_with(monkeypatch) -> None:
    import asyncio
    import json
    import threading

    from fastapi.testclient import TestClient

    flags: list[dict] = []
    started = threading.Event()
    release = threading.Event()

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        yield b"\x00\x01" * 40

    async def pipeline(runner, user_id, text, **kwargs):
        flags.append(dict(kwargs))
        if len(flags) == 1:
            started.set()
            await asyncio.to_thread(release.wait, 5)
        yield {"type": "final", "blocked": False, "response": "done"}

    router, app = _patch_voice(monkeypatch, pipeline)
    monkeypatch.setattr(router, "settle_ms", lambda mode: 20)
    monkeypatch.setattr(router, "synthesize_stream", synthesize_stream)

    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            assert started.wait(3)
            ws.send_text(json.dumps({"type": "mode", "mode": "quick"}))
            release.set()
            assert _events(ws)[-1]["type"] == "turn_end"
            ws.send_bytes(b"\x00\x01" * 160)
            assert _events(ws)[-1]["type"] == "turn_end"

    assert flags[0]["judge"] is True
    assert flags[0]["mask"] is True
    assert flags[0]["stream"] is False
    assert flags[1]["judge"] is False
    assert flags[1]["mask"] is False
    assert flags[1]["stream"] is True


def test_pagehide_keeps_a_live_mic_signed_in() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "src" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    start = source.index("function shouldFlushOnPageHide(")
    end = source.index("window.addEventListener('pagehide'", start)
    script = "\n".join(
        [
            "var USER = 'alice.jones@example.com';",
            "var window = { csVoiceOn: false };",
            source[start:end],
            "const idle = shouldFlushOnPageHide({ persisted: false });",
            "const frozen = shouldFlushOnPageHide({ persisted: true });",
            "window.csVoiceOn = true;",
            "const speaking = shouldFlushOnPageHide({ persisted: false });",
            "USER = null;",
            "window.csVoiceOn = false;",
            "const signedOut = shouldFlushOnPageHide({ persisted: false });",
            "console.log(JSON.stringify({ idle, frozen, speaking, signedOut }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result == {"idle": True, "frozen": False, "speaking": False, "signedOut": False}


def test_barge_in_only_while_the_agent_is_speaking() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    start = source.index("function bargeIn(")
    end = source.index("function downsample(", start)
    script = "\n".join(
        [
            "let agentSpeaking = false;",
            "let stopped = 0;",
            "let interrupted = 0;",
            "function stopPlayback() { stopped += 1; }",
            "function sendInterrupt() { interrupted += 1; }",
            source[start:end],
            "bargeIn();",
            "const quiet = { stopped, interrupted };",
            "agentSpeaking = true;",
            "bargeIn();",
            "console.log(JSON.stringify({ quiet, speaking: { stopped, interrupted } }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["quiet"] == {"stopped": 0, "interrupted": 0}
    assert result["speaking"] == {"stopped": 1, "interrupted": 1}


def test_more_speech_does_not_cancel_the_answer_in_progress(monkeypatch) -> None:
    import asyncio
    import threading
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from src.voice import router

    started = threading.Event()
    heard_more = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    queries: list[str] = []

    async def transcribe(pcm: bytes, sample_rate: int = 16000):
        calls["n"] += 1
        if calls["n"] >= 2:
            heard_more.set()
        text = "hi hello" if calls["n"] == 1 else "how are you"
        return text, SimpleNamespace(prompt_token_count=4, candidates_token_count=2)

    async def pipeline(runner, user_id, text, **kwargs):
        queries.append(text)
        started.set()
        await asyncio.to_thread(release.wait, 5)
        yield {
            "type": "final",
            "blocked": True,
            "response": "blocked",
            "stage": "judge",
        }

    monkeypatch.setattr(router, "transcribe", transcribe)
    monkeypatch.setattr(router, "settle_ms", lambda mode: 20)
    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            assert started.wait(3)
            ws.send_bytes(b"\x00\x01" * 160)
            assert heard_more.wait(3)
            release.set()
            events = _events(ws)

    assert queries == ["hi hello"]
    assert events[-1] == {"type": "turn_end"}


def test_session_check_follows_the_live_runner() -> None:
    from fastapi.testclient import TestClient

    import src.api.web as web

    web._runners["alice.jones@example.com"] = object()
    try:
        client = TestClient(web.app)
        live = client.post("/api/session", json={"user_id": "alice.jones@example.com"})
        gone = client.post("/api/session", json={"user_id": "nobody@example.com"})
    finally:
        web._runners.pop("alice.jones@example.com", None)
    assert live.status_code == 200
    assert live.json()["ok"] is True
    assert gone.status_code == 401


@pytest.mark.skipif(not os.getenv("GOOGLE_API_KEY"), reason="GOOGLE_API_KEY is not set")
async def test_live_transcribe_when_api_key_set() -> None:
    from src.voice.stt import transcribe

    text, _usage = await transcribe(b"\x00\x00" * 1600)
    assert isinstance(text, str)
