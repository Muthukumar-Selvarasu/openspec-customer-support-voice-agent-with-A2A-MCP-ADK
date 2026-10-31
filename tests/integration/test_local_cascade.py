"""Live local cascade against the Podman stack on 127.0.0.1:8000.

Text and voice tests skip when GOOGLE_API_KEY or MEM0_API_KEY is unset.
The voice test also skips when no 16 kHz speech PCM can be produced.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000"
SHOPPER = "alice.jones@example.com"
PASSWORD = "alice"
UTTERANCE = "What is the status of my latest order?"


def _require_live_keys() -> None:
    load_dotenv(ROOT / ".env")
    missing = [
        name
        for name in ("GOOGLE_API_KEY", "MEM0_API_KEY")
        if not os.getenv(name, "").strip()
    ]
    if not missing:
        return
    if len(missing) == 1:
        pytest.skip(f"{missing[0]} is unset")
    pytest.skip(f"{' and '.join(missing)} are unset")


def _speech_pcm() -> bytes | None:
    """Synthesize one 16 kHz mono utterance. None when no local speaker tool exists."""
    say = shutil.which("say")
    if say is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "utterance.wav"
        proc = subprocess.run(
            [say, "-o", str(wav_path), "--data-format=LEI16@16000", UTTERANCE],
            check=False,
            capture_output=True,
        )
        if proc.returncode != 0 or not wav_path.is_file():
            return None
        try:
            with wave.open(str(wav_path), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                    return None
                if wav.getframerate() != 16000:
                    return None
                frames = wav.readframes(wav.getnframes())
        except wave.Error:
            return None
    return frames or None


def test_text_turn_runs_sanitizer_judge_agent_and_masker() -> None:
    _require_live_keys()
    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        login = client.post("/api/login", json={"email": SHOPPER, "password": PASSWORD})
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["ok"] is True
        user_id = body["user_id"]
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"user_id": user_id, "message": UTTERANCE},
        ) as response:
            assert response.status_code == 200, response.read()
            events = [
                json.loads(line)
                for line in response.iter_lines()
                if line.strip()
            ]
    stages = [event["key"] for event in events if event.get("type") == "stage"]
    assert stages[:4] == ["sanitize", "judge", "agent", "mask"], stages
    final = next(event for event in events if event.get("type") == "final")
    assert final["blocked"] is False
    assert str(final["response"]).strip()


@pytest.mark.asyncio
async def test_voice_turn_streams_tts_pcm_after_settle() -> None:
    _require_live_keys()
    pcm = _speech_pcm()
    if not pcm:
        pytest.skip("mic/browser unavailable: no 16 kHz speech PCM source")

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        login = client.post("/api/login", json={"email": SHOPPER, "password": PASSWORD})
        assert login.status_code == 200, login.text
        user_id = login.json()["user_id"]

    import aiohttp

    audio = bytearray()
    events: list[dict] = []
    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(
            BASE + "/voice/ws",
            params={"user_id": user_id},
            timeout=timeout,
        ) as ws:
            await ws.send_bytes(pcm)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 170
            while loop.time() < deadline:
                remaining = max(1.0, deadline - loop.time())
                msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
                if msg.type == aiohttp.WSMsgType.BINARY:
                    audio.extend(msg.data)
                    continue
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                event = json.loads(msg.data)
                events.append(event)
                if event.get("type") == "turn_end":
                    break

    assert any(event.get("type") == "partial_transcript" for event in events), events
    assert any(
        event.get("type") == "stage" and event.get("key") == "judge" for event in events
    ), events
    assert audio, "expected TTS PCM bytes"
    turn_end = next(event for event in events if event.get("type") == "turn_end")
    assert turn_end.get("reason") != "interrupted"
