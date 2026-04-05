"""
FastRouter — Embeddings wrapper.

Provides async functions for generating text embeddings via the
OpenAI-compatible FastRouter API (text-embedding-3-small by default).
"""

import logging
from typing import Optional

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError

from app.core.config import settings

logger = logging.getLogger(__name__)

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

async def get_embeddings(
    text: str,
    *,
    model: str | None = None,
    dimensions: int | None = None,
) -> list[float]:
    """Generate an embedding vector for a single text string.

    Parameters
    ----------
    text : str
        The input text to embed.
    model : str, optional
        Override the default embedding model from settings.
    dimensions : int, optional
        Output vector dimensions (e.g. 1536). If omitted, uses model default.

    Returns
    -------
    list[float]
        The embedding vector.
    """
    client = _get_client()
    resolved_model = model or settings.FASTROUTER_EMBEDDING_MODEL

    kwargs: dict = {"model": resolved_model, "input": text}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions

    try:
        response = await client.embeddings.create(**kwargs)
        embedding = response.data[0].embedding
        logger.debug(
            "Embedding [%s]: %d dims for %d chars",
            resolved_model,
            len(embedding),
            len(text),
        )
        return embedding

    except RateLimitError:
        logger.warning("FastRouter rate limit hit for embeddings.")
        raise
    except APIConnectionError:
        logger.error("FastRouter connection failed for embeddings.")
        raise
    except APIStatusError as exc:
        logger.error("FastRouter API error %d: %s", exc.status_code, exc.message)
        raise


async def get_embeddings_batch(
    texts: list[str],
    *,
    model: str | None = None,
) -> list[list[float]]:
    """Generate embedding vectors for a batch of texts.

    Uses the batch input feature of the embeddings API for efficiency.

    Parameters
    ----------
    texts : list[str]
        List of input texts.
    model : str, optional
        Override the default embedding model.

    Returns
    -------
    list[list[float]]
        List of embedding vectors in the same order as input.
    """
    if not texts:
        return []

    client = _get_client()
    resolved_model = model or settings.FASTROUTER_EMBEDDING_MODEL

    try:
        response = await client.embeddings.create(
            model=resolved_model,
            input=texts,
        )
        # Sort by index to guarantee order matches input
        sorted_data = sorted(response.data, key=lambda d: d.index)
        embeddings = [d.embedding for d in sorted_data]
        logger.debug(
            "Batch embedding [%s]: %d texts → %d dims each",
            resolved_model,
            len(texts),
            len(embeddings[0]) if embeddings else 0,
        )
        return embeddings

    except RateLimitError:
        logger.warning("FastRouter rate limit hit for batch embeddings.")
        raise
    except APIConnectionError:
        logger.error("FastRouter connection failed for batch embeddings.")
        raise
    except APIStatusError as exc:
        logger.error("FastRouter API error %d: %s", exc.status_code, exc.message)
        raise
