"""
Turn Logger — captures a full snapshot of every pipeline turn.

Hooks into runner.py at the END of each turn. Writes a JSON file
per turn into evaluations/sessions/live/ or evaluations/sessions/synthetic/.
Also accumulates per-session data for the MetricsEngine.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

# Root directory for all evaluation output
EVAL_ROOT = Path(__file__).resolve().parents[3] / "evaluations"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class TurnSnapshot:
    """Serialisable snapshot of one pipeline turn."""

    def __init__(
        self,
        state: TurnState,
        *,
        pipeline_latency_ms: float = 0.0,
        step_latencies: Optional[dict[str, float]] = None,
        agents_fired: Optional[list[str]] = None,
        session_type: str = "live",
        test_id: Optional[str] = None,
        token_usage: Optional[dict] = None,
    ):
        now = datetime.now(timezone.utc)

        self.data = {
            # ── Identity ──────────────────────────────────────────
            "timestamp": now.isoformat(),
            "session_id": state.session_id,
            "student_id": state.student_id,
            "student_name": state.student_name,
            "grade": state.grade,
            "session_type": session_type,
            "test_id": test_id,

            # ── Turn context ──────────────────────────────────────
            "turn_count": state.turn_count,
            "student_message": state.student_message,
            "final_message": state.final_message,

            # ── Perception ────────────────────────────────────────
            "emotion": state.emotion,
            "emotion_confidence": state.emotion_confidence,
            "gaze": state.gaze,
            "consecutive_gaze_away": state.consecutive_gaze_away,

            # ── Pipeline decisions ────────────────────────────────
            "orchestrator_intent": {
                "primary_agent": state.orchestrator_intent.primary_agent,
                "supporting_agents": state.orchestrator_intent.supporting_agents,
                "goal": state.orchestrator_intent.goal,
                "reasoning": state.orchestrator_intent.reasoning,
            },
            "agents_fired": agents_fired or [],

            # ── Answer evaluation ─────────────────────────────────
            "last_answer_correct": state.last_answer_correct,
            "attempt_count": state.attempt_count,
            "hint_count": state.hint_count,

            # ── Curriculum progress ───────────────────────────────
            "chapter_id": state.chapter_id,
            "current_section_id": (
                state.chapter_progress.current_section_id
                if state.chapter_progress else None
            ),
            "completion_percent": (
                state.chapter_progress.completion_percent
                if state.chapter_progress else 0.0
            ),
            "section_statuses": (
                {sid: ss.status for sid, ss in state.chapter_progress.section_statuses.items()}
                if state.chapter_progress else {}
            ),
            "was_completed": (
                state.chapter_progress.was_completed
                if state.chapter_progress else False
            ),

            # ── Current section info ──────────────────────────────
            "current_section_concept": (
                state.current_section.concept
                if state.current_section else None
            ),
            "current_section_title": (
                state.current_section.title
                if state.current_section else None
            ),
            "current_section_content": (
                state.current_section.explanation
                if state.current_section else None
            ),

            # ── Conversation context ──────────────────────────────
            "session_summary": state.session_summary,
            "message_history_length": len(state.last_10_messages),

            # ── Performance ───────────────────────────────────────
            "pipeline_latency_ms": round(pipeline_latency_ms, 1),
            "step_latencies": step_latencies or {},
            "response_time_ms": state.response_time_ms,

            # ── Token usage ───────────────────────────────────────
            "token_usage": token_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},

            # ── Word counts (for NLP metrics) ─────────────────────
            "student_word_count": len(state.student_message.split()) if state.student_message else 0,
            "tutor_word_count": len(state.final_message.split()) if state.final_message else 0,

            # ── Math formatting check ─────────────────────────────
            "has_katex": (
                "$$" in state.final_message or "\\(" in state.final_message
                if state.final_message else False
            ),
            "has_broken_katex": _check_broken_katex(state.final_message),
        }

    def to_dict(self) -> dict:
        return self.data


def _check_broken_katex(text: str) -> bool:
    """Quick heuristic: unmatched $$ or \\( delimiters."""
    if not text:
        return False
    # Check unmatched $$
    if text.count("$$") % 2 != 0:
        return True
    # Check unmatched \( \)
    if text.count("\\(") != text.count("\\)"):
        return True
    return False


class TurnLogger:
    """Singleton that logs turn snapshots to the filesystem.

    Usage from runner.py:
        from app.evaluation.turn_logger import turn_logger
        turn_logger.log_turn(state, pipeline_latency_ms=elapsed, ...)
    """

    def __init__(self):
        self._session_turns: dict[str, list[dict]] = {}

    def log_turn(
        self,
        state: TurnState,
        *,
        pipeline_latency_ms: float = 0.0,
        step_latencies: Optional[dict[str, float]] = None,
        agents_fired: Optional[list[str]] = None,
        session_type: str = "live",
        test_id: Optional[str] = None,
        token_usage: Optional[dict] = None,
    ) -> None:
        """Log a single turn snapshot to disk and memory."""
        snapshot = TurnSnapshot(
            state,
            pipeline_latency_ms=pipeline_latency_ms,
            step_latencies=step_latencies,
            agents_fired=agents_fired,
            session_type=session_type,
            test_id=test_id,
            token_usage=token_usage,
        )
        data = snapshot.to_dict()
        session_id = state.session_id

        # ── Accumulate in memory ──────────────────────────────────
        if session_id not in self._session_turns:
            self._session_turns[session_id] = []
        self._session_turns[session_id].append(data)

        # ── Write to filesystem ───────────────────────────────────
        try:
            session_dir = self._session_dir(session_id, session_type, test_id)

            # Write individual turn file
            turn_file = session_dir / f"turn_{state.turn_count:03d}.json"
            with open(turn_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(
                "Logged turn %d for session %s → %s",
                state.turn_count, session_id, turn_file,
            )
        except Exception:
            logger.exception("Failed to write turn log for session %s", session_id)

    # ── Path helpers ──────────────────────────────────────────────────

    @staticmethod
    def _session_dir(
        session_id: str,
        session_type: str = "live",
        test_id: Optional[str] = None,
    ) -> Path:
        """Return the organised directory for a session's files.

        Hierarchy:
          sessions/synthetic/{date}_{test_id}/session_{id8}/
          sessions/live/{date}/session_{id8}/
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        session_short = session_id[:8]

        if session_type == "synthetic":
            folder_name = f"{date_str}_{test_id or 'run'}"
            base = EVAL_ROOT / "sessions" / "synthetic" / folder_name
        else:
            base = EVAL_ROOT / "sessions" / "live" / date_str

        session_dir = base / f"session_{session_short}"
        return _ensure_dir(session_dir)

    def get_session_turns(self, session_id: str) -> list[dict]:
        """Return all logged turns for a session (from memory)."""
        return self._session_turns.get(session_id, [])

    def flush_session(self, session_id: str) -> list[dict]:
        """Pop and return all turns for a session."""
        return self._session_turns.pop(session_id, [])

    def write_session_summary(
        self,
        session_id: str,
        session_type: str = "live",
        test_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Write a combined JSON with ALL turns for one session."""
        turns = self._session_turns.get(session_id)
        if not turns:
            return None

        try:
            session_dir = self._session_dir(session_id, session_type, test_id)

            summary_file = session_dir / "full_session.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(turns, f, indent=2, ensure_ascii=False)

            logger.info(
                "Wrote session summary (%d turns) → %s",
                len(turns), summary_file,
            )
            return summary_file
        except Exception:
            logger.exception("Failed to write session summary for %s", session_id)
            return None


# ── Singleton ────────────────────────────────────────────────────────────
turn_logger = TurnLogger()
