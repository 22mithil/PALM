"""
Pipeline Runner — the 13-step linear turn pipeline.

This is the single entry-point that replaces the old LangGraph
orchestrator. It assembles state, runs all steps in order, and
returns the final message.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curriculum import Chapter
from app.models.mastery import StudentProgress
from app.models.session import StudentSession
from app.models.student import Student
from app.pipeline.answer_checker import check_answer
from app.pipeline.guardrails import apply_guardrails
from app.pipeline.orchestrator import run_orchestrator
from app.pipeline.section_loader import load_section
from app.pipeline.state import (
    AgentOutputs,
    ChapterProgress,
    SectionStatus,
    TurnState,
)
from app.pipeline.summary import maybe_regenerate_summary
from app.services.session_context import session_context_manager
from app.evaluation.turn_logger import turn_logger
from app.integrations.fastrouter.llm import reset_token_counter, get_token_usage

logger = logging.getLogger(__name__)


async def run_turn_pipeline(
    student_id: str,
    session_id: str,
    student_message: str,
    db: AsyncSession,
    response_time_ms: float | None = None,
) -> str:
    """Execute the full 13-step turn pipeline.

    Parameters
    ----------
    student_id : str
        UUID string of the student.
    session_id : str
        UUID string of the current session.
    student_message : str
        The student's message for this turn (may be empty on session start).
    db : AsyncSession
        Active SQLAlchemy async session.

    Returns
    -------
    str
        The final tutor message to send to the student.
    """
    t_start = time.perf_counter()

    # Reset per-turn token counter
    reset_token_counter()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Load student, session, progress from DB → assemble TurnState
    # ═══════════════════════════════════════════════════════════════════
    student_uuid = uuid.UUID(student_id)
    session_uuid = uuid.UUID(session_id)

    # Load student
    student_row = await db.execute(
        select(Student).where(Student.id == student_uuid)
    )
    student = student_row.scalars().first()
    if not student:
        logger.error("Student %s not found", student_id)
        return "Sorry, I couldn't find your student profile. Please try again."

    # Load session
    session_row = await db.execute(
        select(StudentSession).where(StudentSession.id == session_uuid)
    )
    session = session_row.scalars().first()
    if not session:
        logger.error("Session %s not found", session_id)
        return "Sorry, I couldn't find your session. Please try again."

    # Load progress
    chapter_id = session.chapter_id or 0
    progress = None
    if chapter_id:
        progress_row = await db.execute(
            select(StudentProgress).where(
                StudentProgress.student_id == student_uuid,
                StudentProgress.chapter_id == chapter_id,
            )
        )
        progress = progress_row.scalars().first()

        # Auto-create progress if missing
        if progress is None:
            chapter_row = await db.execute(
                select(Chapter).where(Chapter.chapter_id == chapter_id)
            )
            chapter = chapter_row.scalars().first()
            if chapter and chapter.section_ids:
                first_section = chapter.section_ids[0]
                section_statuses = {
                    sid: {"status": "not_started"}
                    for sid in chapter.section_ids
                }
                progress = StudentProgress(
                    student_id=student_uuid,
                    chapter_id=chapter_id,
                    current_section_id=first_section,
                    section_statuses=section_statuses,
                    completion_percent=0.0,
                )
                db.add(progress)
                await db.flush()
                await db.refresh(progress)
                logger.info("Auto-created progress for student=%s chapter=%d", student_id, chapter_id)

    # ── Issue 5: Early return if chapter already 100% and fully mastered ────
    if progress and progress.completion_percent and progress.completion_percent >= 100:
        if not progress.was_completed:
            # Mark as completed on first hit
            progress.was_completed = True
            await db.flush()
        if student_message.strip():
            # Check if a section was specifically reset for review
            raw_statuses = progress.section_statuses or {}
            has_not_started = any(
                isinstance(v, dict) and v.get('status') in ('not_started', 'introduced', 'in_progress')
                for v in raw_statuses.values()
            )
            if not has_not_started:
                return "🎉 You've already mastered this chapter! Head back to the dashboard to explore more topics, or click Restart to practice again."

    # Get perception from session_context_manager
    emotion = "neutral"
    emotion_conf = 0.0
    gaze = "focused"
    session_ctx = session_context_manager.get(session_id)
    if session_ctx:
        perception = await session_ctx.get_perception()
        emotion = perception.emotion_label
        emotion_conf = perception.emotion_confidence
        gaze_raw = perception.gaze
        # Normalize gaze values
        if gaze_raw in ("off_screen", "looking_away"):
            gaze = "looking_away"
        elif gaze_raw in ("on_screen", "focused"):
            gaze = "focused"
        else:
            gaze = gaze_raw or "focused"

    # Compute session duration
    duration_mins = 0.0
    if session.started_at:
        delta = datetime.now(timezone.utc) - session.started_at.replace(
            tzinfo=timezone.utc if session.started_at.tzinfo is None else session.started_at.tzinfo
        )
        duration_mins = delta.total_seconds() / 60.0

    # Build chapter_progress
    chapter_progress = None
    if progress:
        section_statuses_parsed = {}
        raw_statuses = progress.section_statuses or {}
        for sid, val in raw_statuses.items():
            if isinstance(val, dict):
                section_statuses_parsed[sid] = SectionStatus(
                    status=val.get("status", "not_started")
                )
            else:
                section_statuses_parsed[sid] = SectionStatus(status="not_started")

        chapter_progress = ChapterProgress(
            chapter_id=progress.chapter_id,
            current_section_id=progress.current_section_id,
            section_statuses=section_statuses_parsed,
            completion_percent=progress.completion_percent or 0.0,
            was_completed=progress.was_completed,
        )

    # Assemble TurnState
    state = TurnState(
        student_id=student_id,
        session_id=session_id,
        student_name=student.name,
        grade=student.grade,
        student_message=student_message,
        emotion=emotion,
        emotion_confidence=emotion_conf,
        gaze=gaze,
        consecutive_gaze_away=0,  # computed below
        attempt_count=0,  # will be set by answer checker
        hint_count=0,
        turn_count=session.turn_count or 0,
        session_duration_mins=duration_mins,
        last_answer_correct=None,
        last_10_messages=session.last_10_messages or [],
        session_summary=session.session_summary or "",
        chapter_id=chapter_id,
        chapter_progress=chapter_progress,
        asked_questions=session.asked_questions or [],
        previous_agent_outputs_quiz=None,
        response_time_ms=response_time_ms,
    )

    # Check if previous turn had quiz output by inspecting last assistant message
    if state.last_10_messages:
        last_msgs = state.last_10_messages
        # Look for quiz marker in recent messages
        for msg in reversed(last_msgs):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "[QUIZ]" in content:
                    state.previous_agent_outputs_quiz = content
                break

    # ── Compute consecutive_gaze_away from recent history ────────────
    # (Simple: if gaze is away this turn, increment; otherwise reset)
    # We track this on a session-level counter stored in-memory
    if session_ctx and hasattr(session_ctx, '_gaze_away_turns'):
        if gaze == "looking_away":
            session_ctx._gaze_away_turns += 1
        else:
            session_ctx._gaze_away_turns = 0
        state.consecutive_gaze_away = session_ctx._gaze_away_turns
    else:
        if session_ctx:
            session_ctx._gaze_away_turns = 1 if gaze == "looking_away" else 0
            state.consecutive_gaze_away = session_ctx._gaze_away_turns

    logger.info(
        "Pipeline START  session=%s  turn=%d  msg=%s",
        session_id,
        state.turn_count,
        repr(student_message[:60]) if student_message else "(empty)",
    )

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Append student message to last_10_messages
    # ═══════════════════════════════════════════════════════════════════
    if student_message.strip():
        state.last_10_messages.append({
            "role": "user",
            "content": student_message,
        })
        # Also append to all_messages for full history (Issue 6)
        if not hasattr(session, '_all_msgs_buffer'):
            session._all_msgs_buffer = list(session.all_messages or [])
        session._all_msgs_buffer.append({"role": "student", "content": student_message})
        # Trim last_10 to 10
        if len(state.last_10_messages) > 10:
            state.last_10_messages = state.last_10_messages[-10:]

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Load current section content
    # ═══════════════════════════════════════════════════════════════════
    _t3 = time.perf_counter()
    await load_section(state, db)
    _lat_section_loader = (time.perf_counter() - _t3) * 1000

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Check summary regeneration
    # ═══════════════════════════════════════════════════════════════════
    _t4 = time.perf_counter()
    await maybe_regenerate_summary(state)
    _lat_summary = (time.perf_counter() - _t4) * 1000

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4.5: Answer checking (before orchestrator)
    # ═══════════════════════════════════════════════════════════════════
    _t45 = time.perf_counter()
    await check_answer(state)
    _lat_answer_check = (time.perf_counter() - _t45) * 1000

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: Run LLM orchestrator
    # ═══════════════════════════════════════════════════════════════════
    _t5 = time.perf_counter()
    await run_orchestrator(state)
    _lat_orchestrator = (time.perf_counter() - _t5) * 1000

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: Apply guardrails
    # ═══════════════════════════════════════════════════════════════════
    apply_guardrails(state)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 7: Run selected agents
    # ═══════════════════════════════════════════════════════════════════
    from app.agents.hint_agent import run_hint
    from app.agents.quiz_agent import run_quiz
    from app.agents.correction_agent import run_correction
    from app.agents.encouragement_agent import run_encouragement
    from app.agents.engagement_agent import run_engagement

    intent = state.orchestrator_intent
    all_agents = [intent.primary_agent] + intent.supporting_agents

    for agent_name in all_agents:
        if agent_name == "hint":
            await run_hint(state)
        elif agent_name == "quiz":
            await run_quiz(state)
        elif agent_name == "correction":
            await run_correction(state)
        elif agent_name == "encouragement":
            await run_encouragement(state)
        elif agent_name == "engagement":
            await run_engagement(state)
        elif agent_name == "dialogue":
            pass  # Dialogue runs unconditionally in step 9

    # ═══════════════════════════════════════════════════════════════════
    # STEP 8: Run mastery agent (unconditional side-effect)
    # ═══════════════════════════════════════════════════════════════════
    _t8 = time.perf_counter()
    from app.agents.mastery_agent import run_mastery
    await run_mastery(state, db)
    _lat_mastery = (time.perf_counter() - _t8) * 1000

    # ═══════════════════════════════════════════════════════════════════
    # STEP 8.5: Issue D — If chapter just hit 100%, send celebration
    # ═══════════════════════════════════════════════════════════════════
    chapter_just_completed = (
        state.chapter_progress
        and state.chapter_progress.completion_percent >= 100
    )

    if chapter_just_completed:
        # Skip dialogue agent — send celebration message directly
        state.final_message = (
            "🎉 Amazing work! You've mastered every section in this chapter! "
            "You should be incredibly proud — you answered questions, worked through "
            "tricky concepts, and showed real understanding. "
            "Head back to the dashboard to explore more topics, "
            "or click Restart to practice any section again. You're a math superstar! 🌟"
        )
        logger.info("Chapter complete! Skipping dialogue agent, sending celebration.")
    else:
        # ═══════════════════════════════════════════════════════════════════
        # STEP 9: Run dialogue agent (unconditional, sole output generator)
        # ═══════════════════════════════════════════════════════════════════
        _t9 = time.perf_counter()
        from app.agents.dialogue_agent import run_dialogue
        await run_dialogue(state)
        _lat_dialogue = (time.perf_counter() - _t9) * 1000

    # ═══════════════════════════════════════════════════════════════════
    # STEP 10: Append tutor message to last_10_messages
    # ═══════════════════════════════════════════════════════════════════
    if state.final_message:
        state.last_10_messages.append({
            "role": "assistant",
            "content": state.final_message,
        })
        # Also append to all_messages (Issue 6)
        if not hasattr(session, '_all_msgs_buffer'):
            session._all_msgs_buffer = list(session.all_messages or [])
        session._all_msgs_buffer.append({"role": "tutor", "content": state.final_message})
        if len(state.last_10_messages) > 10:
            state.last_10_messages = state.last_10_messages[-10:]

    # ═══════════════════════════════════════════════════════════════════
    # STEP 11: Write session + progress back to DB
    # ═══════════════════════════════════════════════════════════════════
    session.turn_count = state.turn_count + 1
    session.last_10_messages = state.last_10_messages
    session.all_messages = getattr(session, '_all_msgs_buffer', session.all_messages or [])
    session.session_summary = state.session_summary
    session.asked_questions = state.asked_questions

    if progress and state.chapter_progress:
        progress.current_section_id = state.chapter_progress.current_section_id
        progress.section_statuses = {
            sid: {"status": ss.status}
            for sid, ss in state.chapter_progress.section_statuses.items()
        }
        progress.completion_percent = state.chapter_progress.completion_percent
        progress.last_updated = datetime.now(timezone.utc)
        # Issue 7/8: Mark was_completed when first reaching 100%
        if state.chapter_progress.completion_percent >= 100 and not progress.was_completed:
            progress.was_completed = True

    await db.flush()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 12: Clear agent_outputs (for next turn)
    # ═══════════════════════════════════════════════════════════════════
    agents_fired = [intent.primary_agent] + intent.supporting_agents
    state.agent_outputs = AgentOutputs()

    elapsed = (time.perf_counter() - t_start) * 1000
    logger.info(
        "Pipeline DONE  session=%s  turn=%d  latency=%.0fms  chars=%d",
        session_id,
        state.turn_count,
        elapsed,
        len(state.final_message),
    )

    # ═══════════════════════════════════════════════════════════════════
    # STEP 12.5: Log turn snapshot for evaluation
    # ═══════════════════════════════════════════════════════════════════
    try:
        step_latencies = {
            "section_loader_ms": round(_lat_section_loader, 1),
            "summary_regen_ms": round(_lat_summary, 1),
            "answer_checker_ms": round(_lat_answer_check, 1),
            "orchestrator_ms": round(_lat_orchestrator, 1),
            "mastery_agent_ms": round(_lat_mastery, 1),
            "dialogue_agent_ms": round(locals().get('_lat_dialogue', 0), 1),
        }
        turn_logger.log_turn(
            state,
            pipeline_latency_ms=elapsed,
            step_latencies=step_latencies,
            agents_fired=agents_fired,
            token_usage=get_token_usage(),
        )
    except Exception:
        logger.debug("Evaluation logger failed (non-critical)", exc_info=True)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 13: Return final_message
    # ═══════════════════════════════════════════════════════════════════
    return state.final_message
