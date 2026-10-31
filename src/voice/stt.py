"""Speech-to-text: 16 kHz PCM in, plain transcript out."""

from __future__ import annotations

import io
import os
import re
import wave
from functools import lru_cache

from google import genai
from google.genai import types

from src.core.telemetry import ATTR, get_tracer

STT_MODEL = os.getenv("VOICE_STT_MODEL", "gemini-3.1-flash-lite")

_TRANSCRIBE_PROMPT = (
    "You are a speech-to-text engine. Transcribe ONLY the words the speaker says. "
    "Rules: output plain text of the spoken words and nothing else. Do NOT add "
    "timestamps, time codes, WEBVTT/SRT cue markers, speaker labels, brackets, or "
    "any commentary. If the audio contains no clear, intelligible speech, respond "
    "with exactly the token NO_SPEECH and nothing else."
)

_VTT_ARROW = re.compile(
    r"\d{1,2}:\d{2}(?::\d{2})?[.,:]?\d*\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?[.,:]?\d*"
)
_TIMECODE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?([.,:]\d{1,3})?\b")


def _clean(text: str) -> str:
    """Drop VTT cues, timecodes, and the NO_SPEECH token."""
    text = text.strip()
    if not text or text.upper() == "NO_SPEECH":
        return ""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.upper() == "WEBVTT":
            continue
        stripped = _VTT_ARROW.sub("", stripped)
        stripped = _TIMECODE.sub("", stripped).strip(" -\t")
        if stripped:
            lines.append(stripped)
    cleaned = " ".join(lines).strip()
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return ""
    return cleaned


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client()


def pcm16_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap mono 16-bit PCM in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


async def transcribe(pcm: bytes, sample_rate: int = 16000):
    """Return ``(transcript, usage_metadata)`` for one PCM utterance."""
    wav = pcm16_to_wav(pcm, sample_rate)
    with get_tracer().start_as_current_span("stt") as span:
        span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "VOICE")
        span.set_attribute("voice.stage", "stt")
        span.set_attribute("voice.model", STT_MODEL)
        response = await _client().aio.models.generate_content(
            model=STT_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=wav, mime_type="audio/wav"),
                        types.Part(text=_TRANSCRIBE_PROMPT),
                    ],
                )
            ],
        )
    return _clean(response.text or ""), getattr(response, "usage_metadata", None)
