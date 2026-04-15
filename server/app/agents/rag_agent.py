"""
RAG Agent — Retrieval-Augmented Generation for curriculum-grounded responses.

Inherits from ``BaseAgent`` and follows the standard agent contract:
accepts a ``StatePrompt``, returns an ``AgentResponse``.

Flow:
    1. Extract query, topic, grade from StatePrompt
    2. Embed query → retrieve top-10 chunks from Pinecone (via RAG pipeline)
    3. Re-rank top-10 → top-5
    4. Build augmented prompt: [Retrieved Context] --- [Student Query]
    5. Call LLM via FastRouter
    6. Return structured AgentResponse

Usage::

    from app.agents.rag_agent import rag_agent

    response = await rag_agent(state_prompt)
    print(response.text)   # curriculum-grounded answer
"""

import logging
from typing import Any

from app.agents.base import BaseAgent, AgentResponse
from app.integrations.fastrouter.llm import generate_response, stream_response
from app.rag.pipeline import run_rag_pipeline, RAGResult
from app.rag.reranker import rerank
from app.schemas.state_prompt import StatePrompt

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

# ── Context assembly templates ───────────────────────────────────────────

CONTEXT_TEMPLATE = """\
[Retrieved Curriculum Context]
{context}
---
[Student Query]
{query}"""

EMPTY_CONTEXT_TEMPLATE = """\
[No curriculum context found for this query]
---
[Student Query]
{query}"""


# ── Agent ────────────────────────────────────────────────────────────────


class RAGAgent(BaseAgent):
    """Retrieval-Augmented Generation agent.

    Retrieves curriculum chunks from Pinecone, re-ranks them, and
    generates a grounded LLM response via FastRouter.
    """

    name = "rag_agent"

    def __init__(
        self,
        *,
        top_k: int = 10,
        rerank_top_n: int = 5,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.top_k = top_k
        self.rerank_top_n = rerank_top_n
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model
        self.system_prompt = system_prompt or SYSTEM_PROMPT

    # ── BaseAgent interface ──────────────────────────────────────────

    async def run(self, state: StatePrompt) -> AgentResponse:
        """Execute the full RAG pipeline against a StatePrompt.

        Steps:
            1. Extract query + topic + grade from state
            2. Retrieve top-K chunks from Pinecone
            3. Re-rank → top-N
            4. Build augmented prompt
            5. Call LLM
            6. Return AgentResponse
        """
        query = state.query
        topic = state.current_topic or "general"
        grade = state.difficulty_level  # maps to curriculum grade

        if not query.strip():
            return self.respond(
                text="",
                metadata={"skipped": True, "reason": "empty_query"},
            )

        # ── 1-2. Retrieve via RAG pipeline ───────────────────────────
        rag_result: RAGResult = await run_rag_pipeline(
            query,
            grade=grade,
            topic=topic,
            top_k=self.top_k,
        )

        # ── 3. Re-rank top-K → top-N ────────────────────────────────
        reranked = rerank(
            query,
            rag_result.retrieval.results,
            top_n=self.rerank_top_n,
        )

        # ── 4. Build augmented prompt ────────────────────────────────
        context_text = "\n\n---\n\n".join(
            r.text for r in reranked if r.text
        )

        if context_text.strip():
            augmented_prompt = CONTEXT_TEMPLATE.format(
                context=context_text,
                query=query,
            )
        else:
            augmented_prompt = EMPTY_CONTEXT_TEMPLATE.format(query=query)

        # Prepend session context if available
        session_context = self._build_session_context(state)
        if session_context:
            augmented_prompt = (
                f"[Session Context]\n{session_context}\n\n{augmented_prompt}"
            )

        # ── 5. Call LLM ─────────────────────────────────────────────
        answer = await generate_response(
            augmented_prompt,
            system_prompt=self.system_prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # ── 6. Return structured response ────────────────────────────
        return self.respond(
            text=answer,
            metadata=self._build_metadata(
                query=query,
                topic=topic,
                grade=grade,
                chunks_retrieved=rag_result.num_chunks,
                chunks_after_rerank=len(reranked),
            ),
        )

    # ── Streaming variant ────────────────────────────────────────────

    async def run_streaming(self, state: StatePrompt):
        """Execute RAG with streamed LLM output.

        Yields individual text tokens for real-time WebSocket delivery.

        Parameters
        ----------
        state : StatePrompt
            Validated context snapshot.

        Yields
        ------
        str
            Individual text chunks from the LLM stream.
        """
        query = state.query
        topic = state.current_topic or "general"
        grade = state.difficulty_level

        if not query.strip():
            return

        # 1-2. Retrieve
        rag_result = await run_rag_pipeline(
            query,
            grade=grade,
            topic=topic,
            top_k=self.top_k,
        )

        # 3. Re-rank
        reranked = rerank(
            query,
            rag_result.retrieval.results,
            top_n=self.rerank_top_n,
        )

        # 4. Build prompt
        context_text = "\n\n---\n\n".join(
            r.text for r in reranked if r.text
        )

        if context_text.strip():
            augmented_prompt = CONTEXT_TEMPLATE.format(
                context=context_text,
                query=query,
            )
        else:
            augmented_prompt = EMPTY_CONTEXT_TEMPLATE.format(query=query)

        session_context = self._build_session_context(state)
        if session_context:
            augmented_prompt = (
                f"[Session Context]\n{session_context}\n\n{augmented_prompt}"
            )

        # 5. Stream LLM
        async for token in stream_response(
            augmented_prompt,
            system_prompt=self.system_prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            yield token

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_session_context(state: StatePrompt) -> str:
        """Build an optional session context string from StatePrompt."""
        parts: list[str] = []

        if state.mastery_score > 0:
            parts.append(
                f"Student mastery on {state.current_topic}: "
                f"{state.mastery_score:.0%}"
            )
        if state.emotion.label not in ("neutral", "unknown"):
            parts.append(
                f"Current emotion: {state.emotion.label} "
                f"(confidence: {state.emotion.confidence:.0%})"
            )
        if state.session_summary:
            parts.append(f"Session summary: {state.session_summary}")

        return "\n".join(parts)

    @staticmethod
    def _build_metadata(
        *,
        query: str,
        topic: str,
        grade: int,
        chunks_retrieved: int,
        chunks_after_rerank: int,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "topic": topic,
            "grade": grade,
            "chunks_retrieved": chunks_retrieved,
            "chunks_after_rerank": chunks_after_rerank,
        }


# ── Singleton ────────────────────────────────────────────────────────────
rag_agent = RAGAgent()
