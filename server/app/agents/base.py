"""
Base Agent Interface — abstract contract for all PALM agents.

Every agent in the pipeline (Dialogue, Engagement, Hint, Mastery,
Quiz, RAG) inherits from :class:`BaseAgent` and implements the
:meth:`run` coroutine.  This ensures a uniform input/output contract
that the Orchestrator can rely on without knowing agent internals.

Input contract:
    Every agent receives a validated ``StatePrompt`` — the structured
    context snapshot built by the Context Aggregator + StatePrompt Builder.

Output contract:
    Every agent returns an ``AgentResponse`` — a Pydantic model with
    ``text``, ``agent``, and ``metadata`` fields.

Usage::

    class MyAgent(BaseAgent):
        name = "my_agent"

        async def run(self, state: StatePrompt) -> AgentResponse:
            answer = await some_llm_call(state.query)
            return self.respond(text=answer, metadata={"model": "gpt-4"})

    agent = MyAgent()
    result = await agent(state_prompt)   # __call__ delegates to run()
    print(result.text)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.state_prompt import StatePrompt

logger = logging.getLogger(__name__)


# ── Response Schema ──────────────────────────────────────────────────────


class AgentResponse(BaseModel):
    """Standardised response returned by every agent.

    Attributes
    ----------
    text : str
        The agent's primary textual output (answer, hint, feedback, etc.).
    agent : str
        Identifier of the agent that produced this response.
    metadata : dict
        Arbitrary agent-specific metadata (model used, latency, scores, etc.).
    """

    text: str = Field(
        ...,
        description="Primary textual output from the agent.",
    )
    agent: str = Field(
        ...,
        description="Name of the agent that produced this response.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific metadata (model, latency, retrieval stats, etc.).",
    )


# ── Base Agent ───────────────────────────────────────────────────────────


class BaseAgent(ABC):
    """Abstract base class for all PALM pipeline agents.

    Subclasses MUST:
      1. Set ``name`` (class-level str identifying the agent).
      2. Implement ``async def run(self, state: StatePrompt) -> AgentResponse``.

    The base class provides:
      • ``__call__`` — convenience wrapper that delegates to ``run()``
        with automatic latency logging and error handling.
      • ``respond()`` — helper to build an ``AgentResponse`` pre-filled
        with the agent's ``name``.
    """

    name: str = "base_agent"

    # ── Abstract interface ───────────────────────────────────────────

    @abstractmethod
    async def run(self, state: StatePrompt) -> AgentResponse:
        """Execute the agent logic.

        Parameters
        ----------
        state : StatePrompt
            Validated structured context from the Context Aggregator.

        Returns
        -------
        AgentResponse
            Standardised response with ``text``, ``agent``, ``metadata``.
        """
        ...

    # ── Callable shortcut ────────────────────────────────────────────

    async def __call__(self, state: StatePrompt) -> AgentResponse:
        """Run the agent with latency tracking and error handling.

        This is the primary entry-point used by the Orchestrator.
        """
        start = time.perf_counter()
        try:
            response = await self.run(state)
            elapsed = time.perf_counter() - start

            # Inject latency into metadata
            response.metadata.setdefault("latency_ms", round(elapsed * 1000, 1))

            logger.info(
                "%s completed  session=%s  latency=%.0fms  text_len=%d",
                self.name,
                state.session_id,
                elapsed * 1000,
                len(response.text),
            )
            return response

        except Exception:
            elapsed = time.perf_counter() - start
            logger.exception(
                "%s failed  session=%s  after=%.0fms",
                self.name,
                state.session_id,
                elapsed * 1000,
            )
            # Return a safe error response so the pipeline doesn't crash
            return AgentResponse(
                text="",
                agent=self.name,
                metadata={
                    "error": True,
                    "latency_ms": round(elapsed * 1000, 1),
                },
            )

    # ── Response helper ──────────────────────────────────────────────

    def respond(
        self,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentResponse:
        """Build an ``AgentResponse`` pre-filled with this agent's name.

        Parameters
        ----------
        text : str
            The agent's textual output.
        metadata : dict, optional
            Extra metadata to attach.

        Returns
        -------
        AgentResponse
        """
        return AgentResponse(
            text=text,
            agent=self.name,
            metadata=metadata or {},
        )

    # ── Repr ─────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r})>"
