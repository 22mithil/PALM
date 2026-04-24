"""
Orchestrator Executor — public API for the PALM orchestrator.

This is the single entry-point that the rest of the application calls
to run a ``StatePrompt`` through the LangGraph agent pipeline.

Usage::

    from app.orchestrator import run_orchestrator

    result = await run_orchestrator(state_prompt)
    print(result.final_response)   # text for the student
    print(result.agent_used)       # "hint_agent", "rag_agent", etc.
    print(result.route)            # "hint", "rag_dialogue", etc.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import AgentResponse
from app.orchestrator.graph import compiled_graph
from app.orchestrator.state import OrchestratorState
from app.schemas.state_prompt import StatePrompt

logger = logging.getLogger(__name__)


# ── Result Schema ────────────────────────────────────────────────────────


class OrchestratorResult(BaseModel):
    """Structured result returned by :func:`run_orchestrator`.

    Attributes
    ----------
    final_response : str
        The text to send back to the student.
    agent_used : str
        Name of the primary agent that produced the final response.
    route : str
        The route the orchestrator selected (e.g. ``"hint"``,
        ``"rag_dialogue"``).
    all_responses : list[AgentResponse]
        Every ``AgentResponse`` produced during the pipeline (useful
        for logging, debugging, or downstream analytics).
    metadata : dict
        Execution metadata (latency, error flags, etc.).
    """

    final_response: str = Field(
        ...,
        description="Text to return to the student.",
    )
    agent_used: str = Field(
        ...,
        description="Name of the agent that produced the final response.",
    )
    route: str = Field(
        ...,
        description="Route selected by the orchestrator router.",
    )
    all_responses: list[AgentResponse] = Field(
        default_factory=list,
        description="All agent responses produced during the pipeline.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metadata (latency, etc.).",
    )


# ── Public API ───────────────────────────────────────────────────────────


async def run_orchestrator(state_prompt: StatePrompt) -> OrchestratorResult:
    """Run the full LangGraph orchestrator pipeline.

    Takes a validated ``StatePrompt``, routes it through the appropriate
    agent(s), and returns a structured ``OrchestratorResult``.

    Parameters
    ----------
    state_prompt : StatePrompt
        Validated context snapshot from the StatePrompt Builder.

    Returns
    -------
    OrchestratorResult
        Contains ``final_response``, ``agent_used``, ``route``, and
        the full list of agent responses.

    Raises
    ------
    Exception
        Propagates any unhandled errors from the graph execution.
        Individual agent errors are caught by ``BaseAgent.__call__``
        and returned as error responses (``metadata.error = True``).
    """
    start = time.perf_counter()

    # ── Build initial state ──────────────────────────────────────────
    initial_state: OrchestratorState = {
        "state_prompt": state_prompt,
        "route": "",
        "agent_responses": [],
        "final_response": "",
        "agent_used": "",
    }

    try:
        # ── Execute the compiled graph ───────────────────────────────
        final_state = await compiled_graph.ainvoke(initial_state)
        elapsed = time.perf_counter() - start

        result = OrchestratorResult(
            final_response=final_state["final_response"],
            agent_used=final_state["agent_used"],
            route=final_state["route"],
            all_responses=final_state["agent_responses"],
            metadata={
                "latency_ms": round(elapsed * 1000, 1),
                "session_id": state_prompt.session_id,
                "student_id": state_prompt.student_id,
                "nodes_executed": len(final_state["agent_responses"]),
            },
        )

        logger.info(
            "✅ [Orchestrator] Pipeline execution complete!\n"
            "   ┝ Session:  %s\n"
            "   ┝ Route:    %s\n"
            "   ┝ Agent:    %s\n"
            "   ┝ Nodes:    %d\n"
            "   ┝ Latency:  %.0fms\n"
            "   ┕ Response: %s",
            state_prompt.session_id,
            result.route,
            result.agent_used,
            len(result.all_responses),
            elapsed * 1000,
            result.final_response.replace('\n', ' '),
        )

        return result

    except Exception:
        elapsed = time.perf_counter() - start
        logger.exception(
            "Orchestrator failed  session=%s  after=%.0fms",
            state_prompt.session_id,
            elapsed * 1000,
        )

        # Return a safe error result so the pipeline doesn't crash
        return OrchestratorResult(
            final_response="I'm having trouble right now. Let me try again in a moment! 🔄",
            agent_used="orchestrator",
            route="error",
            all_responses=[],
            metadata={
                "error": True,
                "latency_ms": round(elapsed * 1000, 1),
                "session_id": state_prompt.session_id,
            },
        )
