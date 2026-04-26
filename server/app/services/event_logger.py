"""
Event logger — lightweight logging service.

With session_events table removed, this module provides console-level
logging only. The ``event_logger`` singleton maintains the same API
as the old DB-backed logger so callers (video_ws, stt_worker) don't
need changes.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EventLogger:
    """No-op event logger that logs to console instead of DB."""

    async def log_emotion(
        self,
        session_id: str,
        emotion_label: str = "neutral",
        gaze_status: str = "on_screen",
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "EMOTION  session=%s  emotion=%s  gaze=%s",
            session_id, emotion_label, gaze_status,
        )

    async def log_gaze(
        self,
        session_id: str,
        gaze_status: str = "on_screen",
        emotion_label: str = "neutral",
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "GAZE  session=%s  gaze=%s  emotion=%s",
            session_id, gaze_status, emotion_label,
        )

    async def log_query(
        self,
        session_id: str,
        query_text: str = "",
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "QUERY  session=%s  text=%s",
            session_id, repr(query_text[:60]),
        )

    async def log_response(
        self,
        session_id: str,
        response_text: str = "",
        agent_used: str = "",
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "RESPONSE  session=%s  agent=%s  text=%s",
            session_id, agent_used, repr(response_text[:60]),
        )

    def clear_session(self, session_id: str) -> None:
        logger.debug("CLEAR  session=%s", session_id)


# ── Singleton ────────────────────────────────────────────────────────────
event_logger = EventLogger()
