"""
FastRouter — Speech-to-Text via Gemini Flash Lite.

Sends base64-encoded WebM/Opus audio to google/gemini-3.1-flash-lite-preview
through FastRouter's OpenAI-compatible /v1/chat/completions endpoint and
returns the plain transcript.
"""

import asyncio
import base64
import logging

from openai import (
    AsyncOpenAI,
    APIConnectionError,
    RateLimitError,
    APIStatusError,
)

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


# ── Client (lazy singleton) ─────────────────────────────────────────────

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Return a cached async OpenAI client pointed at FastRouter."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.FASTROUTER_API_KEY,
            base_url=settings.FASTROUTER_BASE_URL,
            max_retries=0,  # We handle retries manually for finer control
            timeout=_TIMEOUT_S,
        )
    return _client


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
    data_uri = f"data:audio/webm;base64,{audio_b64}"

    # OpenAI-compatible multimodal message format
    # Audio is sent as a data-URI inside an "image_url" content block.
    # Despite the name, OpenRouter-compatible providers (including FastRouter)
    # route any media type through this block for multimodal models.
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                },
                {
                    "type": "text",
                    "text": "Transcribe this audio.",
                },
            ],
        },
    ]

    # -- Request with retry loop -----------------------------------------
    last_error: STTError | None = None
    client = _get_client()

    for attempt in range(_MAX_RETRIES + 1):  # 1 initial + up to 2 retries
        try:
            response = await client.chat.completions.create(
                model=_STT_MODEL,
                messages=messages,
                max_tokens=1024,
                temperature=0.0,  # Deterministic for transcription
            )

            content = response.choices[0].message.content or ""
            transcript = content.strip()

            logger.debug(
                "STT transcript [%s]: %d chars",
                _STT_MODEL,
                len(transcript),
            )
            return transcript

        except RateLimitError as exc:
            last_error = STTError(429, str(exc))
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "STT rate limit (attempt %d/%d), retrying in %gs…",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    _RETRY_DELAY_S,
                )
                await asyncio.sleep(_RETRY_DELAY_S)
                continue
            logger.error("STT rate limit after %d attempts.", _MAX_RETRIES + 1)
            raise last_error

        except APIStatusError as exc:
            last_error = STTError(exc.status_code, exc.message)

            # Retry only on transient 5xx errors
            if exc.status_code >= 500 and attempt < _MAX_RETRIES:
                logger.warning(
                    "STT transient error %d (attempt %d/%d), retrying in %gs…",
                    exc.status_code,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    _RETRY_DELAY_S,
                )
                await asyncio.sleep(_RETRY_DELAY_S)
                continue

            # 4xx or final 5xx attempt — raise immediately
            logger.error(
                "STT API error %d: %.200s", exc.status_code, exc.message
            )
            raise last_error

        except APIConnectionError:
            last_error = STTError(0, "Connection failed / timed out")
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "STT connection error (attempt %d/%d), retrying in %gs…",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    _RETRY_DELAY_S,
                )
                await asyncio.sleep(_RETRY_DELAY_S)
                continue
            logger.error(
                "STT connection failed after %d attempts.", _MAX_RETRIES + 1
            )
            raise last_error

    # Unreachable in practice, but satisfies the type checker
    raise last_error or STTError(0, "Unknown STT failure")
