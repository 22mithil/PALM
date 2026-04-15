"""
Tone Validator — child-friendliness and language safety checker.

Uses a lightweight LLM call to evaluate whether the agent's response
is appropriate for a primary-school student:

    ✓ Age-appropriate vocabulary and sentence complexity
    ✓ Encouraging, positive tone
    ✗ Harsh, sarcastic, condescending, or negative language
    ✗ Profanity, slang, or adult themes

Usage::

    from app.validators.tone import check_tone

    result = await check_tone("Great job! You're almost there 🌟")
    print(result.is_valid)   # True

    result = await check_tone("That's a stupid mistake.")
    print(result.is_valid)   # False
    print(result.reason)     # "Uses the word 'stupid' ..."
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.integrations.fastrouter.llm import generate_response

logger = logging.getLogger(__name__)


# ── Result ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToneResult:
    """Outcome of a tone-safety check.

    Attributes
    ----------
    is_valid : bool
        ``True`` if the response is child-friendly and tonally safe.
    reason : str
        Short explanation — empty when valid.
    """

    is_valid: bool
    reason: str = ""


# ── System prompt for the checker LLM ────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a child-safety language auditor for an AI math tutor that serves \
primary-school children (ages 5–11).

Evaluate the tutor's response against these criteria:

PASS if ALL are true:
1. Language is age-appropriate (simple words, short sentences).
2. Tone is encouraging, patient, and positive.
3. No harsh, rude, sarcastic, or condescending language.
4. No profanity, slang, insults, or adult-only themes.
5. No shaming or discouraging phrases ("you should know this", "that's wrong").

FAIL if ANY criterion is violated.

Respond with ONLY a JSON object (no markdown fences):
{"is_valid": true}          — if the response is safe and child-friendly
{"is_valid": false, "reason": "..."}  — if there is a tone issue\
"""

_USER_TEMPLATE = """\
[Tutor Response to Evaluate]
{response}\
"""


# ── Blocklist fast-path ──────────────────────────────────────────────────

_BLOCKED_WORDS = frozenset({
    "stupid", "dumb", "idiot", "shut up", "loser", "pathetic",
    "moron", "fool", "hate", "ugly", "useless", "terrible",
    "awful", "disgust", "hell", "damn", "crap",
})


def _fast_blocklist_check(text: str) -> ToneResult | None:
    """Instant rejection if any blocked word is found (case-insensitive).

    Returns ``None`` if no blocked word is detected (proceed to LLM check).
    """
    lower = text.lower()
    for word in _BLOCKED_WORDS:
        if word in lower:
            return ToneResult(
                is_valid=False,
                reason=f"Contains blocked term: '{word}'",
            )
    return None


# ── Public API ───────────────────────────────────────────────────────────


async def check_tone(
    response_text: str,
    *,
    model: str | None = None,
) -> ToneResult:
    """Check whether *response_text* is child-friendly and tonally safe.

    Parameters
    ----------
    response_text : str
        The agent's response text to validate.
    model : str, optional
        LLM model override (defaults to FastRouter default).

    Returns
    -------
    ToneResult
        Pass/fail verdict with optional reason.
    """
    # Fast-path: nothing to validate
    if not response_text.strip():
        return ToneResult(is_valid=True, reason="empty_response")

    # Fast-path: blocklist scan (no LLM cost)
    blocklist_hit = _fast_blocklist_check(response_text)
    if blocklist_hit is not None:
        logger.warning("Tone blocklist hit: %s", blocklist_hit.reason)
        return blocklist_hit

    prompt = _USER_TEMPLATE.format(response=response_text)

    try:
        raw = await generate_response(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            model=model,
            temperature=0.0,      # deterministic for validation
            max_tokens=256,
        )

        result = _parse_llm_json(raw)
        logger.debug("Tone check: %s", result)
        return result

    except Exception:
        logger.exception("Tone check failed — defaulting to VALID")
        # Fail-open: don't block the pipeline on a validator crash
        return ToneResult(is_valid=True, reason="checker_error")


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_llm_json(raw: str) -> ToneResult:
    """Best-effort parse of the LLM's JSON verdict."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Tone LLM returned non-JSON: %s", text[:200])
        return ToneResult(is_valid=True, reason="parse_error")

    is_valid = bool(data.get("is_valid", True))
    reason = str(data.get("reason", "")) if not is_valid else ""
    return ToneResult(is_valid=is_valid, reason=reason)
