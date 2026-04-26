"""
Hint Agent — non-LLM progressive hint system.

Reads ``hint_progression`` from the current section and uses
``state.hint_count`` as the array index (capped at 2).
No LLM call — pure data lookup.
"""

import logging

from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)


async def run_hint(state: TurnState) -> None:
    """Read the next hint from hint_progression and write to agent_outputs.hint."""
    if not state.current_section or not state.current_section.hint_progression:
        logger.warning("No hint_progression available for current section")
        state.agent_outputs.hint = "Let me try to help you think about this differently."
        return

    hints = state.current_section.hint_progression
    # Cap index at len-1 (max index 2 for a 3-element array)
    idx = min(state.hint_count, len(hints) - 1)

    state.agent_outputs.hint = hints[idx]
    state.hint_count = min(state.hint_count + 1, len(hints))

    logger.info(
        "Hint agent: tier=%d/%d  section=%s",
        idx + 1,
        len(hints),
        state.current_section.section_id,
    )
