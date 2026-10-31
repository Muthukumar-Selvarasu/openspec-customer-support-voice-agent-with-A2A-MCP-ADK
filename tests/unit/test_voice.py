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


@pytest.mark.skipif(not os.getenv("GOOGLE_API_KEY"), reason="GOOGLE_API_KEY is not set")
async def test_live_transcribe_when_api_key_set() -> None:
    from src.voice.stt import transcribe

    text, _usage = await transcribe(b"\x00\x00" * 1600)
    assert isinstance(text, str)
