"""
Synthetic Session Runner — headless multi-agent evaluation.

Simulates a student (LLM-powered persona) chatting with the PALM
tutor pipeline, collecting metrics and generating reports.

Usage:
    python -m scripts.run_synthetic_eval --persona frustrated_struggler --chapter 1
    python -m scripts.run_synthetic_eval --all --chapter 1
    python -m scripts.run_synthetic_eval --persona bored_genius --chapter 1 --max-turns 15
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.session import async_session_factory
from app.evaluation.llm_judge import judge_session
from app.evaluation.metrics_engine import compute_session_metrics
from app.evaluation.personas import PERSONAS, PERSONA_NAMES, get_persona
from app.evaluation.report_generator import (
    generate_batch_report,
    generate_session_report,
)
from app.evaluation.session_analyzer import analyze_session
from app.evaluation.turn_logger import turn_logger
from app.integrations.fastrouter.llm import generate_response
from app.models.student import Student
from app.pipeline.runner import run_turn_pipeline
from app.services.session_context import session_context_manager
from app.services import session_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
logger = logging.getLogger("synthetic_eval")

# ── Constants ────────────────────────────────────────────────────────────
DEFAULT_MAX_TURNS = 20
EVAL_ROOT = Path(__file__).resolve().parents[2] / "evaluations"


# ═════════════════════════════════════════════════════════════════════════
# Student Agent — LLM-powered simulated student
# ═════════════════════════════════════════════════════════════════════════

class StudentAgent:
    """Uses an LLM to simulate a student with a specific persona."""

    def __init__(self, persona_key: str):
        self.persona = get_persona(persona_key)
        self.persona_key = persona_key
        self.history: list[dict] = []
        self.turn = 0

    async def respond(self, tutor_message: str) -> dict:
        """Generate a student response given the tutor's last message.

        Returns {"text": str, "emotion": str, "gaze": str}
        """
        self.turn += 1

        # Build conversation for the student LLM
        messages = [
            {"role": "system", "content": self.persona["system_prompt"]},
        ]

        # Add conversation history
        for entry in self.history[-10:]:
            messages.append({"role": "assistant", "content": json.dumps(entry["student"])})
            messages.append({"role": "user", "content": entry["tutor"]})

        # Current tutor message
        messages.append({
            "role": "user",
            "content": f"[Turn {self.turn}] The tutor says:\n{tutor_message}\n\nRespond as your character in JSON.",
        })

        raw = await generate_response(
            "",  # prompt ignored when messages provided
            messages=messages,
            temperature=0.8,
            max_tokens=256,
        )

        # Parse JSON response
        parsed = self._parse_response(raw)

        # Track history
        self.history.append({
            "student": parsed,
            "tutor": tutor_message,
        })

        return parsed

    def _parse_response(self, raw: str) -> dict:
        """Extract JSON from LLM output, with fallbacks."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            data = json.loads(raw)
            return {
                "text": str(data.get("text", "I don't know")),
                "emotion": str(data.get("emotion", "neutral")),
                "gaze": str(data.get("gaze", "focused")),
            }
        except json.JSONDecodeError:
            logger.warning("Student LLM returned non-JSON: %s", raw[:100])
            return {"text": raw[:100], "emotion": "neutral", "gaze": "focused"}


# ═════════════════════════════════════════════════════════════════════════
# Simulation Loop
# ═════════════════════════════════════════════════════════════════════════

async def run_simulation(
    persona_key: str,
    chapter_id: int,
    max_turns: int = DEFAULT_MAX_TURNS,
    grade: int = 4,
) -> dict:
    """Run a single simulated session.

    Returns the computed metrics dict (including LLM judge scores).
    """
    test_id = f"{persona_key}_{int(time.time())}"
    persona = get_persona(persona_key)

    logger.info("=" * 70)
    logger.info("SIMULATION: %s (%s)", persona["name"], persona_key)
    logger.info("Chapter: %d | Max turns: %d | Test ID: %s", chapter_id, max_turns, test_id)
    logger.info("=" * 70)

    student_agent = StudentAgent(persona_key)

    async with async_session_factory() as db:
        try:
            # ── Find or create a test student ────────────────────────
            from sqlalchemy import select, delete
            from app.models.mastery import StudentProgress

            test_email = f"synthetic_{persona_key}@palm-eval.test"
            result = await db.execute(
                select(Student).where(Student.email == test_email)
            )
            student = result.scalars().first()

            if not student:
                student = Student(
                    name=f"[EVAL] {persona['name']}",
                    email=test_email,
                    password_hash="synthetic_no_login",
                    grade=grade,
                    age=9,
                )
                db.add(student)
                await db.flush()
                await db.refresh(student)
                logger.info("Created test student: %s (id=%s)", student.name, student.id)

            student_id = str(student.id)

            # ── Reset chapter progress for clean run ─────────────────
            await db.execute(
                delete(StudentProgress)
                .where(StudentProgress.student_id == student.id)
                .where(StudentProgress.chapter_id == chapter_id)
            )
            await db.commit()

            # ── Create a session ─────────────────────────────────────
            session = await session_service.create_session(
                db,
                student_id=student.id,
                chapter_id=chapter_id,
                grade=grade,
            )
            session_id = str(session.id)
            logger.info("Created session: %s", session_id)

            # ── Register perception context ──────────────────────────
            ctx = await session_context_manager.get_or_create(session_id)

            # ── Run the conversation loop ────────────────────────────
            tutor_message = ""

            for turn in range(max_turns):
                # Step 1: Get initial tutor greeting (turn 0) or run pipeline
                if turn == 0:
                    tutor_message = await run_turn_pipeline(
                        student_id=student_id,
                        session_id=session_id,
                        student_message="",
                        db=db,
                    )
                    logger.info("[Turn 0] TUTOR: %s", tutor_message[:120])
                    await db.commit()
                    continue

                # Step 2: Student agent generates response
                student_response = await student_agent.respond(tutor_message)
                student_text = student_response["text"]
                emotion = student_response["emotion"]
                gaze = student_response["gaze"]

                logger.info(
                    "[Turn %d] STUDENT (%s, %s): %s",
                    turn, emotion, gaze, student_text[:80],
                )

                # Step 3: Inject perception into session context
                gaze_mapped = "off_screen" if gaze == "looking_away" else "on_screen"
                await ctx.update_perception(
                    emotion_label=emotion,
                    emotion_confidence=0.85,
                    gaze=gaze_mapped,
                )

                # Step 4: Run the PALM pipeline
                tutor_message = await run_turn_pipeline(
                    student_id=student_id,
                    session_id=session_id,
                    student_message=student_text,
                    db=db,
                )
                await db.commit()

                logger.info("[Turn %d] TUTOR: %s", turn, tutor_message[:120])

                # Check if chapter completed
                turns_data = turn_logger.get_session_turns(session_id)
                if turns_data:
                    last = turns_data[-1]
                    if last.get("completion_percent", 0) >= 100:
                        logger.info("Chapter mastered at turn %d! Ending.", turn)
                        break

            # ── Compute metrics ──────────────────────────────────────
            turns_data = turn_logger.get_session_turns(session_id)
            metrics = compute_session_metrics(turns_data)
            metrics["session_id"] = session_id
            metrics["persona"] = persona_key
            metrics["persona_name"] = persona["name"]
            metrics["target_test"] = persona["target_test"]

            # ── LLM Judge ────────────────────────────────────────────
            logger.info("Running LLM-as-a-Judge evaluation...")
            judge_scores = await judge_session(
                turns_data,
                student_persona_name=f"{persona['name']} ({persona_key})",
                student_grade=grade,
            )
            metrics["llm_judge_scores"] = judge_scores

            # ── Generate report ──────────────────────────────────────
            report_path = generate_session_report(
                session_id,
                metrics,
                session_type="synthetic",
                test_id=test_id,
            )
            metrics["report_path"] = str(report_path)

            # ── Write session log ────────────────────────────────────
            turn_logger.write_session_summary(
                session_id, session_type="synthetic", test_id=test_id,
            )

            # ── Cleanup ──────────────────────────────────────────────
            await session_context_manager.remove(session_id)

            logger.info("SIMULATION COMPLETE: %s", persona_key)
            logger.info("  Turns: %d", metrics.get("total_turns", 0))
            logger.info("  Accuracy: %.1f%%", metrics.get("accuracy_rate", 0) * 100)
            logger.info("  Talk Ratio: %.3f", metrics.get("student_tutor_talk_ratio", 0))
            logger.info("  Volatility: %.3f", metrics.get("affective_volatility", 0))
            if isinstance(judge_scores, dict) and "overall_score" in judge_scores:
                logger.info("  Judge Score: %.1f/10", judge_scores["overall_score"])
            logger.info("  Report: %s", report_path)

            return metrics

        except Exception:
            await db.rollback()
            logger.exception("Simulation failed for persona %s", persona_key)
            raise


# ═════════════════════════════════════════════════════════════════════════
# Batch Runner
# ═════════════════════════════════════════════════════════════════════════

async def run_all_personas(chapter_id: int, max_turns: int = DEFAULT_MAX_TURNS):
    """Run simulations for ALL personas and generate a batch report."""
    all_metrics = []

    for persona_key in PERSONA_NAMES:
        try:
            metrics = await run_simulation(persona_key, chapter_id, max_turns)
            all_metrics.append(metrics)
        except Exception:
            logger.error("Skipping %s due to error", persona_key)
            all_metrics.append({"persona": persona_key, "error": "failed"})

    # Generate batch report
    batch_id = f"batch_{int(time.time())}"
    report_path = generate_batch_report(batch_id, all_metrics)
    logger.info("=" * 70)
    logger.info("BATCH REPORT: %s", report_path)
    logger.info("=" * 70)

    return all_metrics


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="PALM Synthetic Session Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available personas: {', '.join(PERSONA_NAMES)}",
    )
    parser.add_argument(
        "--persona", "-p",
        choices=PERSONA_NAMES,
        help="Run a single persona simulation",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Run ALL persona simulations",
    )
    parser.add_argument(
        "--chapter", "-c",
        type=int, default=1,
        help="Chapter ID to use (default: 1)",
    )
    parser.add_argument(
        "--max-turns", "-t",
        type=int, default=DEFAULT_MAX_TURNS,
        help=f"Maximum turns per session (default: {DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--list-personas",
        action="store_true",
        help="List all available personas and exit",
    )

    args = parser.parse_args()

    if args.list_personas:
        print("\nAvailable Student Personas:")
        print("-" * 50)
        for key, p in PERSONAS.items():
            print(f"  {key:25s}  {p['name']:10s}  → {p['target_test']}")
        return

    if not args.persona and not args.all:
        parser.error("Specify --persona NAME or --all")

    if args.all:
        asyncio.run(run_all_personas(args.chapter, args.max_turns))
    else:
        asyncio.run(run_simulation(args.persona, args.chapter, args.max_turns))


if __name__ == "__main__":
    main()
