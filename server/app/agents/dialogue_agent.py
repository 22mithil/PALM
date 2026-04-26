"""
Dialogue Agent — sole output generator.

Runs unconditionally as the last agent. Reads orchestrator_intent.goal
and all non-null agent_outputs, then synthesizes a single student-facing
message. This is the ONLY agent that writes to state.final_message.
"""

import logging

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are Pal, a warm and friendly AI math tutor for Grade {grade} primary school students.

Your job is to synthesize a single, cohesive response to the student.
You will receive:
- The orchestrator's goal (what you should accomplish this turn)
- Outputs from other agents (hints, quiz questions, corrections, encouragement)
- The current section's content for reference
- Recent conversation history

Rules:
1. Weave all agent outputs into ONE natural, conversational message.
2. Write in plain prose — no bullet points, no numbered lists.
3. Use warm, grade-appropriate language. Imagine talking to a {grade}-year-old.
4. Keep the response under 150 words unless explaining a concept for the first time.
5. Use 1–2 emojis maximum.
6. If introducing a concept (goal mentions "introduce"), use the section's explanation.
7. If a quiz question is provided, present it naturally — don't just dump it.
8. If a correction is provided, incorporate it gently.
9. If encouragement is provided, blend it naturally at the start.
10. Never say "the agent said" or reference internal systems.
11. Address the student directly with "you".
12. Format math with $$ for LaTeX when needed.\
"""

_USER_TEMPLATE = """\
GOAL: {goal}

SECTION: {section_title} — {concept}
SECTION EXPLANATION: {explanation}

AGENT OUTPUTS:
{agent_outputs}

SESSION SUMMARY: {summary}

RECENT CONVERSATION:
{recent}

STUDENT'S MESSAGE: {student_message}

Generate your response to the student.\
"""


async def run_dialogue(state: TurnState) -> None:
    """Synthesize the final student-facing message."""
    # Collect agent outputs
    outputs_parts = []
    ao = state.agent_outputs
    if ao.hint:
        outputs_parts.append(f"[HINT]: {ao.hint}")
    if ao.quiz:
        outputs_parts.append(f"[QUIZ]: {ao.quiz}")
    if ao.correction:
        outputs_parts.append(f"[CORRECTION]: {ao.correction}")
    if ao.encouragement:
        outputs_parts.append(f"[ENCOURAGEMENT]: {ao.encouragement}")
    if ao.engagement:
        outputs_parts.append(f"[ENGAGEMENT]: {ao.engagement}")

    agent_outputs_text = "\n".join(outputs_parts) if outputs_parts else "(none)"

    # Section info
    section_title = ""
    concept = ""
    explanation = ""
    if state.current_section:
        section_title = state.current_section.title
        concept = state.current_section.concept
        explanation = state.current_section.explanation[:500]

    # Recent conversation
    recent = ""
    for msg in state.last_10_messages[-6:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")[:200]
        recent += f"  {role}: {content}\n"
    if not recent:
        recent = "  (first message of session)"

    goal = state.orchestrator_intent.goal or "Continue the conversation"

    try:
        text = await generate_response(
            _USER_TEMPLATE.format(
                goal=goal,
                section_title=section_title,
                concept=concept,
                explanation=explanation,
                agent_outputs=agent_outputs_text,
                summary=state.session_summary or "(none)",
                recent=recent,
                student_message=state.student_message or "(session start — introduce yourself and the concept)",
            ),
            system_prompt=_SYSTEM_PROMPT.format(grade=state.grade),
            temperature=0.7,
            max_tokens=512,
        )
        state.final_message = text
        logger.info("Dialogue agent: generated %d chars", len(text))
    except Exception:
        logger.exception("Dialogue agent failed — using fallback")
        state.final_message = (
            "That's a great question! 🌟 "
            "Let me think about the best way to explain this. "
            "Can you tell me what part is most confusing? "
            "We'll figure it out together! 💪"
        )
