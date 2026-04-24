"""
Orchestrator Graph — modular agent nodes + compiled LangGraph StateGraph.

Each node is a thin async wrapper around the corresponding agent
singleton.  Nodes read the ``StatePrompt`` from the graph state,
invoke the agent, and write back the ``AgentResponse``, ``final_response``,
and ``agent_used``.

Graph topology::

    START → router_node ──┬─ hint ──────────────── hint_node ──────────────────── END
                          ├─ engagement ─────────── engagement_node ────────────── END
                          ├─ mastery_remedial ───── mastery_remedial_node ──────── END
                          ├─ mastery_quiz ────────── mastery_advance_node → quiz_node → END
                          └─ rag_dialogue ────────── rag_node → dialogue_node ──── END

Usage::

    from app.orchestrator.graph import compiled_graph

    result = await compiled_graph.ainvoke(initial_state)
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.dialogue_agent import dialogue_agent
from app.agents.engagement_agent import engagement_agent
from app.agents.hint_agent import hint_agent
from app.agents.mastery_agent import mastery_agent
from app.agents.quiz_agent import quiz_agent
from app.agents.rag_agent import rag_agent

from app.orchestrator.router import (
    ROUTE_ENGAGEMENT,
    ROUTE_HINT,
    ROUTE_MASTERY_QUIZ,
    ROUTE_MASTERY_REMEDIAL,
    ROUTE_RAG_DIALOGUE,
    route_student,
)
from app.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  AGENT NODES
#  Each node: read state_prompt → call agent → write response fields
# ═══════════════════════════════════════════════════════════════════════════


async def router_node(state: OrchestratorState) -> dict[str, Any]:
    """Compute the route and store it in state.

    This node does NOT call any agent — it only sets the ``route``
    field so the subsequent conditional edges can branch.
    """
    route = route_student(state)
    return {"route": route}


# ── Single-node routes ──────────────────────────────────────────────────


async def hint_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the Hint Agent (progressive 3-tier hints)."""
    prompt = state["state_prompt"]
    response = await hint_agent(prompt)

    logger.info(
        "🤖 [Hint Node] Generated Tier %s Hint\n"
        "   ┕ Response: %s  session=%s",
        response.metadata.get("tier"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        "final_response": response.text,
        "agent_used": response.agent,
    }


async def engagement_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the Engagement Agent (fun re-engagement content)."""
    prompt = state["state_prompt"]
    response = await engagement_agent(prompt)

    logger.info(
        "🤖 [Engagement Node] Generated Content (%s)\n"
        "   ┕ Response: %s  session=%s",
        response.metadata.get("content_type"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        "final_response": response.text,
        "agent_used": response.agent,
    }


async def mastery_remedial_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the Mastery Agent in remedial mode (low mastery coaching)."""
    prompt = state["state_prompt"]
    response = await mastery_agent(prompt)

    logger.info(
        "🤖 [Mastery Remedial Node] Generated Coaching (Mode: %s)\n"
        "   ┕ Response: %s  session=%s",
        response.metadata.get("mode"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        "final_response": response.text,
        "agent_used": response.agent,
    }


# ── Chain route: mastery_quiz (mastery_advance → quiz) ───────────────────


async def mastery_advance_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the Mastery Agent for high-mastery coaching.

    This is the *first* node in the mastery_quiz chain.  It produces
    coaching text; the subsequent ``quiz_node`` generates the actual
    quiz question.
    """
    prompt = state["state_prompt"]
    response = await mastery_agent(prompt)

    logger.info(
        "🤖 [Mastery Advance Node] Generated Intro (Mode: %s)\n"
        "   ┕ Response: %s  session=%s",
        response.metadata.get("mode"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        # Don't set final_response — quiz_node will overwrite
        "final_response": response.text,
        "agent_used": response.agent,
    }


async def quiz_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the Quiz Agent (adaptive question generation).

    When used in the ``mastery_quiz`` chain, this runs *after*
    ``mastery_advance_node`` and produces the final response.
    """
    prompt = state["state_prompt"]
    response = await quiz_agent(prompt)

    # Combine mastery coaching + quiz into a single final response
    mastery_text = state.get("final_response", "")
    combined = f"{mastery_text}\n\n---\n\n{response.text}" if mastery_text else response.text

    logger.info(
        "🤖 [Quiz Node] Generated Question (Type: %s)\n"
        "   ┕ Question: %s  session=%s",
        response.metadata.get("question_type"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        "final_response": combined,
        "agent_used": response.agent,
    }


# ── Chain route: rag_dialogue (RAG → Dialogue) ──────────────────────────


async def rag_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the RAG Agent (curriculum-grounded retrieval).

    First node in the ``rag_dialogue`` chain.  Retrieves curriculum
    context and generates a grounded response that the Dialogue Agent
    can then refine.
    """
    prompt = state["state_prompt"]
    response = await rag_agent(prompt)

    logger.info(
        "🤖 [RAG Node] Retrieved Curriculum Context\n"
        "   ┝ Chunks loaded: %s\n"
        "   ┕ Response: %s  session=%s",
        response.metadata.get("chunks_after_rerank"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        "final_response": response.text,
        "agent_used": response.agent,
    }


async def dialogue_node(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the Dialogue Agent (Socratic conversational tutor).

    When used in the ``rag_dialogue`` chain, this runs *after*
    ``rag_node``.  The RAG context is already embedded in the
    StatePrompt's conversation history / session summary, so the
    Dialogue Agent naturally builds on it.
    """
    prompt = state["state_prompt"]
    response = await dialogue_agent(prompt)

    logger.info(
        "🤖 [Dialogue Node] Generated Conversational Response\n"
        "   ┝ Assumed Emotion: %s\n"
        "   ┕ Response: %s  session=%s",
        response.metadata.get("emotion"),
        response.text.replace('\n', ' '),
        prompt.session_id,
    )

    return {
        "agent_responses": [response],
        "final_response": response.text,
        "agent_used": response.agent,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  GRAPH DEFINITION
# ═══════════════════════════════════════════════════════════════════════════


def build_graph() -> StateGraph:
    """Construct the orchestrator StateGraph (uncompiled).

    Returns the graph builder so callers can inspect or extend it
    before compilation if needed.
    """

    graph = StateGraph(OrchestratorState)

    # ── Add all nodes ────────────────────────────────────────────────
    graph.add_node("router_node", router_node)
    graph.add_node("hint_node", hint_node)
    graph.add_node("engagement_node", engagement_node)
    graph.add_node("mastery_remedial_node", mastery_remedial_node)
    graph.add_node("mastery_advance_node", mastery_advance_node)
    graph.add_node("quiz_node", quiz_node)
    graph.add_node("rag_node", rag_node)
    graph.add_node("dialogue_node", dialogue_node)

    # ── Entry point ──────────────────────────────────────────────────
    graph.set_entry_point("router_node")

    # ── Conditional edges from router_node ───────────────────────────
    graph.add_conditional_edges(
        "router_node",
        lambda state: state["route"],
        {
            ROUTE_HINT: "hint_node",
            ROUTE_ENGAGEMENT: "engagement_node",
            ROUTE_MASTERY_REMEDIAL: "mastery_remedial_node",
            ROUTE_MASTERY_QUIZ: "mastery_advance_node",
            ROUTE_RAG_DIALOGUE: "rag_node",
        },
    )

    # ── Terminal edges (single-node routes) ──────────────────────────
    graph.add_edge("hint_node", END)
    graph.add_edge("engagement_node", END)
    graph.add_edge("mastery_remedial_node", END)

    # ── Chain edges (multi-node routes) ──────────────────────────────
    graph.add_edge("mastery_advance_node", "quiz_node")
    graph.add_edge("quiz_node", END)

    graph.add_edge("rag_node", "dialogue_node")
    graph.add_edge("dialogue_node", END)

    return graph


def compile_graph():
    """Build and compile the orchestrator graph (ready to invoke).

    Returns a compiled ``CompiledStateGraph`` that can be called via
    ``await compiled.ainvoke(state)`` or ``async for event in compiled.astream(state)``.
    """
    graph = build_graph()
    return graph.compile()


# ── Singleton compiled graph ─────────────────────────────────────────────
compiled_graph = compile_graph()
