"""
RAG Agent — Retrieval-Augmented Generation for curriculum-grounded responses.

Takes a student query with grade/topic context, retrieves relevant
curriculum chunks from Pinecone, and generates a grounded LLM response
via FastRouter. Independently callable by any orchestrator or endpoint.

Flow:
    1. Accept query + topic + grade
    2. Run RAG pipeline → embed query → retrieve context from Pinecone
    3. Build augmented prompt (context + query)
    4. Call FastRouter LLM with system persona
    5. Return structured RAGAgentResponse
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.integrations.fastrouter.llm import generate_response, stream_response
from app.rag.pipeline import run_rag_pipeline, RAGResult

logger = logging.getLogger(__name__)


# ── System Prompt ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Pal, a friendly and encouraging AI math tutor for primary school \
students (Grades 1–5). Your responses must follow these rules:

1. ONLY use the [Retrieved Curriculum Context] provided to answer.
2. If the context does not contain the answer, say so honestly — never invent \
   mathematical facts.
3. Use age-appropriate language for the student's grade level.
4. Use Socratic scaffolding: ask guiding questions instead of giving direct answers.
5. Format math expressions using LaTeX delimiters ($$...$$) for rendering.
6. Keep responses concise — under 150 words unless a step-by-step solution \
   is needed.
7. Always be positive and encouraging. Use emojis sparingly (1–2 per response).\
"""


# ── Response Schema ──────────────────────────────────────────────────────

@dataclass
class RAGAgentResponse:
    """Structured output from the RAG Agent."""

    answer: str
    query: str
    grade: int
    topic: str
    num_chunks_used: int
    model: str
    context_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Agent ────────────────────────────────────────────────────────────────

async def run(
    query: str,
    *,
    grade: int,
    topic: str,
    top_k: int = 10,
    subtopic: str | None = None,
    system_prompt: str | None = None,
    session_context: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> RAGAgentResponse:
    """Execute the RAG Agent end-to-end.

    Parameters
    ----------
    query : str
        The student's question.
    grade : int
        Grade level (1–5).
    topic : str
        Curriculum topic (e.g. "Fractions").
    top_k : int
        Number of curriculum chunks to retrieve. Default 10.
    subtopic : str, optional
        Narrow retrieval to a specific subtopic.
    system_prompt : str, optional
        Override the default tutor persona prompt.
    session_context : str, optional
        Extra context (mastery scores, session summary) prepended to the
        augmented prompt.
    model : str, optional
        Override the default chat model.
    temperature : float
        LLM sampling temperature. Default 0.7.
    max_tokens : int
        Max response tokens. Default 1024.

    Returns
    -------
    RAGAgentResponse
        Contains the answer text, retrieval metadata, and model info.
    """
    # 1–3. RAG pipeline: embed → retrieve → assemble augmented prompt
    logger.info(
        "RAG Agent: query='%s', grade=%d, topic=%s",
        query[:60],
        grade,
        topic,
    )

    rag_result: RAGResult = await run_rag_pipeline(
        query,
        grade=grade,
        topic=topic,
        top_k=top_k,
        subtopic=subtopic,
        system_context=session_context,
    )

    # 4. Call LLM via FastRouter
    resolved_system = system_prompt or SYSTEM_PROMPT
    resolved_model = model  # None → uses config default

    answer = await generate_response(
        rag_result.augmented_prompt,
        system_prompt=resolved_system,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    logger.info(
        "RAG Agent response: %d chars, %d chunks used",
        len(answer),
        rag_result.num_chunks,
    )

    # 5. Return structured response
    return RAGAgentResponse(
        answer=answer,
        query=query,
        grade=grade,
        topic=topic,
        num_chunks_used=rag_result.num_chunks,
        model=resolved_model or "default",
        context_text=rag_result.context_text,
        metadata={
            "top_k": top_k,
            "subtopic": subtopic,
            "temperature": temperature,
        },
    )


async def run_streaming(
    query: str,
    *,
    grade: int,
    topic: str,
    top_k: int = 10,
    subtopic: str | None = None,
    system_prompt: str | None = None,
    session_context: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
):
    """Execute the RAG Agent with streamed LLM output.

    Yields individual text tokens as they arrive — designed for
    real-time WebSocket delivery to the frontend.

    Parameters match :func:`run`.

    Yields
    ------
    str
        Individual text chunks from the LLM stream.
    """
    # 1–3. RAG pipeline
    rag_result: RAGResult = await run_rag_pipeline(
        query,
        grade=grade,
        topic=topic,
        top_k=top_k,
        subtopic=subtopic,
        system_context=session_context,
    )

    # 4. Stream LLM response
    resolved_system = system_prompt or SYSTEM_PROMPT

    async for token in stream_response(
        rag_result.augmented_prompt,
        system_prompt=resolved_system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield token
