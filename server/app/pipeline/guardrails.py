"""
Guardrails — hard rules applied after the orchestrator.

Overrides or augments the orchestrator's intent based on
non-negotiable conditions (e.g., prolonged gaze away).
"""

import logging

from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)


def apply_guardrails(state: TurnState) -> None:
    """Apply hard guardrails to the orchestrator intent.

    Currently enforces:
    - If ``consecutive_gaze_away >= 2``, prepend "engagement" to
      supporting_agents so the dialogue agent includes re-engagement.
    """
    intent = state.orchestrator_intent

    # ── Gaze guardrail ───────────────────────────────────────────────
    if state.consecutive_gaze_away >= 2:
        if "engagement" not in intent.supporting_agents:
            intent.supporting_agents.insert(0, "engagement")
            logger.info(
                "Guardrail: injected engagement agent (gaze_away=%d)",
                state.consecutive_gaze_away,
            )
