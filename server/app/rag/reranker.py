"""
Re-ranker — score-based re-ordering of retrieved curriculum chunks.

Takes the top-K results from Pinecone (already sorted by cosine
similarity) and re-ranks them using a lightweight scoring function
that considers both the vector score and text-query overlap.

This module provides a fast, dependency-free re-ranker suitable for
the PALM pipeline.  It can be swapped for a cross-encoder or Cohere
re-rank API in the future without changing the interface.

Usage::

    from app.rag.reranker import rerank

    top5 = rerank(query, results, top_n=5)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever import RetrievalResult

logger = logging.getLogger(__name__)


def rerank(
    query: str,
    results: list[RetrievalResult],
    *,
    top_n: int = 5,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[RetrievalResult]:
    """Re-rank retrieved chunks and return the top N.

    Scoring formula::

        final_score = vector_weight * normalised_vector_score
                    + keyword_weight * keyword_overlap_ratio

    Parameters
    ----------
    query : str
        The student's original question.
    results : list[RetrievalResult]
        Chunks returned by the retriever (already scored by Pinecone).
    top_n : int
        Number of results to keep after re-ranking. Default 5.
    vector_weight : float
        Weight for the normalised Pinecone score. Default 0.7.
    keyword_weight : float
        Weight for the keyword overlap signal. Default 0.3.

    Returns
    -------
    list[RetrievalResult]
        Re-ranked and truncated list of chunks.
    """
    if not results:
        return []

    # Tokenise query into lowercase keywords (strip common noise)
    query_tokens = _tokenise(query)

    if not query_tokens:
        # No useful keywords — fall back to vector-score ordering
        return sorted(results, key=lambda r: r.score, reverse=True)[:top_n]

    # Normalise vector scores to [0, 1] within this result set
    max_score = max(r.score for r in results) or 1.0
    min_score = min(r.score for r in results)
    score_range = max_score - min_score or 1.0

    scored: list[tuple[float, RetrievalResult]] = []

    for result in results:
        # Normalised vector score
        norm_vector = (result.score - min_score) / score_range

        # Keyword overlap: fraction of query tokens found in chunk text
        chunk_tokens = _tokenise(result.text)
        if chunk_tokens:
            overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
        else:
            overlap = 0.0

        final = vector_weight * norm_vector + keyword_weight * overlap
        scored.append((final, result))

    # Sort descending by final score
    scored.sort(key=lambda pair: pair[0], reverse=True)

    reranked = [r for _, r in scored[:top_n]]

    logger.debug(
        "Re-ranked %d → %d chunks (query='%s')",
        len(results),
        len(reranked),
        query[:50],
    )

    return reranked


# ── Helpers ──────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "have", "has", "had", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "it", "its", "this",
    "that", "and", "or", "but", "not", "no", "if", "so", "what",
    "how", "when", "where", "who", "which", "can", "will", "i",
    "me", "my", "you", "your", "we", "our", "they", "them",
})

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenise(text: str) -> set[str]:
    """Extract lowercase keyword tokens, removing stop words."""
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP_WORDS} 
