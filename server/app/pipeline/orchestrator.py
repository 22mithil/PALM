"""
LLM Orchestrator — decides which agents to run and why.

Receives the full TurnState and produces a structured
``OrchestratorIntent`` with: primary_agent, supporting_agents,
goal, and reasoning.

Replaces the old hardcoded ``router.py`` with LLM-based reasoning.
"""

import json
import logging

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import OrchestratorIntent, TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the orchestrator for Pal, an AI math tutor for primary school students.

Your job is to decide which agent(s) should handle this turn based on the student's state.

Available agents:
- "dialogue" — general teaching, explanation, conversation (DEFAULT)
- "hint" — provide a progressive hint from the section's hint_progression
- "quiz" — present a quiz question from the section's quiz_questions
- "correction" — address a wrong answer using common_misconceptions
- "encouragement" — emotional support when student is frustrated
- "engagement" — re-engage a distracted or bored student

Rules:
1. If section status is "not_started", set goal to "introduce" — introduce the concept.
2. If student just answered wrong (last_answer_correct=false), primary_agent MUST be "correction".
3. If student asks for help/hint, primary_agent should be "hint".
4. If emotion is "frustrated" or "sad", include "encouragement" in supporting_agents.
5. After teaching a concept, consider giving a "quiz" to check understanding.
6. If the student seems to understand well, consider advancing with a quiz.
7. Keep goals concise (under 20 words).

Respond with ONLY a JSON object (no markdown):
{"primary_agent": "...", "supporting_agents": [...], "goal": "...", "reasoning": "..."}
"""

_USER_TEMPLATE = """\
Student: {name} (Grade {grade})
Section: {section_title} — {concept}
Section status: {section_status}
Turn count: {turn_count}
Emotion: {emotion} (confidence: {emotion_conf:.2f})
Gaze: {gaze} | Consecutive away: {gaze_away}
Last answer correct: {last_answer}
Attempt count: {attempt_count} | Hint count: {hint_count}
Session duration: {duration:.1f} min
Response time: {response_time}

Student message: {message}

Recent conversation:
{recent_messages}
"""


async def run_orchestrator(state: TurnState) -> None:
    """Run the LLM orchestrator and write intent to state."""
    section_title = ""
    concept = ""
    section_status = "not_started"

    if state.current_section:
        section_title = state.current_section.title
        concept = state.current_section.concept

    if state.chapter_progress and state.current_section:
        sid = state.current_section.section_id
        ss = state.chapter_progress.section_statuses.get(sid)
        if ss:
            section_status = ss.status

    # Format recent messages
    recent = ""
    for msg in state.last_10_messages[-6:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")[:150]
        recent += f"  {role}: {content}\n"
    if not recent:
        recent = "  (no prior messages)"

    last_answer = str(state.last_answer_correct) if state.last_answer_correct is not None else "N/A"

    user_prompt = _USER_TEMPLATE.format(
        name=state.student_name or "Student",
        grade=state.grade,
        section_title=section_title,
        concept=concept,
        section_status=section_status,
        turn_count=state.turn_count,
        emotion=state.emotion,
        emotion_conf=state.emotion_confidence,
        gaze=state.gaze,
        gaze_away=state.consecutive_gaze_away,
        last_answer=last_answer,
        attempt_count=state.attempt_count,
        hint_count=state.hint_count,
        duration=state.session_duration_mins,
        response_time=f"{int(state.response_time_ms)}ms" if state.response_time_ms else "N/A",
        message=state.student_message or "(empty — session start)",
        recent_messages=recent,
    )

    try:
        raw = await generate_response(
            user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=256,
        )

        # Parse JSON
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        state.orchestrator_intent = OrchestratorIntent(
            primary_agent=data.get("primary_agent", "dialogue"),
            supporting_agents=data.get("supporting_agents", []),
            goal=data.get("goal", ""),
            reasoning=data.get("reasoning", ""),
        )

        logger.info(
            "Orchestrator: primary=%s support=%s goal=%s",
            state.orchestrator_intent.primary_agent,
            state.orchestrator_intent.supporting_agents,
            state.orchestrator_intent.goal,
        )

    except Exception:
        logger.exception("Orchestrator LLM failed — defaulting to dialogue")
        state.orchestrator_intent = OrchestratorIntent(
            primary_agent="dialogue",
            supporting_agents=[],
            goal="Continue the tutoring conversation",
            reasoning="orchestrator_error",
        )
