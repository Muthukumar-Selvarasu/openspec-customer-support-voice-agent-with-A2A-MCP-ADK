"""Text-to-speech: reply text in, 24 kHz PCM out."""

from __future__ import annotations

import os
import re
from functools import lru_cache

from google import genai
from google.genai import types

from src.core.telemetry import ATTR, get_tracer

_SENTENCE = re.compile(r".*?[.!?…](?:\s+|$)", re.S)

TTS_MODEL = os.getenv("VOICE_TTS_MODEL", "gemini-3.8-flash-tts")
TTS_VOICE = os.getenv("VOICE_TTS_VOICE", "Kore")
TTS_SAMPLE_RATE = 24000


def split_sentences(text: str, min_len: int = 30) -> list[str]:
    """Chunk ``text`` on ``.!?…``. Keep the first chunk; merge later short ones."""
    text = (text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    position = 0
    for match in _SENTENCE.finditer(text):
        parts.append(match.group().strip())
        position = match.end()
    if position < len(text):
        tail = text[position:].strip()
        if tail:
            parts.append(tail)
    chunks: list[str] = []
    for part in parts:
        if chunks and len(chunks[-1]) < min_len:
            chunks[-1] = f"{chunks[-1]} {part}".strip()
        else:
            chunks.append(part)
    return [chunk for chunk in chunks if chunk]


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client()


def _audio_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
            )
        ),
    )


def _inline_audio(event) -> bytes | None:
    try:
        data = event.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError, TypeError):
        return None
    return data or None


async def synthesize_stream(text: str, usage_out: dict | None = None):
    """Yield 16-bit PCM chunks. Accumulate token totals into ``usage_out``."""
    if not text.strip():
        return
    with get_tracer().start_as_current_span("tts") as span:
        span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "VOICE")
        span.set_attribute("voice.stage", "tts")
        span.set_attribute("voice.model", TTS_MODEL)
        stream = await _client().aio.models.generate_content_stream(
            model=TTS_MODEL,
            contents=text,
            config=_audio_config(),
        )
        async for event in stream:
            data = _inline_audio(event)
            if data:
                yield data
            if usage_out is None:
                continue
            usage = getattr(event, "usage_metadata", None)
            if not usage:
                continue
            usage_out["in"] = max(
                usage_out.get("in", 0),
                getattr(usage, "prompt_token_count", 0) or 0,
            )
            usage_out["out"] = max(
                usage_out.get("out", 0),
                getattr(usage, "candidates_token_count", 0) or 0,
            )


async def synthesize(text: str) -> bytes:
    """Return the whole reply as one PCM blob."""
    if not text.strip():
        return b""
    response = await _client().aio.models.generate_content(
        model=TTS_MODEL,
        contents=text,
        config=_audio_config(),
    )
    part = response.candidates[0].content.parts[0]
    return part.inline_data.data or b""
