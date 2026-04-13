"""
FastRouter — Speech-to-Text via Gemini Flash Lite.

Sends base64-encoded WebM/Opus audio to google/gemini-3.1-flash-lite-preview
through FastRouter's Anthropic-compatible /v1/messages endpoint and returns
the plain transcript.
"""

import asyncio
import base64
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

_STT_MODEL = "google/gemini-3.1-flash-lite-preview"
_MIN_AUDIO_BYTES = 1024  # 1 KB — anything smaller is almost certainly silence
_MAX_RETRIES = 2
_RETRY_DELAY_S = 1.0
_TIMEOUT_S = 15.0

_SYSTEM_PROMPT = (
    "You are a speech transcription engine for a children's math tutoring app (Grades 1–5). "
    "Transcribe the audio exactly as spoken. Return only the transcript, nothing else. "
    "If the audio is silent, unclear, or contains no speech, return an empty string."
)


# ── Exceptions ───────────────────────────────────────────────────────────


class STTError(Exception):
    """Raised when the FastRouter STT API returns a non-200 response."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"STT API error {status_code}: {body}")


# ── Public API ───────────────────────────────────────────────────────────


async def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcribe raw audio bytes to text via Gemini Flash Lite.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio data (WebM/Opus chunks from WebRTC, ~5 s each).

    Returns
    -------
    str
        Plain transcript text, stripped of whitespace.
        Empty string if the audio is too short, silent, or unintelligible.

    Raises
    ------
    STTError
        If the API returns a non-200 response after exhausting retries.
    """
    # -- Fast exit for empty / tiny audio --------------------------------
    if not audio_bytes or len(audio_bytes) < _MIN_AUDIO_BYTES:
        logger.debug(
            "Audio too short (%d B), skipping STT.",
            len(audio_bytes) if audio_bytes else 0,
        )
        return ""

    # -- Encode audio for the API ----------------------------------------
    audio_b64 = base64.standard_b64encode(audio_bytes).decode("ascii")

    payload = {
        "model": _STT_MODEL,
        "max_tokens": 1024,
        "system": _SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "audio/webm",
                            "data": audio_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Transcribe this audio.",
                    },
                ],
            }
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.FASTROUTER_API_KEY,
        "anthropic-version": "2023-06-01",
    }

    url = f"{settings.FASTROUTER_BASE_URL}/messages"

    # -- Request with retry loop -----------------------------------------
    last_error: STTError | None = None

    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        for attempt in range(_MAX_RETRIES + 1):  # 1 initial + up to 2 retries
            try:
                resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    # Anthropic response shape:
                    #   {"content": [{"type": "text", "text": "…"}, …]}
                    text_blocks = [
                        block["text"]
                        for block in data.get("content", [])
                        if block.get("type") == "text"
                    ]
                    return " ".join(text_blocks).strip()

                # -- Non-200 ------------------------------------------------
                body_text = resp.text
                last_error = STTError(resp.status_code, body_text)

                # Retry only on transient 5xx errors
                if resp.status_code >= 500 and attempt < _MAX_RETRIES:
                    logger.warning(
                        "STT transient error %d (attempt %d/%d), retrying in %gs…",
                        resp.status_code,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        _RETRY_DELAY_S,
                    )
                    await asyncio.sleep(_RETRY_DELAY_S)
                    continue

                # 4xx or final 5xx attempt — raise immediately
                logger.error(
                    "STT API error %d: %.200s", resp.status_code, body_text
                )
                raise last_error

            except httpx.TimeoutException:
                last_error = STTError(0, "Request timed out")
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "STT timeout (attempt %d/%d), retrying in %gs…",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        _RETRY_DELAY_S,
                    )
                    await asyncio.sleep(_RETRY_DELAY_S)
                    continue
                logger.error(
                    "STT timed out after %d attempts.", _MAX_RETRIES + 1
                )
                raise last_error

    # Unreachable in practice, but satisfies the type checker
    raise last_error or STTError(0, "Unknown STT failure")
