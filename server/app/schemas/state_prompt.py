"""
StatePrompt — DEPRECATED.

This module is kept as a thin stub for backwards compatibility.
The new architecture uses ``app.pipeline.state.TurnState`` instead.
"""

from app.pipeline.state import TurnState as StatePrompt  # noqa: F401

__all__ = ["StatePrompt"]
