"""
FastRouter — LLM chat completion wrapper.

Provides async functions for single-shot and streamed chat completions
via the OpenAI-compatible FastRouter API.
"""

import logging
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any, Optional

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Token-usage tracking (per async task / turn) ────────────────────────
_token_usage: ContextVar[dict] = ContextVar(
    "llm_token_usage",
    default={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
)


def reset_token_counter() -> None:
    """Reset the per-turn token counter. Call at pipeline turn start."""
    _token_usage.set({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


def get_token_usage() -> dict:
    """Return accumulated token counts for the current turn."""
    return dict(_token_usage.get())

# ── Client (lazy singleton) ─────────────────────────────────────────────
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Return a cached async OpenAI client pointed at FastRouter."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.FASTROUTER_API_KEY,
            base_url=settings.FASTROUTER_BASE_URL,
            max_retries=settings.FASTROUTER_MAX_RETRIES,
            timeout=settings.FASTROUTER_TIMEOUT,
        )
    return _client


# ── Public API ───────────────────────────────────────────────────────────

async def generate_response(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    messages: list[dict[str, str]] | None = None,
    **kwargs: Any,
) -> str:
    """Generate a single chat completion and return the full text.

    Parameters
    ----------
    prompt : str
        The user message (ignored if ``messages`` is provided).
    system_prompt : str, optional
        System instruction prepended to the conversation.
    model : str, optional
        Override the default chat model from settings.
    temperature : float
        Sampling temperature (0–2). Default 0.7.
    max_tokens : int
        Max tokens in the response.
    messages : list[dict], optional
        Full message list (overrides ``prompt`` / ``system_prompt``).
    **kwargs
        Extra params forwarded to the API (e.g. ``top_p``, ``stop``).

    Returns
    -------
    str
        The assistant's reply text.
    """
    client = _get_client()
    resolved_model = model or settings.FASTROUTER_CHAT_MODEL

    if messages is None:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        content = response.choices[0].message.content or ""

        # ── Accumulate token usage ───────────────────────────────
        if response.usage:
            usage = _token_usage.get()
            usage = {
                "prompt_tokens": usage["prompt_tokens"] + (response.usage.prompt_tokens or 0),
                "completion_tokens": usage["completion_tokens"] + (response.usage.completion_tokens or 0),
                "total_tokens": usage["total_tokens"] + (response.usage.total_tokens or 0),
            }
            _token_usage.set(usage)

        logger.debug(
            "LLM response [%s]: %d tokens → %d chars",
            resolved_model,
            response.usage.completion_tokens if response.usage else -1,
            len(content),
        )
        return content

    except RateLimitError:
        logger.warning("FastRouter rate limit hit — retries exhausted.")
        raise
    except APIConnectionError:
        logger.error("FastRouter connection failed.")
        raise
    except APIStatusError as exc:
        logger.error("FastRouter API error %d: %s", exc.status_code, exc.message)
        raise


async def stream_response(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    messages: list[dict[str, str]] | None = None,
    **kwargs: Any,
) -> AsyncIterator[str]:
    """Stream chat completion tokens as an async iterator.

    Yields individual text chunks as they arrive. Useful for real-time
    WebSocket delivery to the frontend.

    Parameters match :func:`generate_response`.
    """
    client = _get_client()
    resolved_model = model or settings.FASTROUTER_CHAT_MODEL

    if messages is None:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

    try:
        stream = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    except RateLimitError:
        logger.warning("FastRouter rate limit hit during stream.")
        raise
    except APIConnectionError:
        logger.error("FastRouter connection failed during stream.")
        raise
    except APIStatusError as exc:
        logger.error("FastRouter API error %d: %s", exc.status_code, exc.message)
        raise
