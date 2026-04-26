# Learning Tutor Chatbot — Implementation Plan

---

## Table of Contents
1. [Overview](#1-overview)
2. [Database Schema](#2-database-schema)
3. [State Object Schema](#3-state-object-schema)
4. [Agent Pipeline](#4-agent-pipeline)
5. [Agents](#5-agents)
6. [Session Summary](#6-session-summary)
7. [Progress Tracking](#7-progress-tracking)
8. [Context Window Management](#8-context-window-management)
9. [Key Rules](#9-key-rules)

---

## 1. Overview

A blackboard-architecture tutoring chatbot where a shared state object is passed through a pipeline of agents each turn. Agents read from state and write their outputs back to it. A dialogue agent always runs last and synthesizes everything into a single student-facing message. No RAG or vector database — content is served from structured chapter notes stored in a relational database.

**Blackboard Pattern:** State is a shared JSON object. Every agent reads it and appends its output to a dedicated field inside it. No agent talks to another agent directly.

**Chapter Notes:** Instead of RAG, chapter content is pre-generated as structured JSON documents stored in the database. Each chapter is broken into sections by concept. Each section contains an explanation, examples, common misconceptions, a three-step hint progression, and quiz questions. This is a one-time manual preparation step per chapter before it can be taught.

**Section Loader:** Not an LLM agent. A plain database read that runs every turn before the orchestrator. It loads the full notes for the student's current concept into state so every agent has access to the content without making additional DB calls.

**Mastery Agent:** A side-effect agent. It runs every turn but never produces student-facing output. Its only job is to assess the student's understanding based on the conversation and update the mastery record in the database.

**Dialogue Agent:** The only agent that produces the final message shown to the student. It runs last every turn, reads the orchestrator's stated intent and whatever agents wrote to agent_outputs, and synthesizes a single natural response.

---

## 2. Database Schema

### students
```
student_id     string      PRIMARY KEY
name           string
grade          integer
created_at     timestamp
```

### chapters
```
chapter_id     integer     PRIMARY KEY
chapter_name   string
grade          integer
subject        string
section_ids    array       -- ordered list of section_ids in teaching sequence
```

### chapter_sections
```
section_id                string      PRIMARY KEY
chapter_id                integer     FOREIGN KEY → chapters
order                     integer     -- position in chapter, 1-indexed
concept                   string      -- short snake_case name e.g. "common_factors"
title                     string
difficulty                string      -- "intro" | "intermediate" | "advanced"
prerequisite_concepts     array       -- concept names that must be mastered first
explanation               string      -- core explanation, 2-4 sentences
examples                  array       -- 3 worked examples as plain text strings
common_misconceptions     array       -- 2-3 specific errors students commonly make
hint_progression          array       -- exactly 3 strings, index 0 vague → index 2 near-complete
quiz_questions            array       -- array of objects: { question, answer, explanation }
```

### student_progress
```
student_id            string      PRIMARY KEY, FOREIGN KEY → students
chapter_id            integer     PRIMARY KEY, FOREIGN KEY → chapters
current_section_id    string
section_statuses      jsonb       -- map of section_id → status string
completion_percent    integer     -- computed: mastered_count / total_sections * 100
last_updated          timestamp
```

section_statuses at runtime:
```json
{
  "ch13_s1": "mastered",
  "ch13_s2": "in_progress",
  "ch13_s3": "not_started",
  "ch13_s4": "not_started"
}
```

### student_sessions
```
session_id          string      PRIMARY KEY
student_id          string      FOREIGN KEY → students
chapter_id          integer     FOREIGN KEY → chapters
started_at          timestamp
turn_count          integer
session_summary     string      -- updated every 5 turns or on concept switch
last_10_messages    jsonb       -- array of message objects, max length 10
```

Each object in last_10_messages:
```json
{
  "role": "student | tutor",
  "content": "string"
}
```

---

## 3. State Object Schema

The state is assembled fresh at the start of every turn from the database. It is passed through the full pipeline entirely in memory and never stored as a whole. At the end of each turn only specific fields are written back to the DB individually.

```json
{
  "student_id": "string",
  "grade": "integer",
  "chapter_id": "integer",

  "emotion": "neutral | confused | bored | frustrated | confident",
  "gaze": "focused | looking_away",
  "consecutive_gaze_away": "integer",

  "attempt_count": "integer",
  "hint_count": "integer",
  "turn_count": "integer",
  "session_duration_mins": "integer",
  "last_answer_correct": "boolean | null",

  "last_10_messages": [
    { "role": "student | tutor", "content": "string" }
  ],

  "session_summary": "string",

  "chapter_progress": {
    "completion_percent": "integer",
    "current_section_id": "string",
    "current_concept": "string",
    "next_concept": "string | null",
    "section_statuses": {
      "<section_id>": "not_started | introduced | in_progress | struggling | mastered"
    }
  },

  "current_section": {
    "section_id": "string",
    "concept": "string",
    "title": "string",
    "difficulty": "string",
    "prerequisite_concepts": ["string"],
    "explanation": "string",
    "examples": ["string"],
    "common_misconceptions": ["string"],
    "hint_progression": ["string", "string", "string"],
    "quiz_questions": [
      {
        "question": "string",
        "answer": "string",
        "explanation": "string"
      }
    ]
  },

  "orchestrator_intent": {
    "primary_agent": "string",
    "supporting_agents": ["string"],
    "goal": "string",
    "reasoning": "string"
  },

  "agent_outputs": {
    "hint": "string | null",
    "correction": "string | null",
    "engagement": "string | null",
    "encouragement": "string | null",
    "quiz": "string | null"
  }
}
```

**What persists to DB vs stays in memory:**

| Field | Persists To |
|---|---|
| last_10_messages, turn_count | student_sessions |
| session_summary | student_sessions (only when regenerated) |
| section_statuses, current_section_id, completion_percent | student_progress (via mastery agent) |
| current_section | never — in-memory only |
| orchestrator_intent | never — in-memory only |
| agent_outputs | never — cleared at end of turn |

---

## 4. Agent Pipeline

Every turn runs these steps in this exact order:

1. Load student, session, and progress records from DB and assemble state
2. Append incoming student message to last_10_messages, trim to last 10
3. Run section loader — DB read, loads current_section into state
4. Check if summary regeneration is needed — regenerate if turn_count is a multiple of five or if current_section_id changed since last turn. Write updated summary back to state and to session record in DB.
5. Run orchestrator — sets orchestrator_intent, returns ordered list of agent names to call
6. Apply hard guardrails on top of orchestrator output — if consecutive_gaze_away is two or more, prepend engagement agent to the list regardless of what the orchestrator decided
7. Run each selected agent in order — each writes to agent_outputs
8. Run mastery agent unconditionally — writes to DB only, does not touch agent_outputs
9. Run dialogue agent unconditionally — reads orchestrator_intent and agent_outputs, writes final_message to state
10. Append tutor message to last_10_messages, trim to last 10
11. Write session and progress back to DB
12. Clear all agent_outputs values to null
13. Return final_message

---

## 5. Agents

### Section Loader
Plain database read. No LLM. Loads the full row from chapter_sections matching the student's current_section_id and writes it into state.current_section. Runs unconditionally every turn before anything else.

### Orchestrator
LLM-based. Receives the full state object. Reasons jointly over emotion, gaze, correctness, attempt_count, hint_count, and mastery status together — not independently — to decide the best pedagogical move for this turn. Must output structured JSON with four fields: primary_agent (string), supporting_agents (array of strings), goal (plain text describing what this turn's response must accomplish), and reasoning (why this combination was chosen). The dialogue agent consumes the goal field directly. Hard guardrails are applied to the orchestrator's output after it returns — the orchestrator itself does not need to handle the gaze guardrail internally.

### Hint Agent
No LLM. Reads hint_progression from current_section. Uses hint_count as the array index to select the appropriate hint. If hint_count is equal to or greater than three it always returns the last hint in the array. After returning the hint it increments hint_count in state. The escalation rule — when hint_count and attempt_count both reach three — is handled by the orchestrator on the next turn by switching to direct explanation mode using the explanation field from current_section instead of calling the hint agent again.

### Correction Agent
LLM-based. Called when last_answer_correct is false. Uses the common_misconceptions field from current_section to identify what the student likely misunderstood. Addresses the specific mistake before pointing forward. Must not give away the answer. Must not re-teach the entire concept — only target the error that was made.

### Engagement Agent
LLM-based. Called when gaze is looking_away for two or more consecutive turns or when emotion is bored. Generates a short re-engagement prompt that references the current concept. Does not re-explain content. Goal is attention recovery only, not instruction.

### Encouragement Agent
LLM-based. Called when emotion is frustrated. Acknowledges the difficulty of the concept and identifies something specific the student did correctly in their last message. Does not provide hints. Does not re-teach. Handles emotional state only. Kept separate from the engagement agent because frustration and boredom are pedagogically different situations requiring different responses.

### Quiz Agent
No LLM. Pulls the next unasked question from current_section.quiz_questions. Tracks which questions have been asked by maintaining a list of asked question strings in the session. If all questions for the current section have been asked, writes a sentinel value to agent_outputs.quiz so the mastery agent knows to evaluate for mastery advancement.

### Mastery Agent
LLM-based. Runs every turn unconditionally after all other agents but before the dialogue agent. Reads the full conversation context, last_answer_correct, attempt_count, hint_count, and current section status to determine the updated mastery status for the current section. Writes the new status to student_progress in the database. If the new status is mastered it also writes the next section_id as current_section_id, marks the new section as introduced in section_statuses, recomputes completion_percent, and resets attempt_count and hint_count to zero in state immediately so the next turn starts clean. Never writes to agent_outputs under any circumstance.

### Dialogue Agent
LLM-based. Always runs last unconditionally. Reads orchestrator_intent.goal to understand what this turn's response must accomplish. Reads all non-null values from agent_outputs. Synthesizes a single student-facing message that prioritises the primary_agent's output while incorporating supporting outputs naturally where relevant. Tone is warm, conversational, and grade-appropriate. No bullet points or lists. Plain prose only.

---

## 6. Session Summary

Two separate summaries must be maintained and must never be combined or stored in the same field.

**Session Summary** is episodic. It records what happened during the current session — which concept was being worked on, what the student got right or wrong, where they got stuck, and what has already been explained or hinted. It is regenerated by passing the existing summary and the last five messages to an LLM and asking for a concise update under eighty words. Regeneration triggers every five turns and whenever the concept changes. Lives in student_sessions.session_summary.

**Mastery Summary** is a skill record. It is the section_statuses map maintained by the mastery agent. It records what the student knows across all sections and persists between sessions. Lives in student_progress.section_statuses. It is not prose — it is a structured status map.

The session summary answers "what happened today". The mastery summary answers "what does this student know". They serve different agents for different purposes and must never be merged.

---

## 7. Progress Tracking

Each section moves through exactly this status sequence:

```
not_started → introduced → in_progress → struggling → mastered
```

Status never moves backward. Once a section is mastered it stays mastered across all future sessions.

**not_started** — default before the section has ever been loaded.

**introduced** — set the first time the section loader loads this section, or when a section is first advanced to after the previous one is mastered.

**in_progress** — set when the student begins attempting questions on this concept.

**struggling** — set when attempt_count reaches three or hint_count reaches three, whichever comes first.

**mastered** — set when the student answers a quiz question correctly with at most one hint used and within two attempts.

When mastery agent sets mastered it immediately: advances current_section_id to the next entry in chapters.section_ids, sets the new section's status to introduced, recomputes completion_percent, and resets attempt_count and hint_count to zero in state. All of this happens atomically before the dialogue agent runs so the dialogue agent can acknowledge the advancement if appropriate.

---

## 8. Context Window Management

Only the last ten messages are kept in state and in the database. When a new message is appended the array is immediately trimmed to ten. Messages that fall off are not lost — their substance is captured in the session summary before dropping. This keeps the context window size fixed and predictable regardless of session length.

Only student and tutor messages go into last_10_messages. Agent outputs, orchestrator reasoning, and internal state fields never appear in message history.

The context injected into every LLM agent call contains exactly three things: the last ten messages, the session summary, and the current section notes. Nothing else. This is sufficient for every agent and keeps token usage bounded.

---

## 9. Key Rules

- agent_outputs is cleared to null for all keys at the end of every turn without exception
- Mastery agent never writes to agent_outputs under any circumstance
- Dialogue agent is the only agent that produces student-facing text
- Section loader always runs before the orchestrator
- Summary regeneration always happens before the orchestrator so the orchestrator has current context
- attempt_count and hint_count reset to zero whenever the section advances
- hint_progression always has exactly three entries — the third must be near-complete but still require the student to supply the final answer step themselves
- Hard guardrails on gaze are applied after the orchestrator returns, not inside the orchestrator prompt
- session_summary and section_statuses are separate fields, separate DB columns, and must never be merged
- current_section, orchestrator_intent, and agent_outputs are never written to the database
