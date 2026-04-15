"""
Response Validation Pipeline — orchestrates correctness + tone checks
with retry logic and RAG fallback.

This is the single entry-point called after the Orchestrator produces a
response.  It validates the ``final_response`` and, if invalid, retries
the LLM up to ``MAX_RETRIES`` times.  If validation still fails after
retries, it falls back to a safe, RAG-grounded answer.

Flow::

    final_response
         │
    ┌────▼────┐     pass
    │ validate ├─────────► return validated text
    └────┬────┘
         │ fail
    ┌────▼────────┐
    │ retry LLM   │  (up to MAX_RETRIES times)
    │ + validate   │
    └────┬────────┘
         │ still failing
    ┌────▼────────────┐
    │ fallback to RAG │  (curriculum-grounded safe answer)
    └─────────────────┘

Usage::

    from app.validators.pipeline import validate_response

    validated = await validate_response(
        response_text="2 + 2 = 5!",
        state_prompt=state_prompt,
        rag_context="Addition: 2 + 2 = 4",
        agent_name="dialogue_agent",
    )
    print(validated.text)        # corrected answer
    print(validated.was_retried) # True
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.integrations.fastrouter.llm import generate_response
from app.schemas.state_prompt import StatePrompt
from app.validators.correctness import check_correctness, CorrectnessResult
from app.validators.tone import check_tone, ToneResult

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_RETRIES = 2

# ── Result ───────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Outcome of the full validation pipeline.

    Attributes
    ----------
    text : str
        The final validated (or fallback) response text.
    is_valid : bool
        ``True`` if the response passed all checks (possibly after retry).
    was_retried : bool
        ``True`` if the initial response failed and a retry was attempted.
    used_fallback : bool
        ``True`` if all retries failed and the RAG fallback was used.
    retry_count : int
        Number of LLM retries performed.
    correctness : CorrectnessResult | None
        Result of the math-correctness check.
    tone : ToneResult | None
        Result of the tone-safety check.
    metadata : dict
        Additional metadata (latency, failure reasons, etc.).
    """

    text: str
    is_valid: bool = True
    was_retried: bool = False
    used_fallback: bool = False
    retry_count: int = 0
    correctness: CorrectnessResult | None = None
    tone: ToneResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Retry system prompt ─────────────────────────────────────────────────

_RETRY_SYSTEM_PROMPT = """\
You are Pal, a friendly AI math tutor for primary school students \
(Grades 1–5). A previous response was rejected by our safety system.

IMPORTANT RULES:
1. ONLY use the [Curriculum Context] to answer — never invent math facts.
2. Use simple, child-friendly language.
3. Be encouraging and positive. No harsh or negative language.
4. Keep your response under 150 words.
5. Use Socratic scaffolding — guide, don't just give answers.\
"""

_RETRY_USER_TEMPLATE = """\
[Curriculum Context]
{context}

[Rejection Reason]
{reason}

[Original Student Query]
{query}

Please provide a corrected, child-friendly response.\
"""

# ── RAG fallback prompt ─────────────────────────────────────────────────

_FALLBACK_SYSTEM_PROMPT = """\
You are Pal, a kind and patient math tutor for primary school children. \
Generate a simple, safe, encouraging response based STRICTLY on the \
curriculum context below. Keep it under 100 words. Use easy vocabulary.\
"""

_FALLBACK_USER_TEMPLATE = """\
[Curriculum Context]
{context}

[Student Query]
{query}

Provide a helpful, curriculum-grounded response.\
"""

_HARD_FALLBACK = (
    "That's a great question! 🌟 "
    "Let me think about the best way to explain this. "
    "Can you tell me what part is most confusing? "
    "We'll figure it out together! 💪"
)


# ── Public API ───────────────────────────────────────────────────────────


async def validate_response(
    response_text: str,
    state_prompt: StatePrompt,
    rag_context: str = "",
    agent_name: str = "unknown",
) -> ValidationResult:
    """Validate an agent's response for correctness and tone.

    Runs math-correctness and tone checks in parallel.  If either fails,
    retries the LLM up to ``MAX_RETRIES`` times with explicit correction
    instructions.  If retries are exhausted, falls back to a safe
    RAG-grounded answer.

    Parameters
    ----------
    response_text : str
        The agent's response text to validate.
    state_prompt : StatePrompt
        The original state prompt (provides query, topic, grade context).
    rag_context : str
        Concatenated RAG curriculum chunks (for correctness comparison
        and fallback generation).
    agent_name : str
        Name of the agent that produced the response (for logging).

    Returns
    -------
    ValidationResult
        Contains the validated (or corrected/fallback) text plus
        detailed check results and metadata.
    """
    start = time.perf_counter()

    # ── First pass ───────────────────────────────────────────────────
    correctness, tone = await _run_checks(response_text, rag_context)

    if correctness.is_valid and tone.is_valid:
        elapsed = time.perf_counter() - start
        logger.info(
            "Validation PASSED  agent=%s  session=%s  latency=%.0fms",
            agent_name,
            state_prompt.session_id,
            elapsed * 1000,
        )
        return ValidationResult(
            text=response_text,
            is_valid=True,
            correctness=correctness,
            tone=tone,
            metadata={"latency_ms": round(elapsed * 1000, 1)},
        )

    # ── Retry loop ───────────────────────────────────────────────────
    failure_reasons = _collect_reasons(correctness, tone)
    logger.warning(
        "Validation FAILED  agent=%s  session=%s  reasons=%s — retrying",
        agent_name,
        state_prompt.session_id,
        failure_reasons,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        retry_text = await _retry_llm(
            query=state_prompt.query,
            rag_context=rag_context,
            failure_reason=failure_reasons,
        )

        correctness, tone = await _run_checks(retry_text, rag_context)

        if correctness.is_valid and tone.is_valid:
            elapsed = time.perf_counter() - start
            logger.info(
                "Validation PASSED after %d retry(ies)  agent=%s  "
                "session=%s  latency=%.0fms",
                attempt,
                agent_name,
                state_prompt.session_id,
                elapsed * 1000,
            )
            return ValidationResult(
                text=retry_text,
                is_valid=True,
                was_retried=True,
                retry_count=attempt,
                correctness=correctness,
                tone=tone,
                metadata={"latency_ms": round(elapsed * 1000, 1)},
            )

        failure_reasons = _collect_reasons(correctness, tone)
        logger.warning(
            "Retry %d/%d still invalid  agent=%s  reasons=%s",
            attempt,
            MAX_RETRIES,
            agent_name,
            failure_reasons,
        )

    # ── Fallback to RAG answer ───────────────────────────────────────
    fallback_text = await _generate_fallback(
        query=state_prompt.query,
        rag_context=rag_context,
    )
    elapsed = time.perf_counter() - start

    logger.warning(
        "All retries exhausted — using RAG fallback  agent=%s  "
        "session=%s  latency=%.0fms",
        agent_name,
        state_prompt.session_id,
        elapsed * 1000,
    )

    return ValidationResult(
        text=fallback_text,
        is_valid=False,
        was_retried=True,
        used_fallback=True,
        retry_count=MAX_RETRIES,
        correctness=correctness,
        tone=tone,
        metadata={
            "latency_ms": round(elapsed * 1000, 1),
            "fallback_reason": failure_reasons,
        },
    )


# ── Internal helpers ─────────────────────────────────────────────────────


async def _run_checks(
    text: str,
    rag_context: str,
) -> tuple[CorrectnessResult, ToneResult]:
    """Run correctness and tone checks concurrently."""
    import asyncio

    correctness_task = asyncio.create_task(
        check_correctness(text, rag_context)
    )
    tone_task = asyncio.create_task(check_tone(text))

    correctness = await correctness_task
    tone = await tone_task
    return correctness, tone


def _collect_reasons(
    correctness: CorrectnessResult,
    tone: ToneResult,
) -> str:
    """Merge failure reasons from both checks into a single string."""
    parts: list[str] = []
    if not correctness.is_valid:
        parts.append(f"Math error: {correctness.reason}")
    if not tone.is_valid:
        parts.append(f"Tone issue: {tone.reason}")
    return "; ".join(parts) or "unknown"


async def _retry_llm(
    query: str,
    rag_context: str,
    failure_reason: str,
) -> str:
    """Re-generate the response with explicit correction instructions."""
    context = rag_context if rag_context.strip() else "No curriculum context available."

    prompt = _RETRY_USER_TEMPLATE.format(
        context=context,
        reason=failure_reason,
        query=query,
    )

    try:
        return await generate_response(
            prompt,
            system_prompt=_RETRY_SYSTEM_PROMPT,
            temperature=0.5,      # slightly less creative for safety
            max_tokens=512,
        )
    except Exception:
        logger.exception("Retry LLM call failed")
        return ""


async def _generate_fallback(
    query: str,
    rag_context: str,
) -> str:
    """Generate a safe, RAG-grounded fallback answer.

    If even the fallback LLM call fails, returns a hard-coded safe
    message.
    """
    if not rag_context.strip():
        return _HARD_FALLBACK

    prompt = _FALLBACK_USER_TEMPLATE.format(
        context=rag_context,
        query=query,
    )

    try:
        return await generate_response(
            prompt,
            system_prompt=_FALLBACK_SYSTEM_PROMPT,
            temperature=0.3,      # conservative for safety
            max_tokens=256,
        )
    except Exception:
        logger.exception("Fallback LLM call failed — using hard fallback")
        return _HARD_FALLBACK
