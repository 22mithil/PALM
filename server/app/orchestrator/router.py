"""
Orchestrator Router — pure-function routing logic.

Inspects the ``OrchestratorState`` (specifically the ``StatePrompt``)
and returns a **route string** that LangGraph uses as a conditional
edge to decide which agent node(s) to invoke next.

Routing rules are evaluated in strict priority order:

    Priority  Condition                                    Route
    ────────  ─────────────────────────────────────────    ─────────────────
    1         frustrated AND consecutive_wrong ≥ 3         mastery_remedial
    2         gaze == off_screen (>3 s) OR bored           engagement
    3         confused OR consecutive_wrong ≥ 2            hint
    4         is_correct AND mastery ≥ 0.7 (confident)     mastery_quiz
    5         fallback — normal query                      rag_dialogue

Priority 1 is checked *before* 3 so a severely struggling student
gets remedial coaching, not just hints.
"""

from __future__ import annotations

import logging

from app.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)

# ── Route constants ──────────────────────────────────────────────────────

ROUTE_MASTERY_REMEDIAL = "mastery_remedial"
ROUTE_ENGAGEMENT = "engagement"
ROUTE_HINT = "hint"
ROUTE_MASTERY_QUIZ = "mastery_quiz"
ROUTE_RAG_DIALOGUE = "rag_dialogue"

ALL_ROUTES = frozenset({
    ROUTE_MASTERY_REMEDIAL,
    ROUTE_ENGAGEMENT,
    ROUTE_HINT,
    ROUTE_MASTERY_QUIZ,
    ROUTE_RAG_DIALOGUE,
})

# ── Thresholds ───────────────────────────────────────────────────────────

_FRUSTRATED_WRONG_THRESHOLD = 3   # consecutive wrong answers
_CONFUSED_WRONG_THRESHOLD = 2     # consecutive wrong answers
_CONFIDENT_MASTERY_THRESHOLD = 0.7  # mastery score considered "confident"


# ── Router function ─────────────────────────────────────────────────────


def route_student(state: OrchestratorState) -> str:
    """Determine which agent route to take based on student state.

    This is the **conditional edge function** used by the LangGraph
    ``StateGraph``.  It reads the ``state_prompt`` from the graph state
    and returns one of the ``ROUTE_*`` constants.

    Parameters
    ----------
    state : OrchestratorState
        The current graph state containing the ``StatePrompt``.

    Returns
    -------
    str
        One of: ``mastery_remedial``, ``engagement``, ``hint``,
        ``mastery_quiz``, ``rag_dialogue``.
    """
    prompt = state["state_prompt"]

    emotion = prompt.emotion.label.lower()
    gaze = prompt.gaze
    consecutive_wrong = prompt.consecutive_wrong
    is_correct = prompt.is_correct
    mastery = prompt.mastery_score

    # ── Priority 1: Frustrated + many wrong → remedial ───────────────
    if emotion == "frustrated" and consecutive_wrong >= _FRUSTRATED_WRONG_THRESHOLD:
        logger.info(
            "Route: %s  (emotion=%s, consecutive_wrong=%d)  session=%s",
            ROUTE_MASTERY_REMEDIAL, emotion, consecutive_wrong,
            prompt.session_id,
        )
        return ROUTE_MASTERY_REMEDIAL

    # ── Priority 2: Disengaged (gaze away / bored) → engagement ──────
    if gaze == "off_screen" or emotion == "bored":
        logger.info(
            "Route: %s  (gaze=%s, emotion=%s)  session=%s",
            ROUTE_ENGAGEMENT, gaze, emotion,
            prompt.session_id,
        )
        return ROUTE_ENGAGEMENT

    # ── Priority 3: Confused OR 2+ wrong → hint ─────────────────────
    if emotion == "confused" or consecutive_wrong >= _CONFUSED_WRONG_THRESHOLD:
        logger.info(
            "Route: %s  (emotion=%s, consecutive_wrong=%d)  session=%s",
            ROUTE_HINT, emotion, consecutive_wrong,
            prompt.session_id,
        )
        return ROUTE_HINT

    # ── Priority 4: Correct + confident mastery → mastery → quiz ─────
    if is_correct is True and mastery >= _CONFIDENT_MASTERY_THRESHOLD:
        logger.info(
            "Route: %s  (correct=%s, mastery=%.2f)  session=%s",
            ROUTE_MASTERY_QUIZ, is_correct, mastery,
            prompt.session_id,
        )
        return ROUTE_MASTERY_QUIZ

    # ── Priority 5: Normal query → RAG → dialogue ───────────────────
    logger.info(
        "Route: %s  (fallback)  session=%s",
        ROUTE_RAG_DIALOGUE,
        prompt.session_id,
    )
    return ROUTE_RAG_DIALOGUE
