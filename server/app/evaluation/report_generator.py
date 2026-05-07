"""
Report Generator — produces Markdown evaluation reports.

Takes computed metrics from MetricsEngine and formats them into
human-readable reports saved to evaluations/reports/.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EVAL_ROOT = Path(__file__).resolve().parents[3] / "evaluations"


def generate_session_report(
    session_id: str,
    metrics: dict,
    *,
    session_type: str = "live",
    test_id: Optional[str] = None,
) -> Path:
    """Generate a Markdown report for a single session.

    Reports are organised into subfolders:
      - evaluations/reports/synthetic/{date}_{test_id}/
      - evaluations/reports/live/{date}/

    Returns the path to the generated report file.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H-%M-%S")

    # ── Organised folder hierarchy ────────────────────────────────
    if session_type == "synthetic":
        folder_name = f"{date_str}_{test_id or 'run'}"
        reports_dir = EVAL_ROOT / "reports" / "synthetic" / folder_name
    else:
        reports_dir = EVAL_ROOT / "reports" / "live" / date_str
    reports_dir.mkdir(parents=True, exist_ok=True)

    filename = f"session_{session_id[:8]}_{time_str}.md"
    report_path = reports_dir / filename

    md = _build_session_markdown(session_id, metrics, session_type, test_id)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)

    # Also write the raw metrics JSON alongside
    json_path = report_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Report generated → %s", report_path)
    return report_path


def generate_batch_report(
    test_id: str,
    all_session_metrics: list[dict],
) -> Path:
    """Generate an aggregate report across multiple sessions (synthetic batch).

    Reports go to: evaluations/reports/batch/{date}_{test_id}/
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H-%M-%S")

    # ── Organised folder hierarchy ────────────────────────────────
    folder_name = f"{date_str}_{test_id}"
    reports_dir = EVAL_ROOT / "reports" / "batch" / folder_name
    reports_dir.mkdir(parents=True, exist_ok=True)

    filename = f"batch_summary_{time_str}.md"
    report_path = reports_dir / filename

    md = _build_batch_markdown(test_id, all_session_metrics)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)

    json_path = report_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_session_metrics, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Batch report generated → %s", report_path)
    return report_path


# ── Markdown Builders ────────────────────────────────────────────────────


def _build_session_markdown(
    session_id: str,
    m: dict,
    session_type: str,
    test_id: Optional[str],
) -> str:
    """Build a Markdown string for a single session report."""
    lines = []
    lines.append(f"# PALM Session Evaluation Report")
    lines.append("")
    lines.append(f"- **Session ID:** `{session_id}`")
    lines.append(f"- **Type:** {session_type}")
    if test_id:
        lines.append(f"- **Test ID:** {test_id}")
    lines.append(f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Total Turns:** {m.get('total_turns', 0)}")
    lines.append(f"- **Final Completion:** {m.get('final_completion_percent', 0)}%")
    lines.append("")

    # ── Efficiency ────────────────────────────────────────────────
    lines.append("## 1. Efficiency Metrics")
    lines.append("")
    ttm = m.get("turns_to_mastery", {})
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Avg Turns to Mastery | **{ttm.get('average', 'N/A')}** |")
    lines.append(f"| Total Answers Evaluated | {m.get('total_answers_evaluated', 0)} |")
    lines.append(f"| Correct Answers | {m.get('correct_answers', 0)} |")
    lines.append(f"| Accuracy Rate | **{m.get('accuracy_rate', 0) * 100:.1f}%** |")
    lines.append("")

    per_section = ttm.get("per_section", {})
    if per_section:
        lines.append("### Turns to Mastery per Section")
        lines.append("| Section | Turns |")
        lines.append("|---------|-------|")
        for sid, count in per_section.items():
            lines.append(f"| `{sid}` | {count} |")
        lines.append("")

    # ── Agent Activation ──────────────────────────────────────────
    lines.append("## 2. Agent Activation Distribution")
    lines.append("")
    dist = m.get("agent_activation_distribution", {})
    if dist:
        lines.append("| Agent | Count | % |")
        lines.append("|-------|-------|---|")
        for agent, info in dist.items():
            lines.append(f"| {agent} | {info['count']} | {info['percent']}% |")
    lines.append("")

    # ── Conversational ────────────────────────────────────────────
    lines.append("## 3. Conversational / NLP Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Avg Student Words/Turn | {m.get('avg_student_words_per_turn', 0)} |")
    lines.append(f"| Avg Tutor Words/Turn | {m.get('avg_tutor_words_per_turn', 0)} |")
    lines.append(f"| Student-Tutor Talk Ratio | **{m.get('student_tutor_talk_ratio', 0)}** |")
    lines.append("")

    vocab = m.get("vocabulary_adoption", {})
    if vocab:
        lines.append("### Vocabulary Adoption")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Terms Introduced by Tutor | {vocab.get('terms_introduced_by_tutor', 0)} |")
        lines.append(f"| Terms Adopted by Student | {vocab.get('terms_adopted_by_student', 0)} |")
        lines.append(f"| Adoption Rate | **{vocab.get('adoption_rate', 0) * 100:.1f}%** |")
        lines.append(f"| Avg Adoption Delay (turns) | {vocab.get('avg_adoption_delay_turns', 0)} |")
    lines.append("")

    # ── Perception ────────────────────────────────────────────────
    lines.append("## 4. Perception / Emotion Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Affective Volatility | **{m.get('affective_volatility', 0)}** |")
    ttb = m.get("time_to_boredom_turn")
    lines.append(f"| Time to Boredom (turn) | {ttb if ttb is not None else 'Never'} |")
    lines.append(f"| Engagement Recovery Rate | **{m.get('engagement_recovery_rate', 1.0) * 100:.1f}%** |")
    lines.append(f"| Gaze Away % | {m.get('gaze_away_percentage', 0)}% |")
    lines.append("")

    emo_dist = m.get("emotion_distribution", {})
    if emo_dist:
        lines.append("### Emotion Distribution")
        lines.append("| Emotion | Count | % |")
        lines.append("|---------|-------|---|")
        for emo, info in emo_dist.items():
            lines.append(f"| {emo} | {info['count']} | {info['percent']}% |")
    lines.append("")

    # ── Pipeline Health ───────────────────────────────────────────
    lines.append("## 5. Pipeline Health Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Avg Latency | **{m.get('latency_avg_ms', 0)} ms** |")
    lines.append(f"| P50 Latency | {m.get('latency_p50_ms', 0)} ms |")
    lines.append(f"| P95 Latency | {m.get('latency_p95_ms', 0)} ms |")
    lines.append(f"| Max Latency | {m.get('latency_max_ms', 0)} ms |")
    lines.append(f"| KaTeX Usage | {m.get('katex_usage_count', 0)} turns |")
    lines.append(f"| KaTeX Broken | {m.get('katex_broken_count', 0)} turns |")
    lines.append(f"| Math Formatting Error Rate | **{m.get('math_formatting_error_rate', 0) * 100:.1f}%** |")
    lines.append("")

    # ── Token Consumption (NEW) ──────────────────────────────────
    tokens = m.get("token_consumption", {})
    lines.append("## 6. Token Consumption (Cost & Efficiency)")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Prompt Tokens | {tokens.get('total_prompt_tokens', 0):,} |")
    lines.append(f"| Total Completion Tokens | {tokens.get('total_completion_tokens', 0):,} |")
    lines.append(f"| **Total Tokens** | **{tokens.get('total_tokens', 0):,}** |")
    lines.append(f"| Avg Tokens/Turn | {tokens.get('avg_tokens_per_turn', 0)} |")
    lines.append("")

    # ── Curriculum Quality ────────────────────────────────────────
    lines.append("## 7. Curriculum Quality")
    lines.append("")
    bottlenecks = m.get("section_bottlenecks", [])
    if bottlenecks:
        lines.append("| Section | Turns Spent | Bottleneck? |")
        lines.append("|---------|-------------|-------------|")
        for b in bottlenecks:
            flag = "⚠️ YES" if b.get("is_bottleneck") else "No"
            lines.append(f"| `{b['section_id']}` | {b['turns_spent']} | {flag} |")
    lines.append("")

    hint = m.get("hint_exhaustion_rate", {})
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Turns with Hints | {hint.get('turns_with_hints', 0)} |")
    lines.append(f"| Turns at Max Hints | {hint.get('turns_at_max_hints', 0)} |")
    lines.append(f"| Hint Exhaustion Rate | **{hint.get('exhaustion_rate', 0) * 100:.1f}%** |")
    lines.append("")

    # ── Pedagogy ──────────────────────────────────────────────────
    lines.append("## 8. Pedagogy Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Intervention Success Rate | **{m.get('intervention_success_rate', 0) * 100:.1f}%** |")
    lines.append(f"| Student Initiative Rate | **{m.get('student_initiative_rate', 0) * 100:.1f}%** |")
    lines.append(f"| Context Compression Ratio | {m.get('context_compression_ratio', 1.0)} |")
    lines.append("")

    # ── LLM Judge Scores ─────────────────────────────────────────
    judge = m.get("llm_judge_scores", {})
    if judge and "error" not in judge:
        lines.append("## 9. LLM-as-a-Judge Qualitative Scores")
        lines.append("")

        # ── Original 5 dimensions ────────────────────────────────
        lines.append("### Core Evaluation Dimensions")
        lines.append("| Dimension | Score | Reasoning |")
        lines.append("|-----------|-------|-----------|")
        for dim in ["socratic_adherence", "empathy_validation", "age_appropriate_tone",
                     "guardrail_resilience", "curriculum_grounding"]:
            entry = judge.get(dim, {})
            if isinstance(entry, dict):
                score = entry.get("score", "N/A")
                reason = entry.get("reasoning", "")[:200]
                label = dim.replace("_", " ").title()
                lines.append(f"| {label} | **{score}/10** | {reason} |")
        lines.append("")

        # ── Grounding & Hallucination (NEW) ──────────────────────
        lines.append("### Grounding & Hallucination Metrics")
        lines.append("| Dimension | Score | Reasoning |")
        lines.append("|-----------|-------|-----------|")
        for dim in ["faithfulness", "answer_relevance", "concept_leakage"]:
            entry = judge.get(dim, {})
            if isinstance(entry, dict):
                score = entry.get("score", "N/A")
                reason = entry.get("reasoning", "")[:200]
                label = dim.replace("_", " ").title()
                lines.append(f"| {label} | **{score}/10** | {reason} |")
        lines.append("")

        # ── Pedagogical Quality (NEW) ────────────────────────────
        lines.append("### Pedagogical Quality Metrics")
        lines.append("| Dimension | Score | Reasoning |")
        lines.append("|-----------|-------|-----------|")
        for dim in ["hint_progression_compliance", "tone_consistency"]:
            entry = judge.get(dim, {})
            if isinstance(entry, dict):
                score = entry.get("score", "N/A")
                reason = entry.get("reasoning", "")[:200]
                label = dim.replace("_", " ").title()
                lines.append(f"| {label} | **{score}/10** | {reason} |")
        lines.append("")

        # ── Safety & Deflection (NEW) ────────────────────────────
        lines.append("### Safety & Deflection Metrics")
        lines.append("| Dimension | Score | Details | Reasoning |")
        lines.append("|-----------|-------|---------|-----------|")

        otd = judge.get("off_topic_deflection", {})
        if isinstance(otd, dict):
            otd_score = otd.get("score", "N/A")
            defl_ok = otd.get("deflections_successful", "?")
            defl_total = otd.get("total_off_topic", "?")
            otd_reason = otd.get("reasoning", "")[:200]
            lines.append(f"| Off-Topic Deflection | **{otd_score}/10** | {defl_ok}/{defl_total} deflected | {otd_reason} |")

        pir = judge.get("prompt_injection_resilience", {})
        if isinstance(pir, dict):
            pir_score = pir.get("score", "N/A")
            inj_attempts = pir.get("injection_attempts", "?")
            inj_blocked = pir.get("injections_blocked", "?")
            pir_reason = pir.get("reasoning", "")[:200]
            lines.append(f"| Prompt Injection Resilience | **{pir_score}/10** | {inj_blocked}/{inj_attempts} blocked | {pir_reason} |")
        lines.append("")

        # ── Overall ──────────────────────────────────────────────
        overall = judge.get("overall_score", "N/A")
        lines.append(f"**Overall Judge Score: {overall}/10**")
        summary = judge.get("summary", "")
        if summary:
            lines.append("")
            lines.append(f"> {summary}")
    lines.append("")

    # ── Persona info ─────────────────────────────────────────────
    if m.get("persona"):
        lines.append("## 10. Test Persona")
        lines.append("")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| Persona | **{m.get('persona_name', '')}** (`{m.get('persona', '')}`) |")
        lines.append(f"| Target Test | {m.get('target_test', '')} |")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by PALM Evaluation Engine*")

    return "\n".join(lines)


def _build_batch_markdown(test_id: str, all_metrics: list[dict]) -> str:
    """Build a summary Markdown for a batch of synthetic sessions."""
    lines = []
    lines.append(f"# PALM Batch Evaluation Report")
    lines.append("")
    lines.append(f"- **Test ID:** `{test_id}`")
    lines.append(f"- **Sessions:** {len(all_metrics)}")
    lines.append(f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    if not all_metrics:
        lines.append("No sessions to report.")
        return "\n".join(lines)

    # Aggregate averages
    def _avg(key):
        vals = [m.get(key, 0) for m in all_metrics if m.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0

    def _avg_nested(key, subkey):
        vals = []
        for m in all_metrics:
            nested = m.get(key, {})
            if isinstance(nested, dict) and subkey in nested:
                vals.append(nested[subkey])
        return round(sum(vals) / len(vals), 2) if vals else 0

    lines.append("## Aggregate Summary")
    lines.append("")
    lines.append("| Metric | Average |")
    lines.append("|--------|---------|")
    lines.append(f"| Total Turns | {_avg('total_turns')} |")
    lines.append(f"| Avg TTM | {_avg_nested('turns_to_mastery', 'average')} |")
    lines.append(f"| Accuracy Rate | {_avg('accuracy_rate') * 100:.1f}% |")
    lines.append(f"| Student-Tutor Talk Ratio | {_avg('student_tutor_talk_ratio')} |")
    lines.append(f"| Affective Volatility | {_avg('affective_volatility')} |")
    lines.append(f"| Engagement Recovery | {_avg('engagement_recovery_rate') * 100:.1f}% |")
    lines.append(f"| Intervention Success | {_avg('intervention_success_rate') * 100:.1f}% |")
    lines.append(f"| Avg Latency (ms) | {_avg('latency_avg_ms')} |")
    lines.append(f"| P95 Latency (ms) | {_avg('latency_p95_ms')} |")
    lines.append(f"| Math Format Error Rate | {_avg('math_formatting_error_rate') * 100:.1f}% |")
    lines.append(f"| Final Completion % | {_avg('final_completion_percent')}% |")
    lines.append(f"| Total Tokens (avg) | {_avg_nested('token_consumption', 'total_tokens'):,} |")
    lines.append(f"| Tokens/Turn (avg) | {_avg_nested('token_consumption', 'avg_tokens_per_turn')} |")
    lines.append("")

    # Per-persona breakdown
    valid = [m for m in all_metrics if "error" not in m]
    if valid:
        lines.append("## Per-Persona Breakdown")
        lines.append("")
        lines.append("| Persona | Turns | Accuracy | Talk Ratio | Volatility | Tokens | Judge |")
        lines.append("|---------|-------|----------|------------|------------|--------|-------|")
        for m in valid:
            name = m.get("persona_name", m.get("persona", "?"))
            turns = m.get("total_turns", 0)
            acc = f"{m.get('accuracy_rate', 0) * 100:.0f}%"
            ratio = f"{m.get('student_tutor_talk_ratio', 0):.2f}"
            vol = f"{m.get('affective_volatility', 0):.2f}"
            tok = m.get("token_consumption", {}).get("total_tokens", 0)
            tok_str = f"{tok:,}"
            judge = m.get("llm_judge_scores", {})
            jscore = judge.get("overall_score", "N/A") if isinstance(judge, dict) else "N/A"
            lines.append(f"| {name} | {turns} | {acc} | {ratio} | {vol} | {tok_str} | {jscore} |")
        lines.append("")

        # ── Per-persona Judge detail ─────────────────────────────
        lines.append("## Per-Persona Judge Scores")
        lines.append("")
        judge_dims = [
            "socratic_adherence", "empathy_validation", "age_appropriate_tone",
            "guardrail_resilience", "curriculum_grounding",
            "faithfulness", "answer_relevance", "concept_leakage",
            "hint_progression_compliance", "tone_consistency",
            "off_topic_deflection", "prompt_injection_resilience",
        ]
        header_labels = [d.replace("_", " ").title()[:12] for d in judge_dims]
        lines.append("| Persona | " + " | ".join(header_labels) + " | Overall |")
        lines.append("|---------|" + "|".join(["------" for _ in judge_dims]) + "|---------|")
        for m in valid:
            name = m.get("persona_name", m.get("persona", "?"))
            judge = m.get("llm_judge_scores", {})
            if not isinstance(judge, dict) or "error" in judge:
                scores_str = " | ".join(["N/A" for _ in judge_dims])
                lines.append(f"| {name} | {scores_str} | N/A |")
                continue
            scores = []
            for dim in judge_dims:
                entry = judge.get(dim, {})
                s = entry.get("score", "N/A") if isinstance(entry, dict) else "N/A"
                scores.append(str(s))
            overall = judge.get("overall_score", "N/A")
            lines.append(f"| {name} | " + " | ".join(scores) + f" | {overall} |")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by PALM Evaluation Engine*")

    return "\n".join(lines)
