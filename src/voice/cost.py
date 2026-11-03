"""Per-turn USD estimates for STT, the text model, and TTS."""

from __future__ import annotations

import os


def _price(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


# USD per 1,000,000 tokens. Override with VOICE_PRICE_* for a different contract.
PRICES = {
    "stt_in": _price("VOICE_PRICE_STT_IN", 3.00),
    "stt_out": _price("VOICE_PRICE_STT_OUT", 4.50),
    "llm_in": _price("VOICE_PRICE_LLM_IN", 0.30),
    "llm_out": _price("VOICE_PRICE_LLM_OUT", 2.50),
    "tts_in": _price("VOICE_PRICE_TTS_IN", 1.00),
    "tts_out": _price("VOICE_PRICE_TTS_OUT", 20.00),
}


def usd(kind: str, tokens_in: int, tokens_out: int) -> float:
    """Dollar cost for ``kind`` (``stt``, ``llm``, or ``tts``)."""
    price_in = PRICES.get(f"{kind}_in", 0.0)
    price_out = PRICES.get(f"{kind}_out", 0.0)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def estimate_tokens(text: str) -> int:
    """Approximate tokens when the model does not report a count (~4 chars each)."""
    return max(1, len(text or "") // 4)


# Tokens per second of 16 kHz audio when a Live response omits usage metadata.
# At the $3.00 / 1M audio-token price this is about $0.0045 per minute.
_LIVE_AUDIO_TOKENS_PER_SEC = 25


def usage_tokens(usage) -> tuple[int, int]:
    """Return ``(prompt_tokens, output_tokens)`` from a usage object."""
    if not usage:
        return 0, 0
    tokens_in = getattr(usage, "prompt_token_count", 0) or 0
    tokens_out = (
        getattr(usage, "candidates_token_count", 0)
        or getattr(usage, "response_token_count", 0)
        or 0
    )
    return int(tokens_in), int(tokens_out)


def stt_charge(usage, pcm_bytes: int, sample_rate: int = 16000) -> tuple[int, int]:
    """Token counts for one live utterance.

    Usage metadata wins. Otherwise the count follows the PCM that was forwarded,
    so quiet listening time is not priced.
    """
    tokens_in, tokens_out = usage_tokens(usage)
    if tokens_in or tokens_out:
        return tokens_in, tokens_out
    if pcm_bytes <= 0 or sample_rate <= 0:
        return 0, 0
    seconds = pcm_bytes / (sample_rate * 2)
    return int(round(seconds * _LIVE_AUDIO_TOKENS_PER_SEC)), 0
