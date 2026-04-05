"""
FastRouter — Speech-to-Text wrapper (stub).

Will integrate with FastRouter's Whisper-compatible STT endpoint.
Currently raises NotImplementedError to flag unfinished integration.
"""

import logging

logger = logging.getLogger(__name__)


async def transcribe_audio(
    audio_bytes: bytes,
    *,
    language: str = "en",
    model: str = "whisper-1",
) -> str:
    """Transcribe audio bytes to text.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio data (WAV / WebM / MP3).
    language : str
        BCP-47 language code. Default ``"en"``.
    model : str
        STT model identifier.

    Returns
    -------
    str
        Transcribed text.

    Raises
    ------
    NotImplementedError
        This is a stub — full implementation pending.
    """
    logger.warning("STT stub called — not yet implemented.")
    raise NotImplementedError(
        "Speech-to-Text integration is not yet implemented. "
        "This stub will be replaced with FastRouter Whisper API calls."
    )
