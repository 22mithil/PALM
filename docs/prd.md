# Product Requirements Document

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Project Goals & Objectives](#3-project-goals--objectives)
4. [Detailed System Architecture](#4-detailed-system-architecture)
5. [Tech Stack Specification](#5-tech-stack-specification)
6. [Module-Level Feature Specifications](#6-module-level-feature-specifications)
7. [API & The 13-Step Pipeline Design](#7-api--the-13-step-pipeline-design)
8. [Database Schema in Detail](#8-database-schema-in-detail)
9. [Frontend UI Specifications](#9-frontend-ui-specifications)
10. [Adaptive Feedback Logic](#10-adaptive-feedback-logic)
11. [Implementation Phases & Milestones](#11-implementation-phases--milestones)

---

## 1. Executive Summary

PALM (Personalized Adaptive Learning Mentor) is a multimodal, multi-agent AI tutoring system designed for primary school students (Grades 1–5) in core mathematics. The system goes beyond conventional e-learning by integrating real-time computer vision-based affective state recognition (emotion, gaze) with a structured curriculum pipeline and specialized agents.

This PRD reflects the **current fully-built state** of the application, incorporating real-world architectural changes (e.g., migrating from LangGraph to a deterministic linear pipeline, shifting curriculum from Pinecone RAG to structured PostgreSQL, and relying on client-side Web Speech APIs for TTS/STT).

---

## 2. Problem Statement

Modern AI tutoring systems and e-learning platforms suffer from three critical gaps:

**The Hallucination Gap** — LLMs generate inaccurate, unverified mathematical content. A structured curriculum loading pipeline grounding all responses in verified database content is required.

**The Perception Gap** — Text-only tutoring systems are blind to non-verbal signals. A student's confusion, frustration, or boredom goes completely undetected, preventing timely pedagogical intervention.

**The Adaptivity Gap** — Static curricula and fixed decision trees cannot dynamically adjust to each student's evolving mastery level, emotional state, and attention patterns. Real-time orchestration is required to modify teaching strategies mid-lesson.

---

## 3. Project Goals & Objectives

| #   | Objective                             | Description                                                                                                  |
| --- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| G1  | Dynamic Learning Path Synthesis       | Assess prior knowledge and adjust curriculum progression in real time based on performance and mastery.      |
| G2  | Real-Time Affective State Recognition | Classify boredom, confusion, frustration, and engagement directly in-browser using MediaPipe blendshapes.      |
| G3  | Gaze & Attention Quantification       | Detect gaze deviation and zone-out events using MediaPipe non-intrusively.                                   |
| G4  | Adaptive Feedback Loops               | Implement Struggle, Boredom, and Mastery loops that alter lesson trajectory based on combined state signals. |
| G5  | Low-Latency Multimodal Perception     | Achieve near real-time processing of audio and visual inputs via client-side processing.                     |
| G6  | Long-Term Context & Mastery Tracking  | Maintain session history and per-student knowledge state in NeonDB for personalized continuity.              |
| G7  | Multi-Agent Pipeline                  | Execute specialized behaviors (Mastery, Engagement, Dialogue, Hint, Quiz) via a deterministic 13-step turn pipeline. |
| G8  | Curriculum Delivery                   | All instructional responses grounded in structured Chapters and Sections stored in PostgreSQL.               |

---

## 4. Detailed System Architecture

PALM operates on a continuous **Perception–Action Cycle**, integrating frontend signals with a centralized state machine backend.

### The Perception Flow (Client -> Server)
1. **Video/Vision:** The React frontend accesses the webcam via WebRTC. Frames are passed to `MediaPipe FaceLandmarker` running locally in the browser (via WebAssembly). The model calculates 52 facial blendshapes and iris landmarks. Custom thresholding logic converts these raw metrics into semantic labels: `emotion` (confident, confused, bored, frustrated, neutral) and `gaze` (focused, looking_away).
2. **Telemetry:** The frontend transmits a lightweight JSON payload (`{"emotion": "confused", "gaze": "focused"}`) over a WebSocket (`/api/v1/ws/video/`) at 1 Hz. This reduces bandwidth dramatically compared to streaming raw video frames.
3. **Audio/Voice:** When the microphone is active, the browser's native `SpeechRecognition` API transcribes speech into text locally. The text is sent over the main Tutor WebSocket.
4. **Backend Context:** The FastAPI backend receives the perception telemetry and caches it in an in-memory `session_context_manager`.

### The Action Flow (Server -> Client)
1. **Pipeline Execution:** When a student sends a message (or upon session start), the backend triggers the **13-Step Linear Pipeline**. This pipeline pulls the cached perception data, fetches the student's curriculum progress from NeonDB, and builds a massive `TurnState` object.
2. **Generation:** Specialized agents append `[HINT]`, `[QUIZ]`, or `[ENGAGEMENT]` data to the `TurnState`. Finally, the Dialogue Agent synthesizes a single, cohesive tutor response in Markdown with KaTeX math formatting.
3. **Delivery:** The backend streams the markdown response back via WebSocket.
4. **Voice Synthesis:** The frontend renders the markdown, intercepts the text, strips out LaTeX and markdown artifacts using custom Regex (in `useTextToSpeech.js`), and feeds it to `window.speechSynthesis` (chunked by sentence to prevent browser cutoff bugs).

---

## 5. Tech Stack Specification

### 5.1 Frontend

| Technology       | Role              | Notes                                      |
| ---------------- | ----------------- | ------------------------------------------ |
| React (Vite)     | UI Framework      |                                            |
| Tailwind CSS     | Styling           |                                            |
| shadcn/ui        | Component Library |                                            |
| WebRTC API       | Media Capture     | Browser-native webcam access               |
| Web Speech API   | STT & TTS         | Client-side transcription and voice synthesis |
| WebSocket Client | Real-time comms   | Bidirectional streaming to FastAPI backend |
| Zustand          | State Management  | Server state caching + client state        |

### 5.2 Backend

| Technology             | Role                | Notes                                  |
| ---------------------- | ------------------- | -------------------------------------- |
| FastAPI (Python 3.11+) | API Server          | Async REST + WebSocket endpoints       |
| 13-Step Pipeline       | Turn Execution      | Replaces LangGraph for predictable execution (`app/pipeline/runner.py`) |
| Pydantic               | Data Validation     | Schema enforcement for API models (`TurnState`) |
| SQLAlchemy (asyncpg)   | ORM                 | Async DB queries against PostgreSQL |
| LLM API (FastRouter)   | Text Generation     | Handles LLM inference behind the scenes |

### 5.3 Relational Database (Primary Store)

| Technology | Role             | Notes                                                                   |
| ---------- | ---------------- | ----------------------------------------------------------------------- |
| NeonDB     | Primary Database | Serverless PostgreSQL; stores student profiles, curriculum, and mastery |

*(Note: Pinecone/Vector DB has been entirely removed. Curriculum is now structured natively in Postgres).*

---

## 6. Module-Level Feature Specifications

### 6.1 Cognitive Engine (Specialized Agents)

All agents are pure functions that read from the `TurnState` and write to `TurnState.agent_outputs`.

- **Mastery Agent (`mastery_agent.py`):** Runs every turn as a side-effect. Uses a strict prompt to evaluate understanding based on answer correctness, attempts, and hint count. Transitions the section status: `introduced` -> `in_progress` -> `struggling` or `mastered`. If `mastered`, it automatically advances `current_section_id` to the next section in the chapter.
- **Engagement Agent (`engagement_agent.py`):** Detects consecutive gaze-away turns or "bored" emotions. Generates re-engagement activities (riddles, physical stretches) and injects an `[ENGAGEMENT]` output.
- **Hint Agent (`hint_agent.py`):** Triggers on confusion or incorrect answers. Provides tiered scaffolding (conceptual -> step-by-step).
- **Quiz Agent (`quiz_agent.py`):** Pulls structured quiz questions from the Postgres `ChapterSection` data to validate understanding before allowing a section to be marked complete.
- **Correction Agent (`correction_agent.py`):** Handles incorrect responses softly, guiding the student without giving away the answer.
- **Encouragement Agent (`encouragement_agent.py`):** Rewards persistence, effort, and correct answers.
- **Dialogue Agent (`dialogue_agent.py`):** The final synthesizer. It reads all generated agent outputs, the section explanation, the orchestrator goal, and the conversation history. It merges them into one age-appropriate, warm response (under 150 words).

---

## 7. API & The 13-Step Pipeline Design

The core of the backend is `app/pipeline/runner.py`. It replaces complex non-deterministic graphs with a strict linear flow:

1. **State Assembly:** Fetches `Student`, `StudentSession`, and `StudentProgress` from DB. Merges in `emotion` and `gaze` from `session_context_manager` to build the `TurnState`.
2. **History Update:** Appends the student's message to the rolling 10-message memory.
3. **Section Loader:** Pulls the exact `Chapter` and `ChapterSection` content from Postgres based on `current_section_id`.
4. **Summary Regen:** Compresses session memory via LLM if it grows too large.
5. **Answer Checker:** Evaluates student math inputs against the known section context. Updates `TurnState.last_answer_correct`.
6. **Orchestrator Intent:** A fast, lightweight LLM call that decides which specialized agents to trigger (e.g., `primary: dialogue, supporting: [quiz, encouragement]`).
7. **Guardrails & Agents:** Applies safety guardrails. Fires the targeted agents requested by the orchestrator.
8. **Mastery Agent Execution:** Unconditionally evaluates progress. If completion hits 100%, it locks the `was_completed` flag to True so mastery cannot degrade in review mode.
9. **Dialogue Agent Execution:** Synthesizes the final response. (Skipped if chapter just hit 100% to output a hardcoded celebration instead).
10. **State Finalization:** Appends Tutor response to history.
11. **Commit:** Writes updated `turn_count`, `last_10_messages`, `section_statuses`, and `completion_percent` back to NeonDB.
12. **Cleanup:** Clears transient `agent_outputs`.
13. **Return:** Returns `final_message` to the WebSocket router.

---

## 8. Database Schema in Detail

Tables are strictly typed via SQLAlchemy in NeonDB.

### Curriculum Schema (`app/models/curriculum.py`)
- **`chapters`**:
  - `chapter_id` (Integer, PK)
  - `chapter_name` (String)
  - `grade` (SmallInteger, 1-5)
  - `section_ids` (ARRAY of Strings, defines the exact ordered progression)
- **`chapter_sections`**:
  - `section_id` (String, PK)
  - `chapter_id` (FK to chapters)
  - `order` (Integer)
  - `concept` (String)
  - `explanation` (Text)
  - `hint_progression` (ARRAY of Text)
  - `quiz_questions` (JSONB)

### State & Progress Schema (`app/models/mastery.py` & `session.py`)
- **`student_progress`**:
  - `student_id` (FK to students)
  - `chapter_id` (FK to chapters)
  - `current_section_id` (String)
  - `completion_percent` (Float, 0-100)
  - `was_completed` (Boolean, permanently locks mastery UI)
  - `section_statuses` (JSONB: tracks `{ "section_1": {"status": "mastered"} }`)
- **`sessions`**:
  - `id` (UUID, PK)
  - `student_id` (FK)
  - `turn_count` (Integer)
  - `last_10_messages` (JSONB array)
  - `session_summary` (Text)

---

## 9. Frontend UI Specifications

**Framework:** React (Vite) + Tailwind CSS + shadcn/ui

### 9.1 Key Routes
- `/`: Landing (Student Name + Grade entry)
- `/dashboard`: Progress overview and topic selection
- `/session/:sessionId`: Main tutoring interface
- `/progress`: Deep-dive mastery report

### 9.2 Session UI Breakdown
- **Perception HUD (`PerceptionHUD.jsx`):** A floating interface overlaying the webcam feed. It shows real-time MediaPipe diagnostics, including an `emotion` badge (e.g., `Confused 😕`) and an eye icon indicating gaze.
- **Chat Window:** Renders markdown. Intercepts special strings like `[QUIZ]` or `[ENGAGEMENT]` to render beautiful, interactive shadcn/ui Cards instead of plain text.
- **Mastery Bar:** Tracks `completion_percent` in real-time. Automatically hides itself if `was_completed` is true to reduce UI clutter during revision.
- **Input Controls:** Microphone toggle (Web Speech) + Text Input.
- **TTS Engine (`useTextToSpeech.js`):** Automatically reads incoming Tutor messages using browser synthesis. Includes sophisticated regex pipelines to strip `$$`, `\n`, and Markdown before pushing to the `SpeechSynthesisUtterance`.

---

## 10. Adaptive Feedback Logic

### 10.1 Struggle Loop
**Trigger:** `answer_checker` flags incorrect answer AND `emotion` == 'confused' or 'frustrated'.
**Action:** The Orchestrator routes to the `Hint Agent`. Progress is halted until the concept is grasped.

### 10.2 Boredom Loop
**Trigger:** `consecutive_gaze_away` > N or `emotion` == 'bored'.
**Action:** The Orchestrator triggers the `Engagement Agent`. It pauses the curriculum delivery to fire a quick physical or mental brain-break.

### 10.3 Mastery Loop
**Trigger:** Section quiz passed with minimal hints.
**Action:** The `Mastery Agent` transitions the current section to `mastered` and advances `current_section_id`. If `completion_percent` hits 100%, `was_completed` is locked to True. A celebration message (confetti) is dispatched.

---

## 11. Implementation Phases & Milestones

All phases below are currently **COMPLETED**:

### Phase 1 — Core Architecture & Curriculum (Completed)
- [x] FastAPI project structure + NeonDB schema setup
- [x] Curriculum loaded into PostgreSQL (`Chapter`, `Section` models)
- [x] Base CRUD endpoints for students, topics, and sessions

### Phase 2 — Perception Engine (Completed)
- [x] WebRTC video + audio capture in React
- [x] MediaPipe FaceLandmarker integration on client-side (gaze/face tracking)
- [x] Threshold-based emotion classification
- [x] Web Speech API integration for STT and TTS
- [x] Emotion + gaze signal display in UI (Perception HUD)

### Phase 3 — Orchestration & Agents (Completed)
- [x] 13-Step Linear Pipeline implemented (`runner.py`)
- [x] All specific agents implemented (Hint, Quiz, Mastery, etc.)
- [x] Context Assembly & Answer Checking logic
- [x] Adaptive feedback loops wired directly into the pipeline
- [x] Persistent mastery score logic (prevents regression on completed chapters)

### Phase 4 — Frontend & UI Polish (Completed)
- [x] Dashboard and Progress pages
- [x] Real-time session interface with chat and HUD
- [x] Client-side text-to-speech implementation (`useTextToSpeech.js`)
- [x] Celebration animations and dynamic UI card rendering

---
*Document reflects the state of the system as of May 2026.*