"""Unit tests for voice framing, transcript cleanup, sentence chunking, and cost."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from src.voice.cost import estimate_tokens, usd, usage_tokens
from src.voice.stt import _clean, pcm16_to_wav
from src.voice.tts import split_sentences


def test_live_session_same_connection_forwards_two_phrases(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    from google.genai import types

    from src.voice import stt

    events: list[str] = []
    generated = {"n": 0}

    class Session:
        def __init__(self) -> None:
            self.audio: list[bytes] = []
            self.ended = False
            self.closed = False
            self.second = False

        async def send_realtime_input(self, *, audio=None, audio_stream_end=None, **kwargs):
            if audio is not None:
                self.audio.append(bytes(audio.data))
                assert audio.mime_type == "audio/pcm;rate=16000"
            if audio_stream_end:
                self.ended = True

        async def receive(self):
            yield SimpleNamespace(
                usage_metadata=None,
                server_content=SimpleNamespace(
                    input_transcription=SimpleNamespace(text="where is order 3", finished=True),
                    interim_input_transcription=None,
                ),
            )
            while not self.closed:
                if self.ended and len(self.audio) >= 3 and not self.second:
                    self.second = True
                    yield SimpleNamespace(
                        usage_metadata=None,
                        server_content=SimpleNamespace(
                            input_transcription=SimpleNamespace(text="and the total", finished=True),
                            interim_input_transcription=None,
                        ),
                    )
                await asyncio.sleep(0.01)

    class Connect:
        def __init__(self, session: Session) -> None:
            self.session = session

        async def __aenter__(self):
            events.append("enter")
            return self.session

        async def __aexit__(self, *args):
            self.session.closed = True
            events.append("exit")
            return False

    session = Session()

    class Live:
        @staticmethod
        def connect(model, config):
            events.append("connect")
            assert model == "gemini-3.1-flash-live-preview"
            assert config.response_modalities == [types.Modality.AUDIO]
            assert config.input_audio_transcription is not None
            assert config.output_audio_transcription is None
            instruction = config.system_instruction
            if hasattr(instruction, "parts"):
                instruction = instruction.parts[0].text
            assert "Do not speak" in str(instruction)
            return Connect(session)

    class Models:
        async def generate_content(self, **kwargs):
            generated["n"] += 1
            raise AssertionError("generate_content must not run for a live utterance")

    class Aio:
        live = Live()
        models = Models()

    class Client:
        aio = Aio()

    monkeypatch.setattr(stt, "_client", lambda: Client())
    frame_a = b"\x00\x01" * 8
    frame_b = b"\x02\x03" * 8

    async def run() -> None:
        utter = stt.open_utterance()
        await utter.open()
        await utter.send(frame_a)
        await utter.send(frame_b)
        seen: list[str] = []

        async def consume() -> None:
            async for text in utter.updates():
                seen.append(text)

        reader = asyncio.create_task(consume())
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.01)
        assert seen == ["where is order 3"]
        assert "exit" not in events
        text, _usage, nbytes = await utter.flush(reader)
        assert text == "where is order 3"
        assert nbytes == len(frame_a) + len(frame_b)
        assert "exit" not in events
        frame_c = b"\x04\x05" * 8
        await utter.send(frame_c)
        for _ in range(50):
            if "and the total" in seen:
                break
            await asyncio.sleep(0.01)
        second, _usage, nbytes = await utter.flush(reader)
        assert second == "and the total"
        assert nbytes == len(frame_c)
        assert session.audio == [frame_a, frame_b, frame_c]
        assert events.count("connect") == 1
        assert "exit" not in events
        await utter.close()
        assert events.count("exit") == 1
        assert generated["n"] == 0

    asyncio.run(run())


def test_live_session_flush_waits_for_final_after_interim_and_caps_empty_drain(monkeypatch) -> None:
    import asyncio
    import time
    from types import SimpleNamespace

    from src.voice import stt

    class Session:
        def __init__(self) -> None:
            self.ended = False
            self.closed = False

        async def send_realtime_input(self, *, audio=None, audio_stream_end=None, **kwargs):
            if audio_stream_end:
                self.ended = True

        async def receive(self):
            yield SimpleNamespace(
                usage_metadata=None,
                server_content=SimpleNamespace(
                    input_transcription=None,
                    interim_input_transcription=SimpleNamespace(text="where is"),
                ),
            )
            while not self.closed:
                if self.ended:
                    self.ended = False
                    await asyncio.sleep(0.03)
                    yield SimpleNamespace(
                        usage_metadata=None,
                        server_content=SimpleNamespace(
                            input_transcription=SimpleNamespace(text="where is order 5", finished=True),
                            interim_input_transcription=None,
                        ),
                    )
                    break
                await asyncio.sleep(0.01)
            while not self.closed:
                await asyncio.sleep(0.01)

    class Connect:
        def __init__(self, session: Session) -> None:
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *args):
            self.session.closed = True
            return False

    session = Session()

    class Live:
        @staticmethod
        def connect(model, config):
            return Connect(session)

    class Aio:
        live = Live()

    class Client:
        aio = Aio()

    monkeypatch.setattr(stt, "_client", lambda: Client())

    async def run() -> None:
        utter = stt.open_utterance()
        await utter.open()
        reader = asyncio.create_task(self_consume(utter))
        # Zero-byte flush returns immediately.
        t0 = time.perf_counter()
        empty_text, _u, empty_bytes = await utter.flush(reader)
        assert empty_text == ""
        assert empty_bytes == 0
        assert (time.perf_counter() - t0) < 0.05

        await utter.send(b"\x00\x01" * 16)
        await asyncio.sleep(0.02)
        # Interim "where is" is present; flush waits for final "where is order 5".
        text, _u, nbytes = await utter.flush(reader)
        assert text == "where is order 5"
        assert nbytes == 32

        # Empty flush with audio bytes drains within ~250 ms (well under 0.6 s).
        await utter.send(b"\x00\x00" * 16)
        t1 = time.perf_counter()
        quiet_text, _u, quiet_bytes = await utter.flush(reader)
        elapsed = time.perf_counter() - t1
        assert quiet_text == ""
        assert quiet_bytes == 32
        assert elapsed < 0.6
        await utter.close()
        reader.cancel()

    async def self_consume(utter) -> None:
        async for _ in utter.updates():
            pass

    asyncio.run(run())


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


def test_take_complete_splits_on_clause_and_newline_headers() -> None:
    from src.voice.router import _take_complete

    head, tail = _take_complete("Here are your recent orders:\n- Order 5 is processing")
    assert head.strip() == "Here are your recent orders:"
    assert tail == "- Order 5 is processing"
    short_head, short_tail = _take_complete("Order: 5")
    assert short_head == ""
    assert short_tail == "Order: 5"


def test_cost_usd_is_non_negative() -> None:
    quiet = usd("tts", 0, 0)
    spoken = usd("tts", 1_000, 2_000)
    assert quiet >= 0
    assert spoken >= quiet
    assert isinstance(spoken, float)


def test_cost_estimate_tokens_uses_about_four_characters() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("12345678") == 2


def test_live_cost_uses_metadata_or_the_forwarded_audio() -> None:
    from src.voice.cost import stt_charge

    measured = SimpleNamespace(prompt_token_count=183, candidates_token_count=4)
    assert stt_charge(measured, 32000 * 4) == (183, 4)
    live = SimpleNamespace(prompt_token_count=50, response_token_count=2)
    assert usage_tokens(live) == (50, 2)
    four_seconds = stt_charge(None, 32000 * 4)
    assert four_seconds == (100, 0)
    assert usd("stt", *four_seconds) == usd("stt", 100, 0)
    assert stt_charge(None, 0) == (0, 0)


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

    _install_scripted(monkeypatch, _TRANSCRIPTS)
    app = FastAPI()
    app.include_router(
        router.make_voice_router(runners={"shopper": object()}, pipeline=pipeline)
    )
    return app


_TRANSCRIPTS = ["status of my order", "and a summary"]


class _ScriptedUtterance:
    def __init__(self, texts: list[str], hook=None) -> None:
        import asyncio
        from types import SimpleNamespace

        self.texts = list(texts)
        self.hook = hook
        self.pcm_bytes = 0
        self.usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=4)
        self._q: asyncio.Queue = asyncio.Queue()
        self._phrase = 0
        self.closed = False

    def _current_text(self) -> str:
        if not self.texts:
            return ""
        return self.texts[min(self._phrase, len(self.texts) - 1)]

    async def open(self) -> None:
        return None

    async def send(self, pcm: bytes) -> None:
        starting = self.pcm_bytes == 0
        self.pcm_bytes += len(pcm)
        if starting:
            if self.hook:
                self.hook(self._phrase + 1)
            await self._q.put(self._current_text())

    async def updates(self):
        while True:
            item = await self._q.get()
            if item is None:
                return
            if item:
                yield item

    async def flush(self, reader=None):
        if self.pcm_bytes == 0:
            return "", self.usage, 0
        text = self._current_text()
        nbytes = self.pcm_bytes
        self._phrase += 1
        self.pcm_bytes = 0
        return text, self.usage, nbytes

    async def finish(self, reader=None):
        result = await self.flush(reader)
        await self.close()
        return result

    async def close(self) -> None:
        self.closed = True
        await self._q.put(None)


def _install_scripted(monkeypatch, texts: list[str], hook=None):
    from src.voice import router

    calls = {"n": 0, "sessions": []}

    def open_utterance():
        calls["n"] += 1
        session = _ScriptedUtterance(texts, hook)
        calls["sessions"].append(session)
        return session

    monkeypatch.setattr(router, "open_utterance", open_utterance)
    return calls


def _end(ws) -> None:
    import json

    ws.send_text(json.dumps({"type": "utterance_end"}))


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
            _end(ws)
            ws.send_bytes(pcm)
            _end(ws)
            events = _events(ws)

    assert queries == ["status of my order and a summary"]
    assert any(event.get("type") == "partial_transcript" for event in events)
    assert events[-1] == {"type": "turn_end"}


def test_commit_utterance_end_starts_turn_immediately_without_settle(monkeypatch) -> None:
    import json
    import time

    from fastapi.testclient import TestClient

    from src.voice import router

    settled = {"called": 0}

    def slow_settle(mode):
        settled["called"] += 1
        return 10000

    monkeypatch.setattr(router, "settle_ms", slow_settle)
    queries: list[str] = []

    async def pipeline(runner, user_id, text, **kwargs):
        queries.append(text)
        yield {"type": "final", "blocked": True, "response": "blocked", "stage": "judge"}

    _install_scripted(monkeypatch, ["where is order 5"])
    app = FastAPI_app(pipeline)
    t0 = time.perf_counter()
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_text(json.dumps({"type": "utterance_end", "commit": True}))
            events = _events(ws)
    elapsed = time.perf_counter() - t0
    assert queries == ["where is order 5"]
    assert settled["called"] == 0
    assert elapsed < 1.0
    assert events[-1] == {"type": "turn_end"}


def test_empty_flush_does_not_start_settle(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.voice import router

    queries: list[str] = []

    async def pipeline(runner, user_id, text, **kwargs):
        queries.append(text)
        yield {"type": "final", "blocked": True, "response": "blocked", "stage": "judge"}

    calls = _install_scripted(monkeypatch, ["", "where is my order"])
    monkeypatch.setattr(router, "settle_ms", lambda mode: 20)
    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 80)
            _end(ws)
            ws.send_bytes(b"\x02\x03" * 80)
            _end(ws)
            events = _events(ws)

    steps = [event for event in events if event.get("type") == "step" and event.get("key") == "stt"]
    assert len(steps) == 1
    assert "where is my order" in steps[0]["detail"]
    assert "no speech" not in steps[0]["detail"]
    assert queries == ["where is my order"]
    assert calls["n"] == 1


def test_live_socket_emits_partial_before_utterance_end(monkeypatch) -> None:
    import json

    from fastapi.testclient import TestClient

    from src.voice import router

    async def pipeline(runner, user_id, text, **kwargs):
        yield {"type": "final", "blocked": True, "response": "blocked", "stage": "judge"}

    monkeypatch.setattr(router, "settle_ms", lambda mode: 5000)
    _install_scripted(monkeypatch, ["where is my order"])
    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 80)
            seen = None
            for _ in range(10):
                event = json.loads(ws.receive()["text"])
                if event.get("type") == "partial_transcript":
                    seen = event
                    break
            assert seen is not None
            assert seen["text"] == "where is my order"
            _end(ws)


def test_interrupt_emits_turn_end_interrupted(monkeypatch) -> None:
    import asyncio
    import json

    from fastapi.testclient import TestClient

    from src.voice import router

    monkeypatch.setattr(router, "_SETTLE_MS", 30)
    _install_scripted(monkeypatch, ["where is my order"])

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        yield b"\x00\x01" * 200
        await asyncio.sleep(30)

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
            _end(ws)
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


def _patch_voice(monkeypatch, pipeline, *, mask: str = "true", stream: str = "true", mask_text=None):
    from fastapi import FastAPI

    from src.voice import router

    monkeypatch.setenv("MASK", mask)
    monkeypatch.setenv("AGENT_RESPONSE_STREAM", stream)
    router.refresh_flags()

    _install_scripted(monkeypatch, ["where is my order"])
    app = FastAPI()
    app.include_router(
        router.make_voice_router(
            runners={"shopper": object()},
            pipeline=pipeline,
            mask_text=mask_text,
        )
    )
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
            _end(ws)
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
    assert flags[0]["judge_if_flagged"] is False
    assert flags[0]["mask"] is False
    assert flags[0]["stream"] is True


def test_demo_mode_explain_speaks_each_masked_sentence(monkeypatch) -> None:
    import asyncio
    import json
    import threading

    from fastapi.testclient import TestClient

    spoken: list[str] = []
    shown: list[str] = []
    flags: list[dict] = []
    settled: list[str] = []
    gate = threading.Event()
    first = "Your order is processing. "
    full = first + "The hub ships Friday."

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        spoken.append(text)
        yield b"\x00\x01" * 80

    async def mask_text(text: str) -> tuple[str, str]:
        return text.replace("order", "item"), "PII masked in the response"

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
        yield {"type": "delta", "text": first}
        await asyncio.to_thread(gate.wait, 5)
        yield {"type": "delta", "text": full}
        yield {"type": "final", "blocked": False, "response": full}

    router, app = _patch_voice(monkeypatch, pipeline, mask_text=mask_text)

    def fast_settle(mode):
        settled.append(mode)
        return 20

    monkeypatch.setattr(router, "settle_ms", fast_settle)
    monkeypatch.setattr(router, "synthesize_stream", synthesize_stream)
    assert router.STREAM_ENABLED is False

    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            _end(ws)
            saw_audio = False
            keys: list[str] = []
            for _ in range(40):
                message = ws.receive()
                if message.get("bytes") is not None:
                    saw_audio = True
                    break
                if message.get("text"):
                    event = json.loads(message["text"])
                    if event.get("type") == "response_text":
                        shown.append(event["text"])
                    if event.get("key"):
                        keys.append(event["key"])
            assert saw_audio
            assert spoken
            assert spoken[0] == "Your item is processing."
            assert "Friday" not in "".join(spoken)
            assert shown
            assert "order" not in shown[-1]
            assert "sanitize" in keys
            assert "mask" in keys
            gate.set()
            events = _events(ws)

    assert settled == ["explain"]
    assert flags[0]["judge"] is True
    assert flags[0]["judge_if_flagged"] is False
    assert flags[0]["mask"] is True
    assert flags[0]["stream"] is True
    assert router.STREAM_ENABLED is False
    assert "judge" in keys
    assert "Friday" in "".join(spoken)


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
            _end(ws)
            assert started.wait(3)
            ws.send_text(json.dumps({"type": "mode", "mode": "quick"}))
            release.set()
            assert _events(ws)[-1]["type"] == "turn_end"
            ws.send_bytes(b"\x00\x01" * 160)
            _end(ws)
            assert _events(ws)[-1]["type"] == "turn_end"

    assert flags[0]["judge"] is True
    assert flags[0]["mask"] is True
    assert flags[0]["stream"] is True
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


def test_ui_streams_frames_and_ends_the_utterance() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    assert "pcm.buffer" not in source
    start = source.index("function sendFrame(")
    end = source.index("function onFrame(", start)
    script = "\n".join(
        [
            "let speaking = false;",
            "let voiceOn = true;",
            "let agentSpeaking = false;",
            "let frames = [1];",
            "let silentFrames = 3;",
            "const sent = [];",
            "const ws = { readyState: 1, send(payload) { sent.push(payload); } };",
            "function setVoiceStatus() {}",
            source[start:end],
            "sendFrame(new Int16Array([1, 2]));",
            "const whileListening = sent.slice();",
            "speaking = true;",
            "const frame = new Int16Array([3, 4]);",
            "sendFrame(frame);",
            "endUtterance();",
            "console.log(JSON.stringify({ whileListening, sent, speaking, frames, silentFrames }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["whileListening"] == []
    assert result["sent"][-1] == '{"type":"utterance_end"}'
    assert len(result["sent"]) == 2
    assert result["speaking"] is False
    assert result["frames"] == []


def test_ptt_hold_and_release_commits_immediately() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    start = source.index("function floatToPcm(")
    end = source.index("async function startCapture(", start)
    script = "\n".join(
        [
            "const VAD_RMS = 0.02;",
            "const BARGE_RMS = 0.12;",
            "const BARGE_FRAMES = 3;",
            "const ONSET_FRAMES = 2;",
            "const END_SILENCE_MS = 1500;",
            "const PLAYBACK_GRACE_MS = 400;",
            "const PREROLL_FRAMES = 3;",
            "const CAPTURE_RATE = 16000;",
            "let speaking = false;",
            "let voiceOn = true;",
            "let pttActive = false;",
            "let pttDownAt = 0;",
            "let pttReleased = false;",
            "let pttPaused = false;",
            "let agentSpeaking = false;",
            "let muted = false;",
            "let frames = [];",
            "let preroll = [];",
            "let silentFrames = 0;",
            "let onsetCount = 0;",
            "let lastPlayStart = 0;",
            "const captureCtx = { sampleRate: 16000 };",
            "const sent = [];",
            "const ws = { readyState: 1, send(payload) { sent.push(payload); } };",
            "function now() { return 1000; }",
            "function setVoiceStatus() {}",
            "function stopPlayback() { agentSpeaking = false; }",
            source[start:end],
            "beginPtt();",
            "const quiet = new Float32Array(1600).fill(0.0);",
            "for (let i = 0; i < 20; i++) onFrame(quiet);",
            "const stillSpeakingDuringHold = speaking;",
            "releasePtt();",
            "const countAtRelease = sent.length;",
            "const loud = new Float32Array(1600).fill(0.5);",
            "for (let i = 0; i < 10; i++) onFrame(loud);",
            "console.log(JSON.stringify({ stillSpeakingDuringHold, speakingAfterRelease: speaking, pttPaused, countAtRelease, countAfterLoud: sent.length, lastSent: sent[sent.length - 1], count: sent.length }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["stillSpeakingDuringHold"] is True
    assert result["speakingAfterRelease"] is False
    assert result["pttPaused"] is True
    assert result["countAfterLoud"] == result["countAtRelease"]
    assert json.loads(result["lastSent"]) == {"type": "utterance_end", "commit": True}
    assert result["count"] >= 21


def test_ptt_release_tail_captures_trailing_speech_for_one_second() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    assert "const PTT_RELEASE_TAIL_MS = 1000;" in source
    start = source.index("function floatToPcm(")
    end = source.index("async function startCapture(", start)
    script = "\n".join(
        [
            "const VAD_RMS = 0.02;",
            "const BARGE_RMS = 0.12;",
            "const BARGE_FRAMES = 3;",
            "const ONSET_FRAMES = 2;",
            "const END_SILENCE_MS = 1500;",
            "const PTT_RELEASE_TAIL_MS = 1000;",
            "const PLAYBACK_GRACE_MS = 400;",
            "const PREROLL_FRAMES = 3;",
            "const CAPTURE_RATE = 16000;",
            "let speaking = false;",
            "let voiceOn = true;",
            "let pttActive = false;",
            "let pttDownAt = 0;",
            "let pttReleased = false;",
            "let pttPaused = false;",
            "let pttTailTimer = null;",
            "let agentSpeaking = false;",
            "let muted = false;",
            "let frames = [];",
            "let preroll = [];",
            "let silentFrames = 0;",
            "let onsetCount = 0;",
            "let lastPlayStart = 0;",
            "const captureCtx = { sampleRate: 16000 };",
            "const sent = [];",
            "const statuses = [];",
            "let scheduledFn = null;",
            "let scheduledMs = 0;",
            "function setTimeout(fn, ms) { scheduledFn = fn; scheduledMs = ms; return 42; }",
            "function clearTimeout() { scheduledFn = null; }",
            "const ws = { readyState: 1, send(payload) { sent.push(payload); } };",
            "function now() { return 1000; }",
            "function setVoiceStatus(t) { statuses.push({ text: t, live: voiceOn && !pttPaused && !pttTailTimer }); }",
            "function stopPlayback() { agentSpeaking = false; }",
            source[start:end],
            "beginPtt();",
            "const frame = new Float32Array(1600).fill(0.2);",
            "onFrame(frame);",
            "const beforeRelease = { count: sent.length, live: statuses[statuses.length - 1].live };",
            "releasePtt();",
            "const rightAfterRelease = { pttActive, pttPaused, speaking, scheduledMs, live: statuses[statuses.length - 1].live, count: sent.length };",
            "// Trailing frames during the 1.0s tail are still captured",
            "onFrame(frame);",
            "onFrame(frame);",
            "const countDuringTail = sent.length;",
            "// After 1.0s tail expires, utterance is committed and mic pauses",
            "scheduledFn();",
            "onFrame(frame);",
            "const afterTail = { pttPaused, speaking, count: sent.length, lastSent: sent[sent.length - 1] };",
            "console.log(JSON.stringify({ beforeRelease, rightAfterRelease, countDuringTail, afterTail }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["beforeRelease"]["live"] is True
    assert result["rightAfterRelease"] == {
        "pttActive": False,
        "pttPaused": False,
        "speaking": True,
        "scheduledMs": 1000,
        "live": False,
        "count": 1,
    }
    assert result["countDuringTail"] == 3
    assert result["afterTail"]["pttPaused"] is True
    assert result["afterTail"]["speaking"] is False
    assert result["afterTail"]["count"] == 4
    assert json.loads(result["afterTail"]["lastSent"]) == {"type": "utterance_end", "commit": True}


def test_mute_unmute_and_mic_click_off() -> None:
    import json
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = (root / "src" / "voice" / "ui.js").read_text(encoding="utf-8")
    html = (root / "src" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'holdBtn.textContent = "Mute";' in source
    assert 'holdBtn.textContent = "Unmute";' in source
    assert 'holdBtn.style.display = "inline-block"' not in source
    assert "Click and hold the Mic button" in source
    assert "Click and hold the Mic button" in html
    start = source.index("function toggleHold(")
    end = source.index("window.addEventListener(\"keydown\"", start)
    script = "\n".join(
        [
            "var USER = 'alice.jones@example.com';",
            "let voiceOn = true;",
            "let speaking = false;",
            "let pttActive = false;",
            "let pttDownAt = 0;",
            "let pttReleased = false;",
            "let pttPaused = true;",
            "let micPressHeld = false;",
            "let tabHeld = false;",
            "let startingVoice = null;",
            "let agentSpeaking = false;",
            "let turnRunning = true;",
            "let muted = false;",
            "let frames = [];",
            "let preroll = [];",
            "let silentFrames = 0;",
            "let onsetCount = 0;",
            "let beganCount = 0;",
            "let committedCount = 0;",
            "const holdBtn = { textContent: 'Mute', title: '', style: { display: 'none' }, classList: { add() {}, remove() {} } };",
            "const micBtn = {};",
            "const window = { addEventListener() {} };",
            "function now() { return 1000; }",
            "function setVoiceStatus() {}",
            "function beginPtt() { beganCount += 1; pttPaused = false; pttActive = true; speaking = true; turnRunning = false; }",
            "function releasePtt() { pttActive = false; speaking = false; pttPaused = true; pttReleased = true; committedCount += 1; }",
            "function endUtterance(commit) { speaking = false; if (commit) committedCount += 1; }",
            "function stopVoice() { voiceOn = false; }",
            "function startVoice() { return Promise.resolve(); }",
            source[start:end],
            "// 1. Press mic down while agent is running -> interrupts and starts listening while held",
            "micBtn.onmousedown();",
            "const whileHeld = { beganCount, speaking, pttPaused, pttActive, holdDisplay: holdBtn.style.display };",
            "// 2. Release mic button (even immediately) -> turns mic off and commits utterance",
            "micBtn.onmouseup();",
            "micBtn.onclick();",
            "const afterRelease = { speaking, pttPaused, pttActive, committedCount, holdDisplay: holdBtn.style.display };",
            "console.log(JSON.stringify({ whileHeld, afterRelease }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["whileHeld"] == {
        "beganCount": 1,
        "speaking": True,
        "pttPaused": False,
        "pttActive": True,
        "holdDisplay": "none",
    }
    assert result["afterRelease"] == {
        "speaking": False,
        "pttPaused": True,
        "pttActive": False,
        "committedCount": 1,
        "holdDisplay": "none",
    }


def test_interrupt_while_thinking_combines_questions_and_while_speaking_starts_new_question(
    monkeypatch,
) -> None:
    import asyncio
    import json
    import threading

    from fastapi.testclient import TestClient

    from src.voice import router

    thinking_started = threading.Event()
    speaking_started = threading.Event()
    hold_turn = threading.Event()
    queries: list[str] = []

    async def synthesize_stream(text: str, usage_out: dict | None = None):
        yield b"\x00\x01" * 80

    async def pipeline(runner, user_id, text, **kwargs):
        queries.append(text)
        if len(queries) == 1:
            # Turn 1: thinking phase (no delta yet) when user interrupts
            thinking_started.set()
            await asyncio.to_thread(hold_turn.wait, 5)
            yield {"type": "final", "blocked": False, "response": "unreachable"}
            return
        if len(queries) == 2:
            # Turn 2: combined question; emits delta (answer started) before user interrupts
            yield {"type": "delta", "text": "Your order is on the way. "}
            speaking_started.set()
            await asyncio.to_thread(hold_turn.wait, 5)
            yield {"type": "final", "blocked": False, "response": "Your order is on the way."}
            return
        # Turn 3: fresh question after mid-answer interrupt
        yield {"type": "delta", "text": "Returns are free within 30 days."}
        yield {"type": "final", "blocked": False, "response": "Returns are free within 30 days."}

    _install_scripted(
        monkeypatch,
        [
            "where is my order",
            "and change the address",
            "what is your return policy",
        ],
    )
    monkeypatch.setattr(router, "settle_ms", lambda mode: 20)
    monkeypatch.setattr(router, "synthesize_stream", synthesize_stream)
    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            # 1. First question committed
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_text(json.dumps({"type": "utterance_end", "commit": True}))
            assert thinking_started.wait(3)
            # Interrupt while still thinking (before any delta/answer)
            ws.send_text(json.dumps({"type": "interrupt"}))
            ev = _events(ws)
            assert ev[-1] == {"type": "turn_end", "reason": "interrupted"}

            # 2. Ask additional question -> should combine with first question!
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_text(json.dumps({"type": "utterance_end", "commit": True}))
            assert speaking_started.wait(3)
            # Interrupt after answer already started streaming
            ws.send_text(json.dumps({"type": "interrupt"}))
            ev2 = _events(ws)
            assert ev2[-1] == {"type": "turn_end", "reason": "interrupted"}

            # 3. Ask next question -> should NOT include previous combined question!
            ws.send_bytes(b"\x00\x01" * 160)
            ws.send_text(json.dumps({"type": "utterance_end", "commit": True}))
            ev3 = _events(ws)
            assert ev3[-1] == {"type": "turn_end"}

    assert queries == [
        "where is my order",
        "where is my order and change the address",
        "what is your return policy",
    ]


def test_barge_gate_holds_frames_until_clear_speech() -> None:
    import json
    import subprocess
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    assert "const VAD_RMS = 0.02;" in source
    assert "const BARGE_RMS = 0.12;" in source
    start = source.index("  function floatToPcm(")
    end = source.index("  async function startCapture(", start)
    script = "\n".join(
        [
            "const VAD_RMS = 0.02;",
            "const BARGE_RMS = 0.12;",
            "const BARGE_FRAMES = 3;",
            "const ONSET_FRAMES = 2;",
            "const PLAYBACK_GRACE_MS = 400;",
            "const PREROLL_FRAMES = 3;",
            "const CAPTURE_RATE = 16000;",
            "let speaking = false;",
            "let voiceOn = true;",
            "let agentSpeaking = true;",
            "let muted = false;",
            "let frames = [];",
            "let preroll = [];",
            "let silentFrames = 0;",
            "let onsetCount = 0;",
            "let lastPlayStart = 0;",
            "const captureCtx = { sampleRate: 16000 };",
            "const sent = [];",
            "const ws = { readyState: 1, send(payload) { sent.push(payload); } };",
            "function now() { return 1000; }",
            "function setVoiceStatus() {}",
            "function stopPlayback() { agentSpeaking = false; }",
            source[start:end],
            "const quiet = new Float32Array(160).fill(0.02);",
            "onFrame(quiet);",
            "const whileSpeaking = sent.length;",
            "const loud = new Float32Array(160).fill(0.5);",
            "onFrame(loud);",
            "onFrame(loud);",
            "const beforeThird = sent.length;",
            "onFrame(loud);",
            "console.log(JSON.stringify({ whileSpeaking, beforeThird, sent: sent.map((item) => typeof item === 'string' ? item : 'audio') }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["whileSpeaking"] == 0
    assert result["beforeThird"] == 0
    assert result["sent"][0] == '{"type":"interrupt"}'
    assert "audio" in result["sent"][1:]


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


def test_during_turn_drops_audio_until_interrupt(monkeypatch) -> None:
    import asyncio
    import json
    import threading

    from fastapi.testclient import TestClient

    from src.voice import router

    started = threading.Event()
    accepted = threading.Event()
    release = threading.Event()
    queries: list[str] = []

    def heard(index: int) -> None:
        if index >= 2:
            accepted.set()

    async def pipeline(runner, user_id, text, **kwargs):
        queries.append(text)
        started.set()
        await asyncio.to_thread(release.wait, 5)
        yield {"type": "final", "blocked": True, "response": "blocked", "stage": "judge"}

    calls = _install_scripted(monkeypatch, ["where is my order"], heard)
    monkeypatch.setattr(router, "settle_ms", lambda mode: 20)
    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            _end(ws)
            assert started.wait(3)
            session = calls["sessions"][0]
            ws.send_bytes(b"\x02\x03" * 160)
            assert accepted.wait(0.4) is False
            assert session.pcm_bytes == 0
            assert calls["n"] == 1
            ws.send_text(json.dumps({"type": "interrupt"}))
            ws.send_bytes(b"\x04\x05" * 80)
            assert accepted.wait(2)
            assert calls["n"] == 1
            assert session is calls["sessions"][0]
            assert session.pcm_bytes > 0
            release.set()
            events = _events(ws)

    assert queries == ["where is my order"]
    assert events[-1]["type"] == "turn_end"


def test_more_speech_does_not_cancel_the_answer_in_progress(monkeypatch) -> None:
    import asyncio
    import threading

    from fastapi.testclient import TestClient

    from src.voice import router

    started = threading.Event()
    release = threading.Event()
    queries: list[str] = []

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

    calls = _install_scripted(monkeypatch, ["hi hello", "how are you"])
    monkeypatch.setattr(router, "settle_ms", lambda mode: 20)
    app = FastAPI_app(pipeline)
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws?user_id=shopper") as ws:
            ws.send_bytes(b"\x00\x01" * 160)
            _end(ws)
            assert started.wait(3)
            ws.send_bytes(b"\x00\x01" * 160)
            assert calls["n"] == 1
            assert calls["sessions"][0].pcm_bytes == 0
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
