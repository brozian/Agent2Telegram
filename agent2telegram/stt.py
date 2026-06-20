"""Optional speech-to-text for Telegram voice messages.

Currently supports **ElevenLabs Scribe** (`scribe_v1`). It is enabled only when the user
provides their own API key (``elevenlabs_api_key`` in config or ``ELEVENLABS_API_KEY`` in
the environment) — there is no shared/default key and no third-party Python dependency:
the multipart upload is built by hand on top of ``urllib``.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import uuid

log = logging.getLogger("agent2telegram.stt")

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL_ID = "scribe_v1"


class STTError(Exception):
    pass


def _multipart(fields: dict[str, str], filename: str, audio: bytes,
               content_type: str = "audio/ogg") -> tuple[str, bytes]:
    boundary = "----a2t" + uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode()
    )
    parts.append(audio)
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    return boundary, b"".join(parts)


def transcribe_elevenlabs(audio: bytes, *, api_key: str, filename: str = "voice.ogg",
                          opener=None, timeout: float = 120) -> str:
    """Transcribe *audio* bytes with ElevenLabs Scribe. Returns the recognized text."""
    if not api_key:
        raise STTError("no ElevenLabs API key configured")
    boundary, body = _multipart({"model_id": MODEL_ID}, filename, audio)
    req = urllib.request.Request(
        ELEVENLABS_URL,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    op = opener or urllib.request.build_opener()
    try:
        with op.open(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise STTError(f"ElevenLabs request failed: {e}") from e
    text = (payload.get("text") or "").strip()
    if not text:
        raise STTError("transcription returned no text")
    return text


def transcribe(audio: bytes, *, api_key: str, filename: str = "voice.ogg") -> str:
    """Provider dispatcher (only ElevenLabs Scribe today)."""
    return transcribe_elevenlabs(audio, api_key=api_key, filename=filename)
