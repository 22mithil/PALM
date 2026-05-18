"""
Metrics Engine — computes all quantitative and qualitative metrics
from a list of turn snapshots for a single session.

Metrics computed:
  Efficiency:       Turns to Mastery (TTM), Agent Activation Distribution
  NLP:              Student-Tutor Talk Ratio, Vocabulary Adoption Rate
  Perception:       Affective Volatility, Time-to-Boredom
  Pipeline Health:  Avg Latency, Math Formatting Error Rate, Context Compression
  Curriculum:       Section Bottleneck Detection, Hint Exhaustion Rate
  Pedagogy:         Intervention Success Rate
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# Math vocabulary that we track for Vocabulary Adoption
MATH_VOCABULARY = {
    "add", "subtract", "multiply", "divide", "sum", "difference",
    "product", "quotient", "fraction", "numerator", "denominator",
    "decimal", "percent", "equation", "equal", "greater", "less",
    "angle", "triangle", "rectangle", "square", "circle", "area",
    "perimeter", "volume", "length", "width", "height", "digit",
    "place value", "ones", "tens", "hundreds", "thousands",
    "remainder", "carry", "borrow", "half", "quarter", "third",
    "whole", "part", "ratio", "pattern", "symmetry", "data",
    "graph", "table", "chart", "average", "mean", "even", "odd",
}


def compute_session_metrics(turns: list[dict]) -> dict:
    """Compute all metrics from a list of turn snapshot dicts.

    Parameters
    ----------
    turns : list[dict]
        Ordered list of turn snapshots (from TurnLogger).

    Returns
    -------
    dict
        Dictionary of all computed metrics.
    """
    if not turns:
        return {"error": "no_turns"}

    metrics = {}

    # ═══════════════════════════════════════════════════════════════
    # 1. EFFICIENCY METRICS
    # ═══════════════════════════════════════════════════════════════
    metrics["total_turns"] = len(turns)
    metrics["turns_to_mastery"] = _compute_ttm(turns)
    metrics["agent_activation_distribution"] = _compute_agent_distribution(turns)

    # ═══════════════════════════════════════════════════════════════
    # 2. CONVERSATIONAL / NLP METRICS
    # ═══════════════════════════════════════════════════════════════
    student_words = [t.get("student_word_count", 0) for t in turns]
    tutor_words = [t.get("tutor_word_count", 0) for t in turns]

    avg_student = sum(student_words) / len(student_words) if student_words else 0
    avg_tutor = sum(tutor_words) / len(tutor_words) if tutor_words else 0

    metrics["avg_student_words_per_turn"] = round(avg_student, 1)
    metrics["avg_tutor_words_per_turn"] = round(avg_tutor, 1)
    metrics["student_tutor_talk_ratio"] = (
        round(avg_student / avg_tutor, 3) if avg_tutor > 0 else 0.0
    )
    metrics["vocabulary_adoption"] = _compute_vocabulary_adoption(turns)

    # ═══════════════════════════════════════════════════════════════
    # 3. PERCEPTION / EMOTION METRICS
    # ═══════════════════════════════════════════════════════════════
    metrics["affective_volatility"] = _compute_affective_volatility(turns)
    metrics["time_to_boredom_turn"] = _compute_time_to_boredom(turns)
    metrics["engagement_recovery_rate"] = _compute_engagement_recovery(turns)
    metrics["emotion_distribution"] = _compute_emotion_distribution(turns)
    metrics["gaze_away_percentage"] = _compute_gaze_away_pct(turns)

    # ═══════════════════════════════════════════════════════════════
    # 4. PIPELINE HEALTH METRICS
    # ═══════════════════════════════════════════════════════════════
    latencies = [t.get("pipeline_latency_ms", 0) for t in turns if t.get("pipeline_latency_ms")]
    if latencies:
        sorted_lat = sorted(latencies)
        metrics["latency_avg_ms"] = round(sum(sorted_lat) / len(sorted_lat), 1)
        metrics["latency_p50_ms"] = round(sorted_lat[len(sorted_lat) // 2], 1)
        metrics["latency_p95_ms"] = round(sorted_lat[int(len(sorted_lat) * 0.95)], 1)
        metrics["latency_max_ms"] = round(sorted_lat[-1], 1)
    else:
        metrics["latency_avg_ms"] = 0
        metrics["latency_p50_ms"] = 0
        metrics["latency_p95_ms"] = 0
        metrics["latency_max_ms"] = 0

    katex_turns = [t for t in turns if t.get("has_katex")]
    broken = [t for t in turns if t.get("has_broken_katex")]
    metrics["katex_usage_count"] = len(katex_turns)
    metrics["katex_broken_count"] = len(broken)
    metrics["math_formatting_error_rate"] = (
        round(len(broken) / len(katex_turns), 3) if katex_turns else 0.0
    )

    # ═══════════════════════════════════════════════════════════════
    # 5. CURRICULUM QUALITY METRICS
    # ═══════════════════════════════════════════════════════════════
    metrics["section_bottlenecks"] = _compute_section_bottlenecks(turns)
    metrics["hint_exhaustion_rate"] = _compute_hint_exhaustion(turns)

    # ═══════════════════════════════════════════════════════════════
    # 6. PEDAGOGY METRICS
    # ═══════════════════════════════════════════════════════════════
    metrics["intervention_success_rate"] = _compute_intervention_success(turns)

    # ═══════════════════════════════════════════════════════════════
    # 7. ANSWER METRICS
    # ═══════════════════════════════════════════════════════════════
    answered = [t for t in turns if t.get("last_answer_correct") is not None]
    correct = [t for t in answered if t.get("last_answer_correct") is True]
    metrics["total_answers_evaluated"] = len(answered)
    metrics["correct_answers"] = len(correct)
    metrics["accuracy_rate"] = (
        round(len(correct) / len(answered), 3) if answered else 0.0
    )

    # ═══════════════════════════════════════════════════════════════
    # 8. COMPLETION TRAJECTORY
    # ═══════════════════════════════════════════════════════════════
    metrics["completion_trajectory"] = [
        {"turn": t.get("turn_count", i), "percent": t.get("completion_percent", 0)}
        for i, t in enumerate(turns)
    ]
    metrics["final_completion_percent"] = turns[-1].get("completion_percent", 0)

    # ═══════════════════════════════════════════════════════════════
    # 9. TOKEN CONSUMPTION (Cost & Efficiency)
    # ═══════════════════════════════════════════════════════════════
    total_prompt = sum(t.get("token_usage", {}).get("prompt_tokens", 0) for t in turns)
    total_completion = sum(t.get("token_usage", {}).get("completion_tokens", 0) for t in turns)
    total_tokens = sum(t.get("token_usage", {}).get("total_tokens", 0) for t in turns)
    metrics["token_consumption"] = {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "avg_tokens_per_turn": round(total_tokens / len(turns), 1) if turns else 0,
    }

    return metrics



# ── Helper Functions ─────────────────────────────────────────────────────


def _compute_ttm(turns: list[dict]) -> dict:
    """Turns to Mastery — per section and overall."""
    # Count the number of turns where current_section_id was equal to sid
    # before it reached "mastered" status. 
    section_turns_to_mastery: dict[str, int] = {}
    
    current_counts: dict[str, int] = Counter()
    
    for t in turns:
        sid = t.get("current_section_id")
        statuses = t.get("section_statuses", {})
        
        if sid:
            current_counts[sid] += 1
            
        for s_id, status in statuses.items():
            if status == "mastered" and s_id not in section_turns_to_mastery:
                section_turns_to_mastery[s_id] = current_counts[s_id]

    avg = round(sum(section_turns_to_mastery.values()) / len(section_turns_to_mastery), 1) if section_turns_to_mastery else 0
    return {"per_section": section_turns_to_mastery, "average": avg}


def _compute_agent_distribution(turns: list[dict]) -> dict:
    """Count how often each agent was the primary_agent."""
    counter = Counter()
    for t in turns:
        intent = t.get("orchestrator_intent", {})
        primary = intent.get("primary_agent", "unknown")
        counter[primary] += 1
        for sa in intent.get("supporting_agents", []):
            counter[sa] += 1
    total = sum(counter.values()) or 1
    return {
        agent: {"count": count, "percent": round(count / total * 100, 1)}
        for agent, count in counter.most_common()
    }


def _compute_affective_volatility(turns: list[dict]) -> float:
    """Number of emotion label changes divided by total turns."""
    if len(turns) < 2:
        return 0.0
    changes = sum(
        1 for i in range(1, len(turns))
        if turns[i].get("emotion") != turns[i - 1].get("emotion")
    )
    return round(changes / len(turns), 3)


def _compute_time_to_boredom(turns: list[dict]) -> Optional[int]:
    """Turn index where 'bored' or 'looking_away' first appears."""
    for i, t in enumerate(turns):
        if t.get("emotion") == "bored" or t.get("gaze") == "looking_away":
            return i
    return None  # Never bored


def _compute_engagement_recovery(turns: list[dict]) -> float:
    """After an engagement agent fires, how often does gaze return to focused?"""
    engagement_indices = []
    for i, t in enumerate(turns):
        intent = t.get("orchestrator_intent", {})
        agents = [intent.get("primary_agent", "")] + intent.get("supporting_agents", [])
        if "engagement" in agents:
            engagement_indices.append(i)

    if not engagement_indices:
        return 1.0  # No engagement needed — perfect

    recovered = 0
    for idx in engagement_indices:
        # Check next 2 turns for recovery
        for j in range(idx + 1, min(idx + 3, len(turns))):
            if turns[j].get("gaze") == "focused" and turns[j].get("emotion") != "bored":
                recovered += 1
                break

    return round(recovered / len(engagement_indices), 3)


def _compute_emotion_distribution(turns: list[dict]) -> dict:
    """Percentage breakdown of each emotion across all turns."""
    counter = Counter(t.get("emotion", "unknown") for t in turns)
    total = len(turns) or 1
    return {
        emotion: {"count": count, "percent": round(count / total * 100, 1)}
        for emotion, count in counter.most_common()
    }


def _compute_gaze_away_pct(turns: list[dict]) -> float:
    """Percentage of turns where gaze was not focused."""
    if not turns:
        return 0.0
    away = sum(1 for t in turns if t.get("gaze") != "focused")
    return round(away / len(turns) * 100, 1)


def _compute_vocabulary_adoption(turns: list[dict]) -> dict:
    """Track which math terms the tutor introduced and the student adopted."""
    tutor_introduced: dict[str, int] = {}  # word -> turn introduced
    student_adopted: dict[str, int] = {}   # word -> turn adopted

    for i, t in enumerate(turns):
        tutor_text = (t.get("final_message") or "").lower()
        student_text = (t.get("student_message") or "").lower()

        for word in MATH_VOCABULARY:
            if word in tutor_text and word not in tutor_introduced:
                tutor_introduced[word] = i
            if word in student_text and word in tutor_introduced and word not in student_adopted:
                student_adopted[word] = i

    adoption_delays = {}
    for word, adopted_turn in student_adopted.items():
        introduced_turn = tutor_introduced.get(word, 0)
        adoption_delays[word] = adopted_turn - introduced_turn

    return {
        "terms_introduced_by_tutor": len(tutor_introduced),
        "terms_adopted_by_student": len(student_adopted),
        "adoption_rate": (
            round(len(student_adopted) / len(tutor_introduced), 3)
            if tutor_introduced else 0.0
        ),
        "avg_adoption_delay_turns": (
            round(sum(adoption_delays.values()) / len(adoption_delays), 1)
            if adoption_delays else 0.0
        ),
    }


def _compute_section_bottlenecks(turns: list[dict]) -> list[dict]:
    """Find sections that took disproportionately many turns."""
    section_turns: dict[str, int] = Counter()
    for t in turns:
        sid = t.get("current_section_id")
        if sid:
            section_turns[sid] += 1

    if not section_turns:
        return []

    avg = sum(section_turns.values()) / len(section_turns)
    bottlenecks = []
    for sid, count in section_turns.most_common():
        bottlenecks.append({
            "section_id": sid,
            "turns_spent": count,
            "is_bottleneck": count > avg * 1.5,
        })
    return bottlenecks


def _compute_hint_exhaustion(turns: list[dict]) -> dict:
    """How often hints are given vs how often max hints are reached."""
    hint_turns = [t for t in turns if t.get("hint_count", 0) > 0]
    max_hint_turns = [t for t in turns if t.get("hint_count", 0) >= 3]
    return {
        "turns_with_hints": len(hint_turns),
        "turns_at_max_hints": len(max_hint_turns),
        "exhaustion_rate": (
            round(len(max_hint_turns) / len(hint_turns), 3)
            if hint_turns else 0.0
        ),
    }


def _compute_intervention_success(turns: list[dict]) -> float:
    """After a wrong answer + hint, did the student get the NEXT answer right?"""
    interventions = 0
    successes = 0

    for i in range(len(turns) - 1):
        t = turns[i]
        intent = t.get("orchestrator_intent", {})
        agents = [intent.get("primary_agent", "")] + intent.get("supporting_agents", [])

        # An intervention is when hint or correction fired after a wrong answer
        if t.get("last_answer_correct") is False and ("hint" in agents or "correction" in agents):
            interventions += 1
            # Check if next evaluated answer is correct
            for j in range(i + 1, min(i + 4, len(turns))):
                if turns[j].get("last_answer_correct") is True:
                    successes += 1
                    break
                elif turns[j].get("last_answer_correct") is False:
                    break  # Got it wrong again

    return round(successes / interventions, 3) if interventions else 1.0
