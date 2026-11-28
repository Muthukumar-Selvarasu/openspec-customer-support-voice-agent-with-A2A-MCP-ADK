"""Speech-to-text: 16 kHz PCM in, plain transcript out."""

from __future__ import annotations

import asyncio
from array import array
import io
import os
import re
import sys
import time
import wave
from functools import lru_cache

from google import genai
from google.genai import types

from src.core.telemetry import ATTR, get_tracer

LIVE_STT_MODEL = os.getenv("VOICE_STT_LIVE_MODEL", "gemini-3.1-flash-live-preview")
_PCM_MIME = "audio/pcm;rate=16000"

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


def live_model() -> str:
    """Live transcription model. Override with ``VOICE_STT_LIVE_MODEL``."""
    return os.getenv("VOICE_STT_LIVE_MODEL", LIVE_STT_MODEL)


# This model rejects TEXT (Live close 1007). AUDIO is required to connect.
# Model audio is ignored; the shopper still hears the TTS stage.
_LISTEN_ONLY = "Transcribe the caller. Do not speak, do not answer, and do not greet."


def _live_config() -> types.LiveConnectConfig:
    """Input transcription for a native-audio Live model."""
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=_LISTEN_ONLY,
    )


_FLUSH_DRAIN_SEC = 0.25
_INTERIM_FINALIZE_SEC = 0.7
_SPEECH_FLUSH_WAIT_SEC = 2.5
_SPEECH_PEAK_THRESHOLD = 200  # ~-44 dBFS on 16-bit PCM; distinguishes speech from silence
_END_SILENCE_PCM = b"\x00" * 32000  # 1.0 s of 16 kHz mono 16-bit PCM silence for Live VAD


def _pcm_has_speech(pcm: bytes) -> bool:
    """True when 16-bit little-endian PCM contains non-silent speech energy."""
    usable = len(pcm) - (len(pcm) % 2)
    if usable <= 0:
        return False
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    return max(abs(min(samples)), abs(max(samples))) >= _SPEECH_PEAK_THRESHOLD


class LiveUtterance:
    """One Live session for the whole time the microphone is on.

    ``updates`` yields transcript text as it arrives. ``flush`` ends the
    current phrase and leaves the connection open. ``close`` ends it.
    """

    def __init__(self) -> None:
        self.pcm_bytes = 0
        self.usage = None
        self._committed = ""
        self._interim = ""
        self._flushed = ""
        self._seq = 0
        self._last_rx = 0.0
        self._turn_done = False
        self._vad_active = False
        self._has_speech = False
        self._session = None
        self._cm = None
        self._span_cm = None
        self._closed = False

    def transcript(self) -> str:
        if self._interim:
            if self._interim.startswith(self._committed):
                return self._interim.strip()
            return f"{self._committed} {self._interim}".strip()
        return self._committed.strip()

    def _absorb(self, message) -> str | None:
        usage = getattr(message, "usage_metadata", None)
        if usage:
            self.usage = usage
        va = getattr(message, "voice_activity", None)
        if va is not None:
            va_type = str(getattr(va, "voice_activity_type", "") or "").upper()
            if "ACTIVITY_START" in va_type:
                self._vad_active = True
            elif "ACTIVITY_END" in va_type:
                self._vad_active = False
                self._turn_done = True
        content = getattr(message, "server_content", None)
        if content is None:
            return None
        if getattr(content, "turn_complete", False):
            self._turn_done = True
        interim = getattr(content, "interim_input_transcription", None)
        final = getattr(content, "input_transcription", None)
        changed = False
        if interim is not None and getattr(interim, "text", None):
            self._interim = str(interim.text).strip()
            self._seq += 1
            self._last_rx = time.monotonic()
            changed = True
        if final is not None and getattr(final, "text", None):
            self._take_final(str(final.text).strip())
            self._seq += 1
            self._last_rx = time.monotonic()
            if getattr(final, "finished", False):
                self._turn_done = True
            changed = True
        if not changed:
            return None
        text = self.transcript()
        return text or None

    def _take_final(self, piece: str) -> None:
        if not piece:
            return
        if piece.startswith(self._committed):
            self._committed = piece
        else:
            self._committed = f"{self._committed} {piece}".strip()
        self._interim = ""

    async def open(self) -> None:
        self._span_cm = get_tracer().start_as_current_span("stt")
        span = self._span_cm.__enter__()
        span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "VOICE")
        span.set_attribute("voice.stage", "stt")
        span.set_attribute("voice.model", live_model())
        self._cm = _client().aio.live.connect(model=live_model(), config=_live_config())
        self._session = await self._cm.__aenter__()

    async def send(self, pcm: bytes) -> None:
        self.pcm_bytes += len(pcm)
        if not self._has_speech and _pcm_has_speech(pcm):
            self._has_speech = True
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm, mime_type=_PCM_MIME)
        )

    async def updates(self):
        while not self._closed and self._session is not None:
            got_any = False
            async for message in self._session.receive():
                got_any = True
                heard = self._absorb(message)
                if heard:
                    yield heard
            if not got_any:
                break

    def _new_piece(self) -> str:
        full = _clean(self.transcript())
        if not full:
            return ""
        if self._flushed and full.startswith(self._flushed):
            return full[len(self._flushed) :].strip()
        if full == self._flushed:
            return ""
        return full

    async def _end_audio(self, *, pad_silence: bool = False) -> None:
        try:
            if self._session is not None:
                if pad_silence:
                    await self._session.send_realtime_input(
                        audio=types.Blob(data=_END_SILENCE_PCM, mime_type=_PCM_MIME)
                    )
                await self._session.send_realtime_input(audio_stream_end=True)
        except Exception:
            pass

    async def flush(self, reader: asyncio.Task | None = None):
        """End this phrase and return its transcript. The connection stays open."""
        phrase_bytes = self.pcm_bytes
        had_speech = self._has_speech or self._vad_active
        self.pcm_bytes = 0
        self._has_speech = False
        if phrase_bytes == 0 and not self._new_piece():
            usage = self.usage
            self.usage = None
            return "", usage, 0
        seq_before = self._seq
        self._turn_done = False
        pad_silence = phrase_bytes >= 3200 and had_speech and not self._new_piece()
        await self._end_audio(pad_silence=pad_silence)
        loop = asyncio.get_running_loop()
        start = loop.time()
        if self._new_piece():
            max_wait = _INTERIM_FINALIZE_SEC
        elif pad_silence:
            max_wait = _SPEECH_FLUSH_WAIT_SEC
        else:
            max_wait = _FLUSH_DRAIN_SEC
        deadline = start + max_wait
        while loop.time() < deadline:
            piece = self._new_piece()
            if piece:
                if deadline < start + _INTERIM_FINALIZE_SEC:
                    deadline = start + _INTERIM_FINALIZE_SEC
                if self._turn_done:
                    break
                if self._seq > seq_before and (time.monotonic() - self._last_rx) >= 0.2:
                    break
                if not self._interim and self._seq == seq_before and (loop.time() - start) >= 0.2:
                    break
            elif self._turn_done and not pad_silence:
                break
            if reader is not None and reader.done():
                break
            await asyncio.sleep(0.01)
        if self._interim:
            self._take_final(self._interim)
        piece = self._new_piece()
        full = _clean(self.transcript())
        if full:
            self._flushed = full
        usage = self.usage
        self.usage = None
        return piece, usage, phrase_bytes

    async def finish(self, reader: asyncio.Task | None = None):
        """Flush the current phrase and close. No second transcription."""
        result = await self.flush(reader)
        await self.close()
        return result

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        cm = self._cm
        self._cm = None
        self._session = None
        if cm is not None:
            await cm.__aexit__(None, None, None)
        if self._span_cm is not None:
            self._span_cm.__exit__(None, None, None)
            self._span_cm = None


def open_utterance() -> LiveUtterance:
    return LiveUtterance()
