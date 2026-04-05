"""
FastRouter — Text-to-Speech wrapper (stub).

Will integrate with FastRouter's TTS endpoint for child-friendly
voice synthesis. Currently raises NotImplementedError.
"""

import logging

logger = logging.getLogger(__name__)


async def synthesize_speech(
    text: str,
    *,
    voice: str = "alloy",
    model: str = "tts-1",
    response_format: str = "mp3",
) -> bytes:
    """Convert text to speech audio.

    Parameters
    ----------
    text : str
        The text to synthesize.
    voice : str
        Voice preset (e.g. ``"alloy"``, ``"echo"``, ``"nova"``).
    model : str
        TTS model identifier.
    response_format : str
        Audio format: ``"mp3"``, ``"opus"``, ``"aac"``, ``"flac"``.

    Returns
    -------
    bytes
        Raw audio bytes in the requested format.

    Raises
    ------
    NotImplementedError
        This is a stub — full implementation pending.
    """
    logger.warning("TTS stub called — not yet implemented.")
    raise NotImplementedError(
        "Text-to-Speech integration is not yet implemented. "
        "This stub will be replaced with FastRouter TTS API calls."
    )
