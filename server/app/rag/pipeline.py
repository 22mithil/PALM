"""
RAG Pipeline — end-to-end retrieval-augmented generation.

Orchestrates the full RAG flow:
    1. Embed the student query
    2. Retrieve top-K curriculum chunks from Pinecone
    3. Assemble context
    4. Return an augmented prompt ready for LLM consumption

Designed to be reusable by any agent (RAG, Hint, Quiz, Dialogue).
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.rag.retriever import retrieve, RetrievalResponse

logger = logging.getLogger(__name__)


# ── Response Schema ──────────────────────────────────────────────────────

@dataclass
class RAGResult:
    """Output of the RAG pipeline, ready for LLM consumption."""

    augmented_prompt: str
    context_text: str
    query: str
    grade: int
    topic: str
    num_chunks: int
    retrieval: RetrievalResponse


# ── Pipeline ─────────────────────────────────────────────────────────────

CONTEXT_TEMPLATE = """[Retrieved Curriculum Context]
{context}
---
[Student Query]
{query}"""

EMPTY_CONTEXT_TEMPLATE = """[No curriculum context found for this query]
---
[Student Query]
{query}"""


async def run_rag_pipeline(
    query: str,
    *,
    grade: int,
    topic: str,
    top_k: int = 10,
    subtopic: str | None = None,
    score_threshold: float = 0.0,
    system_context: str | None = None,
) -> RAGResult:
    """Execute the full RAG pipeline and return an augmented prompt.

    Parameters
    ----------
    query : str
        The student's question.
    grade : int
        Grade level (1–5) for Pinecone namespace + filter.
    topic : str
        Curriculum topic for metadata filter.
    top_k : int
        Number of chunks to retrieve. Default 10.
    subtopic : str, optional
        Additional subtopic filter.
    score_threshold : float
        Minimum similarity score. Default 0.0 (include all).
    system_context : str, optional
        Extra context to prepend (e.g. mastery info, session summary).

    Returns
    -------
    RAGResult
        Contains the augmented prompt, raw context, and retrieval metadata.

    Usage by agents::

        from app.rag.pipeline import run_rag_pipeline

        result = await run_rag_pipeline(
            query="How do I add fractions with different denominators?",
            grade=3,
            topic="Fractions",
        )
        llm_response = await generate_response(
            result.augmented_prompt,
            system_prompt="You are a friendly math tutor ...",
        )
    """
    # 1–2. Embed query + retrieve from Pinecone
    logger.info(
        "RAG pipeline: query='%s', grade=%d, topic=%s, top_k=%d",
        query[:60],
        grade,
        topic,
        top_k,
    )

    retrieval = await retrieve(
        query,
        grade=grade,
        topic=topic,
        top_k=top_k,
        subtopic=subtopic,
        score_threshold=score_threshold,
    )

    # 3. Assemble context
    context_text = retrieval.context_text

    if context_text.strip():
        augmented_prompt = CONTEXT_TEMPLATE.format(
            context=context_text,
            query=query,
        )
    else:
        augmented_prompt = EMPTY_CONTEXT_TEMPLATE.format(query=query)
        logger.warning(
            "No curriculum chunks retrieved for query='%s' (grade=%d, topic=%s)",
            query[:60],
            grade,
            topic,
        )

    # 4. Prepend optional system context (mastery, session summary, etc.)
    if system_context:
        augmented_prompt = f"[Session Context]\n{system_context}\n\n{augmented_prompt}"

    logger.info(
        "RAG pipeline complete: %d chunks, prompt length=%d chars",
        retrieval.total,
        len(augmented_prompt),
    )

    return RAGResult(
        augmented_prompt=augmented_prompt,
        context_text=context_text,
        query=query,
        grade=grade,
        topic=topic,
        num_chunks=retrieval.total,
        retrieval=retrieval,
    )
