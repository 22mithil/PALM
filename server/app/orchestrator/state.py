"""
Orchestrator Graph State — the shared ``TypedDict`` that flows through
every node in the LangGraph ``StateGraph``.

All nodes read from and write to this state dict.  LangGraph merges
returned partial dicts into the running state automatically.

Fields
------
state_prompt : StatePrompt
    The validated, immutable input context built by the StatePrompt
    Builder.  Nodes should treat this as read-only.

route : str
    The route selected by the router node.  Set once by the router
    and consumed by conditional edges to decide the next node.

agent_responses : list[AgentResponse]
    Accumulated responses from every agent node that ran.  Each node
    *appends* its response so chain routes (e.g. RAG → Dialogue)
    preserve the full pipeline output.

final_response : str
    The text returned to the student — set by the *last* node in
    the route.

agent_used : str
    Name of the primary agent that produced the final response.
"""

from __future__ import annotations

from typing import Annotated

from typing_extensions import TypedDict

from app.agents.base import AgentResponse
from app.schemas.state_prompt import StatePrompt


def _append_responses(
    existing: list[AgentResponse],
    new: list[AgentResponse],
) -> list[AgentResponse]:
    """Reducer: append new responses to the existing list.

    LangGraph calls this reducer when a node returns
    ``{"agent_responses": [resp]}``.  Instead of *replacing* the list,
    we concatenate so chain routes accumulate all outputs.
    """
    return existing + new


class OrchestratorState(TypedDict):
    """Shared state flowing through the orchestrator graph."""

    state_prompt: StatePrompt
    route: str
    agent_responses: Annotated[list[AgentResponse], _append_responses]
    final_response: str
    agent_used: str
