"""
Pinecone vector database client for the PALM curriculum RAG pipeline.

Provides reusable functions for upserting and querying vectors against
the ``palm-fyp`` index (cosine similarity, 1536 dims).

Index configuration (from PRD):
    - Index Name:  palm-fyp
    - Dimensions:  1536 (text-embedding-3-small)
    - Metric:      Cosine Similarity
    - Namespaces:  grade-1 … grade-5
    - Metadata:    grade, topic, subtopic, chunk_index, source_doc
"""

import logging
from typing import Any, Optional

from pinecone import Pinecone

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Client (lazy singleton) ─────────────────────────────────────────────
_pc: Pinecone | None = None
_index: Any | None = None


def _get_index():
    """Return a cached Pinecone Index instance."""
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        _index = _pc.Index(settings.PINECONE_INDEX_NAME)
        logger.info(
            "Pinecone index '%s' connected.",
            settings.PINECONE_INDEX_NAME,
        )
    return _index


# ── Public API ───────────────────────────────────────────────────────────

def upsert_vectors(
    vectors: list[dict[str, Any]],
    *,
    namespace: str = "",
    batch_size: int = 100,
) -> int:
    """Upsert embedding vectors into Pinecone.

    Parameters
    ----------
    vectors : list[dict]
        Each dict must contain:
        - ``id``       : str — unique vector ID
        - ``values``   : list[float] — embedding vector (1536 dims)
        - ``metadata`` : dict — metadata (grade, topic, subtopic, etc.)

        Example::

            {
                "id": "grade3-fractions-chunk-001",
                "values": [0.012, -0.034, ...],
                "metadata": {
                    "grade": 3,
                    "topic": "Fractions",
                    "subtopic": "Addition",
                    "chunk_index": 1,
                    "source_doc": "ncert_grade3_ch7.pdf",
                    "text": "A fraction represents …",
                },
            }

    namespace : str
        Pinecone namespace (e.g. ``"grade-3"``). Empty string = default.
    batch_size : int
        Number of vectors per upsert call. Default 100.

    Returns
    -------
    int
        Total number of vectors upserted.
    """
    index = _get_index()
    total = 0

    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)
        logger.debug(
            "Upserted batch %d–%d (%d vectors) to namespace '%s'",
            i,
            i + len(batch) - 1,
            len(batch),
            namespace,
        )

    logger.info(
        "Upserted %d vectors total to namespace '%s'.",
        total,
        namespace,
    )
    return total


def query_vectors(
    vector: list[float],
    *,
    namespace: str = "",
    top_k: int = 10,
    filter: Optional[dict[str, Any]] = None,
    include_metadata: bool = True,
    include_values: bool = False,
) -> list[dict[str, Any]]:
    """Query the Pinecone index for similar vectors.

    Parameters
    ----------
    vector : list[float]
        The query embedding vector (1536 dims).
    namespace : str
        Pinecone namespace to search in (e.g. ``"grade-3"``).
    top_k : int
        Number of top results to return. Default 10.
    filter : dict, optional
        Metadata filter (Pinecone filter syntax).
        Example: ``{"topic": {"$eq": "Fractions"}}``
    include_metadata : bool
        Whether to return metadata with results. Default True.
    include_values : bool
        Whether to return the stored vectors. Default False.

    Returns
    -------
    list[dict]
        List of match dicts, each containing:
        - ``id``       : str
        - ``score``    : float (cosine similarity, 0–1)
        - ``metadata`` : dict (if ``include_metadata=True``)

        Sorted by descending similarity score.
    """
    index = _get_index()

    results = index.query(
        vector=vector,
        namespace=namespace,
        top_k=top_k,
        filter=filter,
        include_metadata=include_metadata,
        include_values=include_values,
    )

    matches = []
    for match in results.get("matches", []):
        entry = {
            "id": match["id"],
            "score": match["score"],
        }
        if include_metadata and "metadata" in match:
            entry["metadata"] = match["metadata"]
        if include_values and "values" in match:
            entry["values"] = match["values"]
        matches.append(entry)

    logger.debug(
        "Query returned %d matches (top_k=%d, namespace='%s').",
        len(matches),
        top_k,
        namespace,
    )
    return matches


def delete_vectors(
    ids: list[str],
    *,
    namespace: str = "",
) -> None:
    """Delete vectors by ID from a namespace.

    Parameters
    ----------
    ids : list[str]
        Vector IDs to delete.
    namespace : str
        Pinecone namespace.
    """
    index = _get_index()
    index.delete(ids=ids, namespace=namespace)
    logger.info("Deleted %d vectors from namespace '%s'.", len(ids), namespace)


def get_index_stats() -> dict[str, Any]:
    """Return index statistics (total vectors, namespace breakdown)."""
    index = _get_index()
    stats = index.describe_index_stats()
    return stats
