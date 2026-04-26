"""
Session Summary Generator — LLM-compressed session summary.

Triggered every 5 turns or on concept change. Compresses recent
conversation into a concise ≤80-word summary for context carryover.
"""

import logging

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are summarizing a tutoring session for a primary school math student.
Produce a concise summary (under 80 words) capturing:
- What concepts were covered
- What the student understood well
- What the student struggled with
- Current learning state

Write in third person. Be factual and concise.\
"""

_USER_TEMPLATE = """\
Existing summary: {existing}

Recent messages:
{messages}

Update the summary to include the new information.\
"""


async def maybe_regenerate_summary(state: TurnState) -> None:
    """Regenerate session summary if conditions are met.

    Conditions: every 5 turns OR first turn (turn_count == 0).
    """
    if state.turn_count > 0 and state.turn_count % 5 != 0:
        return

    existing = state.session_summary or "(no prior summary)"

    # Format last 5 messages
    recent = state.last_10_messages[-5:]
    msg_text = ""
    for m in recent:
        role = m.get("role", "?")
        content = m.get("content", "")[:200]
        msg_text += f"{role}: {content}\n"

    if not msg_text.strip():
        return

    try:
        summary = await generate_response(
            _USER_TEMPLATE.format(
                existing=existing,
                messages=msg_text,
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=150,
        )
        state.session_summary = summary.strip()
        logger.info("Summary regenerated at turn %d", state.turn_count)
    except Exception:
        logger.exception("Summary regeneration failed — keeping existing")
