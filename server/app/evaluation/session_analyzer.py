"""
Session Analyzer — triggered when a session ends.

Pulls all logged turns from the TurnLogger, runs the MetricsEngine,
and generates a Markdown report via the ReportGenerator.

Can be called manually or hooked into the session-end API.
"""

import logging
from typing import Optional

from app.evaluation.turn_logger import turn_logger
from app.evaluation.metrics_engine import compute_session_metrics
from app.evaluation.report_generator import generate_session_report

logger = logging.getLogger(__name__)


def analyze_session(
    session_id: str,
    *,
    session_type: str = "live",
    test_id: Optional[str] = None,
) -> dict:
    """Run full analysis on a completed session.

    1. Retrieves all turn snapshots from the TurnLogger.
    2. Computes metrics via MetricsEngine.
    3. Generates a Markdown report.
    4. Writes the combined session log.

    Returns the computed metrics dict.
    """
    turns = turn_logger.get_session_turns(session_id)

    if not turns:
        logger.warning("No turns found for session %s — skipping analysis", session_id)
        return {"error": "no_turns", "session_id": session_id}

    # Compute metrics
    metrics = compute_session_metrics(turns)
    metrics["session_id"] = session_id
    metrics["session_type"] = session_type

    # Generate report
    try:
        report_path = generate_session_report(
            session_id,
            metrics,
            session_type=session_type,
            test_id=test_id,
        )
        metrics["report_path"] = str(report_path)
        logger.info(
            "Session analysis complete: %d turns, report → %s",
            len(turns), report_path,
        )
    except Exception:
        logger.exception("Report generation failed for session %s", session_id)

    # Write combined session log
    try:
        turn_logger.write_session_summary(
            session_id,
            session_type=session_type,
            test_id=test_id,
        )
    except Exception:
        logger.exception("Session summary write failed for session %s", session_id)

    return metrics
