"""
TurnState — the shared blackboard state object for the pipeline.

A fresh ``TurnState`` is assembled at the start of every turn from
DB records + perception signals.  It flows through all pipeline steps
and agents, accumulating outputs.  At the end of the turn, relevant
fields are persisted back to the database.

This replaces the old ``OrchestratorState`` (LangGraph TypedDict) and
``StatePrompt`` (Pydantic model) with a single unified schema.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Nested Sub-Models ────────────────────────────────────────────────────


class SectionStatus(BaseModel):
    """Status of a single section within a chapter."""
    status: str = Field(
        default="not_started",
        description="not_started | introduced | in_progress | struggling | mastered",
    )


class ChapterProgress(BaseModel):
    """Student's progress through a chapter — loaded from student_progress."""
    chapter_id: int
    current_section_id: str
    section_statuses: dict[str, SectionStatus] = Field(default_factory=dict)
    completion_percent: float = 0.0
    was_completed: bool = False


class CurrentSection(BaseModel):
    """Full content of the active section — loaded by the Section Loader."""
    section_id: str = ""
    chapter_id: int = 0
    order: int = 0
    concept: str = ""
    title: str = ""
    difficulty: str = "intro"
    prerequisite_concepts: list[str] = Field(default_factory=list)
    explanation: str = ""
    examples: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    hint_progression: list[str] = Field(default_factory=list)
    quiz_questions: list[dict[str, str]] = Field(default_factory=list)


class OrchestratorIntent(BaseModel):
    """Output of the LLM orchestrator — which agents to run and why."""
    primary_agent: str = "dialogue"
    supporting_agents: list[str] = Field(default_factory=list)
    goal: str = ""
    reasoning: str = ""


class AgentOutputs(BaseModel):
    """Accumulated outputs from agents during this turn."""
    hint: Optional[str] = None
    quiz: Optional[str] = None
    correction: Optional[str] = None
    encouragement: Optional[str] = None
    engagement: Optional[str] = None


# ── Main State Object ────────────────────────────────────────────────────


class TurnState(BaseModel):
    """Shared blackboard for one pipeline turn.

    Assembled fresh from the DB at the start of every turn.
    Modified in-place by pipeline steps and agents.
    Relevant fields are written back to the DB at the end.
    """

    # ── Identity ─────────────────────────────────────────────────────
    student_id: str
    session_id: str
    student_name: str = ""
    grade: int = 5

    # ── Student message ──────────────────────────────────────────────
    student_message: str = ""

    # ── Perception (from session_context_manager) ────────────────────
    emotion: str = "neutral"
    emotion_confidence: float = 0.0
    gaze: str = "focused"
    consecutive_gaze_away: int = 0

    # ── Session counters ─────────────────────────────────────────────
    attempt_count: int = 0
    hint_count: int = 0
    turn_count: int = 0
    session_duration_mins: float = 0.0

    # ── Answer evaluation ────────────────────────────────────────────
    last_answer_correct: Optional[bool] = None

    # ── Conversation history ─────────────────────────────────────────
    last_10_messages: list[dict[str, str]] = Field(default_factory=list)
    session_summary: str = ""

    # ── Curriculum context ───────────────────────────────────────────
    chapter_id: int = 0
    chapter_progress: Optional[ChapterProgress] = None
    current_section: Optional[CurrentSection] = None

    # ── Pipeline outputs ─────────────────────────────────────────────
    orchestrator_intent: OrchestratorIntent = Field(
        default_factory=OrchestratorIntent
    )
    agent_outputs: AgentOutputs = Field(default_factory=AgentOutputs)

    # ── Final output ─────────────────────────────────────────────────
    final_message: str = ""

    # ── Quiz context tracking ────────────────────────────────────────
    asked_questions: list[str] = Field(default_factory=list)
    previous_agent_outputs_quiz: Optional[str] = None

    # ── Response time tracking (Issue 4) ─────────────────────────────
    response_time_ms: Optional[float] = None
