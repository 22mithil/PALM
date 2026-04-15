"""
Correctness Validator — LLM-based math accuracy checker.

Compares the agent's response text against RAG-retrieved curriculum
context to detect mathematical inaccuracies or fabricated facts.

The check uses a lightweight LLM call with a strict JSON schema to
produce a binary pass/fail verdict plus an explanation.

Usage::

    from app.validators.correctness import check_correctness

    result = await check_correctness(
        response_text="2 + 2 = 5",
        rag_context="Addition: 2 + 2 = 4",
    )
    print(result.is_valid)   # False
    print(result.reason)     # "States 2+2=5 but curriculum says 2+2=4"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.integrations.fastrouter.llm import generate_response

logger = logging.getLogger(__name__)


# ── Result ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CorrectnessResult:
    """Outcome of a math-correctness check.

    Attributes
    ----------
    is_valid : bool
        ``True`` if the response is mathematically consistent with the
        RAG context (or if no math content is present to validate).
    reason : str
        Short explanation — empty when valid.
    """

    is_valid: bool
    reason: str = ""


# ── System prompt for the checker LLM ────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a strict math-accuracy auditor. Your ONLY job is to compare a \
tutor's response against retrieved curriculum context and decide if the \
math content is correct.

Rules:
1. Focus ONLY on mathematical statements, equations, and numeric facts.
2. If the response contains NO mathematical content, it is automatically VALID.
3. Minor phrasing differences are acceptable — only flag actual math errors.
4. Invented or fabricated mathematical facts not supported by the context \
   count as INVALID.

Respond with ONLY a JSON object (no markdown fences):
{"is_valid": true}          — if math is correct or absent
{"is_valid": false, "reason": "..."}  — if there is a math error\
"""

_USER_TEMPLATE = """\
[Curriculum Context]
{context}

---

[Tutor Response to Validate]
{response}\
"""

_NO_CONTEXT_PASS = CorrectnessResult(is_valid=True, reason="no_rag_context")


# ── Public API ───────────────────────────────────────────────────────────


async def check_correctness(
    response_text: str,
    rag_context: str,
    *,
    model: str | None = None,
) -> CorrectnessResult:
    """Check whether *response_text* is mathematically consistent with
    the *rag_context*.

    Parameters
    ----------
    response_text : str
        The agent's response text to validate.
    rag_context : str
        Concatenated RAG curriculum chunks used to ground the response.
    model : str, optional
        LLM model override (defaults to FastRouter default).

    Returns
    -------
    CorrectnessResult
        Pass/fail verdict with optional reason.
    """
    # Fast-path: nothing to validate
    if not response_text.strip():
        return CorrectnessResult(is_valid=True, reason="empty_response")

    if not rag_context.strip():
        return _NO_CONTEXT_PASS

    prompt = _USER_TEMPLATE.format(
        context=rag_context,
        response=response_text,
    )

    try:
        raw = await generate_response(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            model=model,
            temperature=0.0,      # deterministic for validation
            max_tokens=256,
        )

        result = _parse_llm_json(raw)
        logger.debug("Correctness check: %s", result)
        return result

    except Exception:
        logger.exception("Correctness check failed — defaulting to VALID")
        # Fail-open: don't block the pipeline on a validator crash
        return CorrectnessResult(is_valid=True, reason="checker_error")


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_llm_json(raw: str) -> CorrectnessResult:
    """Best-effort parse of the LLM's JSON verdict."""
    # Strip markdown fences if the model wraps output
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Correctness LLM returned non-JSON: %s", text[:200])
        return CorrectnessResult(is_valid=True, reason="parse_error")

    is_valid = bool(data.get("is_valid", True))
    reason = str(data.get("reason", "")) if not is_valid else ""
    return CorrectnessResult(is_valid=is_valid, reason=reason)
