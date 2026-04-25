"""
RAG Retriever — curriculum-grounded vector search.

Embeds the student query via FastRouter, then queries Pinecone with
grade/topic metadata filters to retrieve the most relevant curriculum
chunks for prompt augmentation.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.integrations.fastrouter.embeddings import get_embeddings
from app.rag.pinecone_client import query_vectors

logger = logging.getLogger(__name__)


# ── Topic Normalisation ──────────────────────────────────────────────────

# Roman numeral mapping used in Pinecone topic names (e.g. "We the TravellersI")
_ARABIC_TO_ROMAN = {
    "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
    "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X",
}

# Reverse map
_ROMAN_TO_ARABIC = {v: k for k, v in _ARABIC_TO_ROMAN.items()}

# Pattern to detect trailing separators with a number:
#   "We the Travellers - 1"  →  match(" - 1")
#   "We the Travellers-1"    →  match("-1")
_TRAILING_NUM_RE = re.compile(r"[\s\-–—]+(\d+)\s*$")

# Pattern to detect a trailing Roman numeral (capital) glued to the name:
#   "We the TravellersI"  →  match("I")
_TRAILING_ROMAN_RE = re.compile(r"(I{1,3}|IV|V|VI{0,3}|IX|X)\s*$")


def _generate_topic_variants(topic: str) -> list[str]:
    """Generate plausible Pinecone topic-name variants for a UI topic string.

    Covers mismatches like:
        UI: "We the Travellers - 1"   →  Pinecone: "We the TravellersI"
        UI: "We the Travellers"       →  Pinecone: "We the Travellers"

    Returns a deduplicated list of 1-N candidate strings to use with ``$in``.
    """
    variants: set[str] = set()
    stripped = topic.strip()
    variants.add(stripped)

    # ── Case 1: trailing " - N" / " – N" / "-N" ─────────────────────
    m = _TRAILING_NUM_RE.search(stripped)
    if m:
        arabic = m.group(1)
        base = stripped[: m.start()].rstrip()   # "We the Travellers"
        roman = _ARABIC_TO_ROMAN.get(arabic, arabic)

        variants.add(base)                      # "We the Travellers"
        variants.add(f"{base}{roman}")           # "We the TravellersI"
        variants.add(f"{base} {roman}")          # "We the Travellers I"
        variants.add(f"{base} - {arabic}")       # "We the Travellers - 1"
        variants.add(f"{base}-{arabic}")         # "We the Travellers-1"

    # ── Case 2: trailing Roman numeral glued to text ─────────────────
    elif _TRAILING_ROMAN_RE.search(stripped):
        m2 = _TRAILING_ROMAN_RE.search(stripped)
        roman = m2.group(1)
        base = stripped[: m2.start()]

        arabic = _ROMAN_TO_ARABIC.get(roman, "")
        variants.add(base)
        variants.add(f"{base}{roman}")
        if arabic:
            variants.add(f"{base} - {arabic}")
            variants.add(f"{base}-{arabic}")

    result = sorted(variants)
    if len(result) > 1:
        logger.debug("Topic variants for %r: %s", topic, result)
    return result


# ── Result Schema ────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    """A single retrieved curriculum chunk."""

    id: str
    score: float
    text: str = ""
    grade: int = 0
    topic: str = ""
    subtopic: str = ""
    chunk_index: int = 0
    source_doc: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResponse:
    """Full retriever response wrapping all retrieved chunks."""

    query: str
    grade: int
    topic: str
    results: list[RetrievalResult]
    total: int = 0

    @property
    def context_text(self) -> str:
        """Concatenate all chunk texts into a single context block.

        Used for injecting into the LLM prompt::

            [Retrieved Context]
            ---
            [Student Query]
        """
        return "\n\n---\n\n".join(r.text for r in self.results if r.text)


# ── Public API ───────────────────────────────────────────────────────────

async def retrieve(
    query: str,
    *,
    grade: int,
    topic: str,
    top_k: int = 10,
    namespace: str | None = None,
    subtopic: str | None = None,
    score_threshold: float = 0.0,
) -> RetrievalResponse:
    """Retrieve curriculum chunks relevant to a student query.

    Pipeline:
        1. Embed the query via FastRouter (text-embedding-3-small)
        2. Query Pinecone filtered by grade + topic (+ optional subtopic)
        3. Parse results into structured ``RetrievalResult`` objects

    Parameters
    ----------
    query : str
        The student's question or search text.
    grade : int
        Filter by grade level (1–5).
    topic : str
        Filter by curriculum topic (e.g. "Fractions").
    top_k : int
        Max results to return. Default 10.
    namespace : str, optional
        Pinecone namespace. Defaults to ``"grade-{grade}"``.
    subtopic : str, optional
        Optional additional subtopic filter.
    score_threshold : float
        Minimum cosine similarity score to include. Default 0.0 (all).

    Returns
    -------
    RetrievalResponse
        Structured response with all retrieved chunks and metadata.
    """
    # 1. Embed the query
    logger.debug("Embedding query: %s", query[:80])
    query_vector = await get_embeddings(query)

    # 2. Build metadata filter
    #    Pinecone metadata has a ``topic`` field matching the chapter name
    #    (e.g. "Weight and Capacity", "Fractions") and a ``grade`` int.
    pinecone_filter: dict[str, Any] = {
        "grade": {"$eq": grade},
    }

    # Only add topic filter if we have a specific topic (not "general")
    if topic and topic.lower() not in ("general", "math", "mathematics", ""):
        variants = _generate_topic_variants(topic)
        if len(variants) == 1:
            pinecone_filter["topic"] = {"$eq": variants[0]}
        else:
            pinecone_filter["topic"] = {"$in": variants}

    # 3. Resolve namespace
    #    The upsert script stores all vectors in the default (empty) namespace,
    #    so we query the default namespace unless explicitly overridden.
    resolved_namespace = namespace or ""

    # 4. Query Pinecone
    logger.debug(
        "Querying Pinecone: namespace='%s', top_k=%d, filter=%s",
        resolved_namespace,
        top_k,
        pinecone_filter,
    )
    raw_matches = query_vectors(
        vector=query_vector,
        namespace=resolved_namespace,
        top_k=top_k,
        filter=pinecone_filter,
        include_metadata=True,
    )

    # 4b. Fallback: if no results with topic filter, retry without it
    if not raw_matches and pinecone_filter.get("topic"):
        logger.info(
            "No results with topic filter, retrying grade-only  "
            "grade=%d, topic=%s",
            grade,
            topic,
        )
        grade_only_filter: dict[str, Any] = {"grade": {"$eq": grade}}
        raw_matches = query_vectors(
            vector=query_vector,
            namespace=resolved_namespace,
            top_k=top_k,
            filter=grade_only_filter,
            include_metadata=True,
        )

    # 5. Parse into structured results
    results: list[RetrievalResult] = []
    for match in raw_matches:
        score = match.get("score", 0.0)
        if score < score_threshold:
            continue

        meta = match.get("metadata", {})
        results.append(
            RetrievalResult(
                id=match["id"],
                score=score,
                text=meta.get("text", ""),
                grade=meta.get("grade", grade),
                topic=meta.get("topic", topic),
                subtopic=meta.get("subtopic", ""),
                chunk_index=meta.get("chunk_index", 0),
                source_doc=meta.get("source_doc", ""),
                metadata=meta,
            )
        )

    logger.info(
        "Retrieved %d chunks for query '%s' (grade=%d, topic=%s)",
        len(results),
        query[:50],
        grade,
        topic,
    )

    return RetrievalResponse(
        query=query,
        grade=grade,
        topic=topic,
        results=results,
        total=len(results),
    )
