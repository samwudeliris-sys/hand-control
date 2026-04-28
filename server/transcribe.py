"""OpenAI Whisper transcription.

Called once per utterance after the phone releases its hold. Takes the
raw ``audio/mp4`` (AAC) bytes that ``MediaRecorder`` produced on iOS
Safari and posts them to OpenAI's ``/v1/audio/transcriptions`` endpoint.

Why `httpx` and not the ``openai`` SDK: the SDK pulls in a few hundred
MB of transitive deps we don't need for a single multipart POST. FastAPI
already depends on httpx (via Starlette's TestClient), so adding it
explicitly is essentially free.

Environment:
    OPENAI_API_KEY         required; if missing we raise and the
                           server reports a friendly error to the phone
    HC_TRANSCRIBE_MODEL    default ``whisper-1``. Also useful:
                           ``gpt-4o-mini-transcribe`` (newer, often
                           cheaper + better quality for short clips).
    HC_TRANSCRIBE_LANGUAGE optional ISO-639-1 hint (e.g. ``en``).
                           Whisper auto-detects but a hint reduces
                           false detections on noisy short clips.
    HC_WHISPER_PROMPT      optional bias string (max 224 tokens for
                           whisper-1). Useful for steering toward
                           code-heavy vocabulary (e.g. ``"refactor,
                           async, useEffect, FastAPI"``).
"""

from __future__ import annotations

import os
from typing import Optional

import httpx


class TranscriptionError(RuntimeError):
    """Raised when we can't produce a transcription for the caller."""


_OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"

# Generous ceiling. Whisper caps uploads at 25 MB, which is ~25 min of
# AAC at 64 kbps — far longer than any realistic hold. We still enforce
# it client-side to fail fast with a clean error instead of a 413.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise TranscriptionError(
            "OPENAI_API_KEY is not set. Add it to ~/.hand-control.env or "
            "export it in the shell that runs ./run.sh."
        )
    return key


def _model() -> str:
    return os.environ.get("HC_TRANSCRIBE_MODEL", "whisper-1").strip() or "whisper-1"


def _language() -> Optional[str]:
    lang = os.environ.get("HC_TRANSCRIBE_LANGUAGE", "").strip()
    return lang or None


def _prompt() -> Optional[str]:
    p = os.environ.get("HC_WHISPER_PROMPT", "").strip()
    return p or None


async def transcribe_m4a(audio_bytes: bytes) -> str:
    """Transcribe a single utterance.

    Parameters
    ----------
    audio_bytes:
        Raw bytes of an ``audio/mp4`` (AAC-in-MP4) container, i.e. what
        ``MediaRecorder`` on iOS Safari produces with
        ``mimeType: 'audio/mp4'``. Whisper also happily accepts webm,
        wav, m4a, mp3 — we just declare ``.m4a`` as the filename so the
        server picks the right decoder.

    Returns
    -------
    The transcribed text, stripped of leading/trailing whitespace. An
    empty clip yields an empty string rather than an error.
    """
    if not audio_bytes:
        return ""
    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        raise TranscriptionError(
            f"Audio is too large ({len(audio_bytes) / 1024 / 1024:.1f} MB). "
            f"Whisper caps uploads at 25 MB."
        )

    headers = {"Authorization": f"Bearer {_api_key()}"}

    files = {
        # Filename matters — OpenAI uses the extension to pick the
        # decoder. ``.m4a`` matches AAC-in-MP4 from MediaRecorder.
        "file": ("utterance.m4a", audio_bytes, "audio/mp4"),
    }
    data: dict[str, str] = {
        "model": _model(),
        "response_format": "json",
    }
    lang = _language()
    if lang:
        data["language"] = lang
    prompt = _prompt()
    if prompt:
        data["prompt"] = prompt

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _OPENAI_URL,
                headers=headers,
                files=files,
                data=data,
            )
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Network error talking to OpenAI: {exc}") from exc

    if resp.status_code != 200:
        # OpenAI returns { "error": { "message": "..." } } on failures.
        msg = f"HTTP {resp.status_code}"
        try:
            err = resp.json().get("error", {})
            if isinstance(err, dict) and err.get("message"):
                msg = f"{msg}: {err['message']}"
        except Exception:
            pass
        raise TranscriptionError(msg)

    try:
        payload = resp.json()
    except ValueError as exc:
        raise TranscriptionError(f"Malformed response: {exc}") from exc

    text = (payload.get("text") or "").strip()
    return text
