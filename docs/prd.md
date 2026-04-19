# Product Requirements Document

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Project Goals & Objectives](#3-project-goals--objectives)
4. [Scope & Exclusions](#4-scope--exclusions)
5. [System Architecture Overview](#5-system-architecture-overview)
6. [Tech Stack Specification](#6-tech-stack-specification)
7. [Module-Level Feature Specifications](#7-module-level-feature-specifications)
   - 7.1 Perception Engine
   - 7.2 Orchestration & State Management
   - 7.3 Cognitive & Knowledge Engine (Multi-Agent)
   - 7.4 RAG Pipeline & Vector DB
   - 7.5 Response Validator & Verification Layer
   - 7.6 Output Generation Layer
   - 7.7 Frontend (Student Interface)
8. [API Design](#8-api-design)
9. [Database Schema](#9-database-schema)
10. [Frontend UI Specifications](#10-frontend-ui-specifications)
11. [Adaptive Feedback Logic](#11-adaptive-feedback-logic)
12. [Implementation Phases & Milestones](#13-implementation-phases--milestones)

---

## 1. Executive Summary

PALM (Personalized Adaptive Learning Mentor) is a multimodal, multi-agent AI tutoring system designed for primary school students (Grades 1–5) in core mathematics. The system goes beyond conventional e-learning by integrating real-time computer vision-based affective state recognition (emotion, gaze), a Retrieval-Augmented Generation (RAG) cognitive core grounded in curriculum-aligned knowledge, and a specialized multi-agent orchestration layer.

This PRD covers the **Stage 2 full-system build** using the following confirmed tech stack:

| Layer                    | Technology                       |
| ------------------------ | -------------------------------- |
| Frontend                 | React + Tailwind CSS + shadcn/ui |
| Backend                  | FastAPI (Python)                 |
| LLM / Embeddings Routing | FastRouter                       |
| Vector Database          | Pinecone                         |
| Relational Database      | NeonDB (serverless PostgreSQL)   |
| Orchestration            | LangGraph                        |
| Vision                   | MediaPipe FaceLandmarker (Client-side) |
| STT                      | FastRouter                       |
| TTS                      | FastRouter                       |

---

## 2. Problem Statement

Modern AI tutoring systems and e-learning platforms suffer from three critical gaps:

**The Hallucination Gap** — LLMs generate inaccurate, unverified mathematical content ("botpoop"), undermining pedagogical trust. A RAG-first architecture grounding all responses in verified curriculum data is required.

**The Perception Gap** — Text-only tutoring systems are blind to non-verbal signals. A student's confusion, frustration, or boredom goes completely undetected, preventing timely pedagogical intervention.

**The Adaptivity Gap** — Static curricula and fixed decision trees cannot dynamically adjust to each student's evolving mastery level, emotional state, and attention patterns. Real-time, agentic orchestration is required to modify teaching strategies mid-lesson.

---

## 3. Project Goals & Objectives

| #   | Objective                             | Description                                                                                                  |
| --- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| G1  | Dynamic Learning Path Synthesis       | Assess prior knowledge before each topic; adjust curriculum in real time based on performance and mastery.   |
| G2  | Real-Time Affective State Recognition | Classify boredom, confusion, frustration, and engagement directly in-browser using MediaPipe blendshapes.      |
| G3  | Gaze & Attention Quantification       | Detect gaze deviation and zone-out events using MediaPipe non-intrusively.                                   |
| G4  | Adaptive Feedback Loops               | Implement Struggle, Boredom, and Mastery loops that alter lesson trajectory based on combined state signals. |
| G5  | Low-Latency Multimodal Perception     | Achieve near real-time processing of audio and visual inputs (< 300ms for perception pipeline).              |
| G6  | Long-Term Context & Mastery Tracking  | Maintain session history and per-student knowledge state in NeonDB for personalized continuity.              |
| G7  | Agentic Orchestration                 | Deploy Orchestrator + specialized agents (RAG, Mastery, Engagement, Dialogue, Hint, Quiz) via LangGraph.     |
| G8  | RAG-Grounded Curriculum Delivery      | All instructional responses retrieved from Pinecone vector store seeded with NCERT-style math PDFs.          |
| G9  | Response Verification                 | Validate LLM outputs for mathematical correctness and age-appropriate tone before delivery.                  |

---

## 4. Scope & Exclusions

### In Scope
- Target users: Primary school students, Grades 1–5
- Subject domain: Mathematics only (Number Systems, Fractions & Decimals, Applied Measurement, Geometry & Visuals, Data Handling)
- Interface: Web-based (React) requiring webcam and microphone

---

## 5. System Architecture Overview

PALM operates on a continuous **Perception–Action Cycle** composed of five architectural layers:

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT SIDE                             │
│   Webcam ──► MediaPipe FaceLandmarker (in-browser)          │
│              [Face Mesh, Emotion (Blendshapes),              │
│               Gaze Tracking (Iris Landmarks)]                │
│              ──► perception_update JSON (~100 bytes/sec)     │
│   Microphone ──► Audio Chunks ──► /ws/audio                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ WebSocket (JSON)
┌───────────────────────▼─────────────────────────────────────┐
│              PERCEPTION RECEIVER (FastAPI)                   │
│   Receives { emotion, gaze } from client                    │
│   Updates SessionContext + logs events to DB                │
│   STT via FastRouter                                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│         ORCHESTRATION & STATE MANAGEMENT                    │
│   Context Aggregator → State Prompt Builder                 |
|                           ↑                                 |
│   in-memory (active session) + NeonDB read on session start |
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│           COGNITIVE & KNOWLEDGE ENGINE                      │
│   LangGraph Orchestrator                                    │
│   ├── RAG Agent ──► Pinecone Vector DB                      │
│   ├── Mastery Agent                                         │
│   ├── Engagement Agent                                      │
│   ├── Dialogue Agent                                        │
│   ├── Hint Agent                                            │
│   └── Quiz Agent                                            │
│   LLM Engine via FastRouter                                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              VERIFICATION LAYER                             │
│   Response Validator (Correctness + Tone Audit)             │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              OUTPUT GENERATION LAYER                        │
│   UI Renderer + TTS                                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              FRONTEND — STUDENT INTERFACE                   │
│   React + Tailwind + shadcn/ui Dashboard                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Tech Stack Specification

### 6.1 Frontend

| Technology       | Role              | Notes                                      |
| ---------------- | ----------------- | ------------------------------------------ |
| React (Vite)     | UI Framework      |
| Tailwind CSS     | Styling           |
| shadcn/ui        | Component Library |                                            |
| WebRTC API       | Media Capture     | Browser-native webcam + microphone access  |
| WebSocket Client | Real-time comms   | Bidirectional streaming to FastAPI backend |
| Zustand          | State Management  | Server state caching + client state        |
| KaTeX            | Math Rendering    | Render math formulas in UI                 |

### 6.2 Backend

| Technology             | Role                | Notes                                  |
| ---------------------- | ------------------- | -------------------------------------- |
| FastAPI (Python 3.11+) | API Server          | Async REST + WebSocket endpoints       |
| LangGraph              | Agent Orchestration | Stateful multi-agent workflow graphs   |
| MediaPipe (client)     | Face + Gaze + Emotion | Runs in browser via @mediapipe/tasks-vision |
| FastRouter API         | Speech-to-Text      | Audio transcription                    |
| FastRouter API         | Text-to-Speech      | Natural voice synthesis                |
| Pydantic               | Data Validation     | Schema enforcement for API models      |
| python-dotenv          | Config Management   | Environment variable management        |

### 6.3 LLM & Embeddings Layer

| Technology | Role                   | Notes |
| ---------- | ---------------------- | ----- |
| FastRouter | LLM / Embedding Router |

### 6.4 Vector Database

| Technology | Role         | Notes                                          |
| ---------- | ------------ | ---------------------------------------------- |
| Pinecone   | Vector Store | Stores curriculum embeddings for RAG retrieval |

**Pinecone Index Configuration:**
- **Index Name:** `palm-fyp`
- **Dimensions:** 1536 (for `text-embedding-3-small`)
- **Metric:** Cosine Similarity
- **Metadata Fields:** `grade`, `topic`, `subtopic`, `chunk_index`, `source_doc`
- **Namespaces:** One per grade (`grade-1`, `grade-2`, ... `grade-5`)

**RAG Seeding Pipeline:**
1. Parse NCERT math PDFs using pedagogical chunking (concept-level, ~400 tokens/chunk)
2. Enrich each chunk with metadata (grade, topic, difficulty, concept tags)
3. Embed using FastRouter → `text-embedding-3-small`
4. Upsert to Pinecone with metadata

### 6.5 Relational Database

| Technology | Role             | Notes                                                                   |
| ---------- | ---------------- | ----------------------------------------------------------------------- |
| NeonDB     | Primary Database | Serverless PostgreSQL; stores student profiles, sessions, mastery state |

NeonDB is a serverless PostgreSQL provider.

**Important:**
All AI-related functionalities in the system will be routed through FastRouter, which acts as a unified abstraction and orchestration layer.

FastRouter will handle:

Large Language Model (LLM) inference (chat, summarization, reasoning)
Embedding generation for vector search (Pinecone integration)
Speech-to-Text (STT)
Text-to-Speech (TTS)

The backend will not directly integrate with individual model providers (e.g., OpenAI, Anthropic, Google). Instead, FastRouter will serve as the single interface for all AI operations.

---

## 7. Module-Level Feature Specifications

### 7.1 Perception Engine

**Purpose:** Capture and process multimodal student inputs (video + audio) into structured signals.

#### 7.1.1 Vision Pipeline

| Component           | Implementation                                                                 | Output                                                                                |
| ------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Face Mesh + Gaze    | MediaPipe FaceLandmarker (client-side, @mediapipe/tasks-vision)                | 478 landmarks + iris landmarks → gaze state (on_screen/off_screen/closed_eyes)       |
| Emotion Recognition | MediaPipe FaceLandmarker blendshapes (client-side, threshold logic)            | Emotion label: `{confident, confused, bored, frustrated, neutral}`                   |
| Perception Sender   | usePerceptionStream.js (client → server JSON at max 1/sec)                     | `{"type": "perception_update", "emotion": str, "gaze": str}` ~100 bytes/sec         |

**Note:** The vision pipeline previously ran server-side (OpenCV + MediaPipe + CNN-LSTM on JPEG frames).
As of April 2025, all perception runs client-side using the browser MediaPipe FaceLandmarker SDK.
The server receives only lightweight JSON perception updates (~500x bandwidth reduction).

**Gaze Logic:**
- Compute eye landmark ratios to determine gaze direction
- Label: `on_screen`, `off_screen`, `closed_eyes`
- Track sustained off-screen duration → trigger `gaze_away_flag` if > 3 seconds

**Emotion Classification Logic:**
- MediaPipe FaceLandmarker computes 52 facial blendshapes per frame
- Threshold-based heuristics map specific blendshapes (e.g., browDown, jawDrop) to discrete emotion labels
- Output: categorical emotion state (`confident`, `confused`, `bored`, `frustrated`, `neutral`)

#### 7.1.2 Audio Pipeline

| Component           | Implementation                                                                   | Output                       |
| ------------------- | -------------------------------------------------------------------------------- | ---------------------------- |
| Audio Capture       | WebRTC `getUserMedia` audio stream; VAD-chunked at ~5s segments                  | WAV audio chunks             |
| Speech-to-Text      | fastrouter                                                                       | Transcribed text string      |
| Voice Tone Analysis | Basic prosody features (speaking rate, pause frequency) as supplementary signals | `engaged` / `uncertain` flag |

---

### 7.2 Orchestration & State Management

**Purpose:** Aggregate all perception signals into a unified `StatePrompt` and manage session-level memory.

#### 7.2.1 Context Aggregator

The Context Aggregator collects:
- Transcribed student query (from STT)
- Current emotion label + confidence
- Gaze status (`on_screen` / `off_screen`)
- Last N student responses (rolling window of 5)
- Current topic, subtopic, and difficulty level
- Student mastery score for the current topic (from NeonDB)
- Session history summary (compressed from NeonDB)

It builds a structured `StatePrompt` (JSON object) passed to the LangGraph Orchestrator.

**StatePrompt Schema:**
```json
{
  "student_id": "uuid",
  "session_id": "uuid",
  "query": "What is 3/4 + 1/2?",
  "emotion": { "label": "confused", "confidence": 0.82 },
  "gaze": "on_screen",
  "current_topic": "Fractions",
  "difficulty_level": 2,
  "mastery_score": 0.45,
  "last_responses": ["wrong", "wrong", "correct"],
  "session_summary": "Student struggles with fraction addition. Has mastered whole number addition."
}
```

#### 7.2.2 Session State Storage (NeonDB)

- Every `StatePrompt` snapshot is persisted to `session_events` table
- Mastery scores updated after each interaction
- Session summaries compressed and stored in `sessions` table

---

### 7.3 Cognitive & Knowledge Engine (Multi-Agent)

**Purpose:** Route the `StatePrompt` to the appropriate specialized agent(s) and synthesize the instructional response.

**Framework:** LangGraph (stateful, cyclic agent graphs)

#### 7.3.1 Orchestrator Agent (Logic Router)

The central LangGraph node. Receives `StatePrompt` and decides which agent(s) to invoke based on the following routing rules:

| Condition                                           | Agent Invoked                             |
| --------------------------------------------------- | ----------------------------------------- |
| Normal query on curriculum topic                    | RAG Agent → Dialogue Agent                |
| Emotion = `confused` OR last 2 responses = wrong    | Hint Agent                                |
| Emotion = `frustrated` AND last 3 responses = wrong | Mastery Agent (remedial path)             |
| Gaze = `off_screen` for > 3s OR Emotion = `bored`   | Engagement Agent                          |
| Student answers correctly AND emotion = `confident` | Mastery Agent (advance path) → Quiz Agent |
| Open-ended conversational input                     | Dialogue Agent                            |

#### 7.3.2 RAG Agent

- Takes the student query from `StatePrompt`
- Queries Pinecone index filtered by `grade` and `topic` metadata
- Retrieves top-K (K=5) relevant curriculum chunks
- Augments the prompt with retrieved context
- Passes augmented prompt to LLM via FastRouter

**Retrieval Strategy:**
- Hybrid search: dense vector similarity + metadata filter
- Re-ranking: cross-encoder re-rank on top-10 before selecting top-5
- Context injection format: `[Retrieved Context]\n---\n[Student Query]`

#### 7.3.3 Mastery Agent

- Reads student's current mastery scores from NeonDB
- Determines next concept in the learning path (based on prerequisite graph)
- Two sub-modes:
  - **Remedial Mode** (low mastery): Simplify explanation, use analogies, decrease difficulty
  - **Advance Mode** (high mastery): Increment difficulty, introduce next topic
- Updates mastery score in NeonDB after each interaction

#### 7.3.4 Engagement Agent

- Triggered on boredom/gaze-away detection
- Generates re-engagement micro-activities: riddles, story-math problems, mini-games prompts
- Can pause lesson delivery and request UI to render an interactive challenge card

#### 7.3.5 Dialogue Agent

- Maintains age-appropriate, encouraging conversational tone for Grades 1–5
- Injects persona: "Friendly AI tutor Pal"
- Applies Socratic scaffolding: asks leading questions rather than giving direct answers
- Enforces safe content and positive reinforcement

#### 7.3.6 Hint Agent

- Activated when student is confused or struggling
- Delivers structured, progressive hints (3-tier):
  - Hint 1: Conceptual reminder ("Remember, fractions mean equal parts")
  - Hint 2: Step-by-step scaffold
  - Hint 3: Worked example with similar numbers
- Does NOT reveal the direct answer until all 3 hint tiers are exhausted

#### 7.3.7 Quiz Agent

- Generates formative assessment questions based on current topic and mastery level
- Uses RAG to pull curriculum-aligned question contexts from Pinecone
- Three question types: MCQ, Fill-in-the-blank, Short answer
- Evaluates student response and passes correctness flag to Mastery Agent

#### 7.3.8 LLM Tutor Engine

- All agents produce augmented prompts that are forwarded to the LLM via **FastRouter**
- FastRouter selects the model (GPT-4o primary, Llama-3/Groq fallback based on latency/availability)
- System prompt is injected by FastRouter: persona, safety constraints, output format (markdown with KaTeX for math)
- LLM output is streamed back through FastRouter to the backend

---

### 7.4 RAG Pipeline & Vector DB

**Purpose:** Seed, manage, and query the Pinecone curriculum knowledge base.

#### 7.4.1 Seeding Pipeline (Offline, One-Time)

```
NCERT Math PDFs (Grade 1–5)
        │
        ▼
PDF Parser (pdfplumber / PyMuPDF)
        │
        ▼
Pedagogical Chunker
(concept-level chunking, ~400 tokens,
 preserve examples + diagrams context)
        │
        ▼
Metadata Enrichment
{grade, topic, subtopic, difficulty,
 chunk_index, source_doc, concept_tags}
        │
        ▼
FastRouter → text-embedding-3-small
        │
        ▼
Pinecone Upsert (namespace: grade-N)
```

#### 7.4.2 Query Pipeline (Online, Per Interaction)

```
Student Query (from StatePrompt)
        │
        ▼
Query Embedding via FastRouter
        │
        ▼
Pinecone Query
(filter: grade=N, topic=current_topic,
 top_k=10, namespace=grade-N)
        │
        ▼
Cross-Encoder Re-ranking (top-10 → top-5)
        │
        ▼
Context Assembly
        │
        ▼
Augmented Prompt → LLM via FastRouter
```

---

### 7.5 Response Validator & Verification Layer

**Purpose:** Audit LLM-generated responses before delivery to ensure mathematical correctness and appropriate tone.

#### 7.5.1 Correctness Verifier

- Symbolic math checker: parse numerical/algebraic expressions from LLM output
- Cross-validate against the retrieved RAG context (answer must be present in or derivable from context)
- If mismatch detected → re-query LLM with stricter prompt (max 2 retries) or fall back to RAG-sourced answer directly

#### 7.5.2 Tone Auditor

- Check response against age-appropriateness rules (vocabulary level for Grades 1–5)
- Detect negative/discouraging language → replace with positive alternatives
- Ensure no direct answer is revealed when Hint Agent is active (anti-spoiler guard)

---

### 7.6 Output Generation Layer

**Purpose:** Synthesize and deliver the validated response to the student via UI and audio.

| Component                  | Implementation         | Notes                                                             |
| -------------------------- | ---------------------- | ----------------------------------------------------------------- |
| Text/Math Renderer         | React UI with KaTeX    | Renders formatted math, diagrams, step-by-step solutions          |
| TTS Engine                 | Fastrouter             | Convert response text to warm, child-friendly voice               |
| Animation Controller       | Framer Motion          | Animate tutor avatar, progress indicators, celebrations           |
| Engagement Prompt Renderer | shadcn Card components | Renders re-engagement challenge cards when Engagement Agent fires |

---

### 7.7 Frontend (Student Interface)

**Purpose:** Provide an accessible, child-friendly web UI for students to interact with PALM.

Detailed breakdown in Section 10.

---

## 8. API Design

### 8.1 REST Endpoints

#### Student Management

| Method | Path                            | Description                        |
| ------ | ------------------------------- | ---------------------------------- |
| `POST` | `/api/v1/students`              | Register new student               |
| `GET`  | `/api/v1/students/{student_id}` | Get student profile + mastery data |
| `PUT`  | `/api/v1/students/{student_id}` | Update student profile             |

#### Sessions

| Method  | Path                                | Description                  |
| ------- | ----------------------------------- | ---------------------------- |
| `POST`  | `/api/v1/sessions`                  | Start a new learning session |
| `GET`   | `/api/v1/sessions/{session_id}`     | Get session details          |
| `PATCH` | `/api/v1/sessions/{session_id}/end` | End and summarize a session  |

#### Curriculum

| Method | Path                                      | Description                 |
| ------ | ----------------------------------------- | --------------------------- |
| `GET`  | `/api/v1/curriculum/topics?grade={n}`     | List all topics for a grade |
| `GET`  | `/api/v1/curriculum/next?student_id={id}` | Get recommended next topic  |

#### Mastery

| Method | Path                                  | Description                            |
| ------ | ------------------------------------- | -------------------------------------- |
| `GET`  | `/api/v1/mastery/{student_id}`        | Get full mastery breakdown by topic    |
| `POST` | `/api/v1/mastery/{student_id}/update` | Update mastery score after interaction |

### 8.2 WebSocket Endpoints

| Path                     | Direction       | Description                                                                                        |
| ------------------------ | --------------- | -------------------------------------------------------------------------------------------------- |
| `/ws/video/{session_id}` | Client → Server | Receive perception updates (JSON: emotion + gaze, max 1/sec, ~100 bytes/sec)                       |
| `/ws/audio/{session_id}` | Client → Server | Stream audio chunks (WAV)                                                                          |
| `/ws/tutor/{session_id}` | Bidirectional   | Main interaction channel: send `StatePrompt`, receive streamed LLM response tokens + TTS audio URL |

### 8.3 Request/Response Schemas (Key Examples)

**POST `/api/v1/sessions` — Request:**
```json
{
  "student_id": "uuid",
  "grade": 3,
  "topic": "Fractions"
}
```

**WebSocket `/ws/tutor/{session_id}` — Incoming Message:**
```json
{
  "type": "state_prompt",
  "payload": {
    "query": "I don't understand how to add fractions",
    "emotion": { "label": "confused", "confidence": 0.79 },
    "gaze": "on_screen",
    "current_topic": "Fractions",
    "difficulty_level": 2
  }
}
```

**WebSocket `/ws/tutor/{session_id}` — Outgoing Message (streamed):**
```json
{
  "type": "token",
  "payload": { "token": "Let's", "done": false }
}
```
```json
{
  "type": "response_complete",
  "payload": {
    "full_text": "Let's think about fractions as slices of a pizza...",
    "tts_url": "https://cdn.elevenlabs.io/audio/abc123.mp3",
    "agent_used": "hint_agent",
    "mastery_delta": -0.05
  }
}
```

---

## 9. Database Schema

All tables stored in **NeonDB** (serverless PostgreSQL). Use `asyncpg` + SQLAlchemy async ORM.

### 9.1 Tables

#### `students`
```sql
CREATE TABLE students (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,
    grade           SMALLINT NOT NULL CHECK (grade BETWEEN 1 AND 5),
    age             SMALLINT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `sessions`
```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID REFERENCES students(id) ON DELETE CASCADE,
    grade           SMALLINT NOT NULL,
    topic           VARCHAR(100),
    started_at      TIMESTAMPTZ DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    summary         TEXT,   -- LLM-compressed session summary
    total_turns     INTEGER DEFAULT 0
);
```

#### `session_events`
```sql
CREATE TABLE session_events (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp       TIMESTAMPTZ DEFAULT now(),
    event_type      VARCHAR(50),  -- 'student_query', 'agent_response', 'emotion_event', 'gaze_event'
    emotion_label   VARCHAR(30),
    gaze_status     VARCHAR(20),
    agent_used      VARCHAR(50),
    query_text      TEXT,
    response_text   TEXT,
    is_correct      BOOLEAN
);
```

#### `mastery_scores`
```sql
CREATE TABLE mastery_scores (
    id              BIGSERIAL PRIMARY KEY,
    student_id      UUID REFERENCES students(id) ON DELETE CASCADE,
    grade           SMALLINT NOT NULL,
    topic           VARCHAR(100) NOT NULL,
    subtopic        VARCHAR(100),
    score           FLOAT DEFAULT 0.0 CHECK (score BETWEEN 0.0 AND 1.0),
    attempts        INTEGER DEFAULT 0,
    last_updated    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(student_id, grade, topic, subtopic)
);
```

#### `curriculum_topics`
```sql
CREATE TABLE curriculum_topics (
    id              SERIAL PRIMARY KEY,
    grade           SMALLINT NOT NULL,
    topic           VARCHAR(100) NOT NULL,
    subtopic        VARCHAR(100),
    prerequisite_topic_id INTEGER REFERENCES curriculum_topics(id),
    difficulty      SMALLINT CHECK (difficulty BETWEEN 1 AND 5),
    description     TEXT
);
```

### 9.2 Indexes

```sql
CREATE INDEX idx_sessions_student ON sessions(student_id);
CREATE INDEX idx_events_session ON session_events(session_id);
CREATE INDEX idx_mastery_student ON mastery_scores(student_id, grade, topic);
```

---

## 10. Frontend UI Specifications

**Framework:** React (Vite) + Tailwind CSS + shadcn/ui  
**Routing:** React Router v6  
**State:** Zustand 

### 10.1 Pages / Routes

| Route        | Page            | Description                                   |
| ------------ | --------------- | --------------------------------------------- |
| `/`          | Landing / Login | Student name entry + grade selection          |
| `/dashboard` | Dashboard       | Progress overview, topic map, recent sessions |
| `/session`   | Active Session  | Main tutoring interface (camera, chat, TTS)   |
| `/progress`  | Progress Report | Mastery heatmap, session history, weak areas  |

### 10.2 Active Session Page — Component Breakdown

```
┌─────────────────────────────────────────────────────────┐
│  HEADER: Topic: Fractions  |  Grade 3  |  End Session   │
├──────────────────────┬──────────────────────────────────┤
│                      │                                   │
│   WEBCAM PREVIEW     │   TUTOR CHAT AREA                │
│   (small, top-right) │   - Tutor avatar (animated)      │
│   + emotion badge    │   - Scrollable message history   │
│   + gaze indicator   │   - Math rendered with KaTeX     │
│                      │   - Re-engagement cards          │
├──────────────────────┴──────────────────────────────────┤
│   MASTERY BAR: Fractions ████████░░ 80%                 │
│   INPUT BAR: [🎤 Speaking... / Type your answer] [Send] │
└─────────────────────────────────────────────────────────┘
```

### 10.3 Key shadcn/ui Components Used

| Component  | Usage                                                          |
| ---------- | -------------------------------------------------------------- |
| `Card`     | Tutor message bubbles, re-engagement challenge cards           |
| `Badge`    | Emotion state indicator, difficulty badge                      |
| `Progress` | Mastery score bars                                             |
| `Avatar`   | Tutor Pal avatar                                               |
| `Sheet`    | Session summary panel                                          |
| `Tabs`     | Dashboard tabs (Progress, Topics, History)                     |
| `Alert`    | System notifications (e.g., "Great job! Moving to next topic") |
| `Skeleton` | Loading states during LLM streaming                            |
| `Tooltip`  | Hint system explanations                                       |
and other relevant shadcn/ui components.

### 10.4 Emotion & Gaze Overlay

- Webcam preview rendered in a `<video>` element (WebRTC)
- Emotion + gaze classified client-side via MediaPipe FaceLandmarker (useFaceMesh.js)
- Emotion label displayed as a shadcn `Badge` below the webcam (`Confused 😕`, `Bored 😴`, etc.)
- Gaze indicator: Eye icon shows `Focused` / `Looking Away` / `Eyes Closed` with color change
- Perception updates sent to backend via WebSocket as JSON at max 1/sec (~100 bytes/sec)
- No JPEG frames are streamed to the backend

### 10.5 Math Rendering

- All LLM responses parsed for LaTeX delimiters (`$$...$$`, `\(...\)`)
- Rendered client-side using `react-katex`
- Step-by-step solutions rendered as numbered `<ol>` with individual math expressions

---

## 11. Adaptive Feedback Logic

The system implements three non-linear feedback loops, each triggered by combined signals from the `StatePrompt`:

### 11.1 Struggle Loop

**Trigger Conditions:**
- Student answer is incorrect AND emotion = `confused` OR `frustrated`
- OR: Last 2 consecutive answers are wrong

**Actions (in order):**
1. Orchestrator routes to **Hint Agent** (Tier 1 hint)
2. If still wrong → Hint Agent (Tier 2)
3. If still wrong → Hint Agent (Tier 3) + Mastery Agent sets difficulty to `remedial`
4. Mastery score for topic decremented by 0.1 per wrong answer
5. UI renders a "Let's try a simpler problem first" card

### 11.2 Boredom Loop

**Trigger Conditions:**
- Gaze = `off_screen` sustained for ≥ 3 seconds
- OR: Emotion = `bored` with confidence ≥ 0.7

**Actions:**
1. Orchestrator routes to **Engagement Agent**
2. Engagement Agent generates a re-engagement activity (math riddle, visual puzzle, mini-story problem)
3. UI renders an interactive `EngagementCard` component (shadcn `Card` with animated border)
4. Lesson resumes after student engages with the card
5. TTS delivers a friendly "Hey, let's try something fun!" prompt

### 11.3 Mastery Loop

**Trigger Conditions:**
- Student answer is correct AND emotion = `confident` OR `neutral`
- Mastery score for current topic ≥ 0.85

**Actions:**
1. Orchestrator routes to **Mastery Agent** (advance mode)
2. Mastery Agent queries NeonDB for next topic in prerequisite graph
3. Mastery score incremented by 0.1 per correct answer
4. UI renders a celebration animation (confetti via Framer Motion)
5. Quiz Agent generates 2 consolidation questions before topic transition

---

## New Student Flow —   

Here is the exact end-to-end flow:

### Step 1 — Landing Page
Student opens the web app. They see a simple onboarding form:
- Enter your name
- Select your grade (1–5)

No password. No email. They click **"Start Learning"**.

**What happens in the background:**
```
Frontend → POST /api/v1/students
         { name: "Riya", grade: 3 }

NeonDB → INSERT into students
         returns student_id (UUID)

Zustand → stores { studentId, name, grade }
```

---

### Step 2 — Dashboard
Student lands on their dashboard. Since they're new, it's mostly empty — no past sessions, no mastery data yet.

They see:
- A topic map for Grade 3 (all topics listed, all at 0% mastery)
- A **"Start Session"** button

Student picks a topic — say, **Fractions** — and clicks Start Session.

**What happens in the background:**
```
Frontend → POST /api/v1/sessions
         { studentId, grade: 3, topic: "Fractions" }

NeonDB → INSERT into sessions
         returns session_id (UUID)

NeonDB → SELECT mastery_scores WHERE student_id = ?
         (empty for new student, defaults all to 0.0)

NeonDB → SELECT summary FROM sessions (last session)
         (null for new student)

SessionContext object created in FastAPI memory:
{
  student_id, session_id,
  current_topic: "Fractions",
  difficulty_level: 1,        ← starts at easiest
  conversation_history: [],
  mastery_scores: {},          ← all zero
  last_session_summary: null
}
```

---

### Step 3 — Session Page Loads
The student sees the main tutoring interface:
- Webcam preview (small, top-right)
- Empty chat area with tutor avatar
- Microphone button
- Topic: Fractions | Grade 3

Two things happen simultaneously:

**WebSocket connections open:**
```
/ws/video/{session_id}   ← client sends perception updates (JSON, max 1/sec)
/ws/tutor/{session_id}   ← main interaction channel opens
```

**Tutor sends the opening message:**

The Orchestrator automatically fires a greeting via the Dialogue Agent — no student input needed:

> *"Hi Riya! 👋 Today we're going to learn about Fractions. Before we start, can you tell me — have you heard the word 'fraction' before?"*

This is delivered as streamed tokens to the UI + TTS audio plays.

---

### Step 4 — Perception Engine Activates
From this point on, on every animation frame:

```
Webcam video → MediaPipe FaceLandmarker (in-browser)
              → Emotion classification (blendshape thresholds)
              → Gaze tracking (iris landmarks 473/468)
              → Result: { emotion: "neutral", gaze: "on_screen" }
              → Sent to /ws/video/{session_id} as JSON (max 1/sec)
              → FastAPI → Stored in SessionContext (in-memory)
```

And whenever the student speaks:
```
Microphone audio → WebRTC VAD detects speech → 5s audio chunk
                 → /ws/audio/{session_id}
                 → FastAPI → FastRouter → Whisper STT
                 → Transcribed text stored in SessionContext
```

---

### Step 5 — Student Responds
Riya says (or types): *"Yes I think it means like half of something?"*

**State Prompt is built:**
```json
{
  "student_id": "uuid",
  "session_id": "uuid",
  "query": "Yes I think it means like half of something?",
  "emotion": { "label": "neutral", "confidence": 0.74 },
  "gaze": "on_screen",
  "current_topic": "Fractions",
  "difficulty_level": 1,
  "mastery_score": 0.0,
  "last_responses": [],
  "session_summary": null
}
```

**Orchestrator receives StatePrompt → decides: normal query → RAG Agent + Dialogue Agent**

```
RAG Agent → FastRouter → embed("Fractions introduction grade 3")
          → Pinecone query (namespace: grade-3, topic: Fractions, top-k: 5)
          → retrieves curriculum chunks about fraction basics
          → augmented prompt assembled

Dialogue Agent → injects persona + Socratic tone

FastRouter → GPT-4o
           → streams response tokens back
```

**Response delivered:**
> *"Exactly right, Riya! 🌟 A fraction IS like splitting something equally. Imagine a pizza cut into 4 equal slices — if you eat 1 slice, you've eaten 1 out of 4 slices. We write that as 1/4. The bottom number tells us how many total pieces, and the top number tells us how many we took. Does that make sense?"*

Tokens stream into the UI. TTS plays the audio.

---

### Step 6 — Lesson Continues (Happy Path)
Student keeps answering correctly, emotion stays confident/neutral, gaze stays on screen.

After each correct answer:
```
Mastery Agent → mastery_score += 0.1
NeonDB → UPDATE mastery_scores SET score = 0.1
UI → Fractions progress bar updates to 10%
```

---

### Step 7 — Boredom Loop Fires
After a few minutes, Riya's gaze drifts away for 4 seconds. Emotion reads as `bored`.

```
Perception → { gaze: "off_screen" (4s), emotion: "bored", confidence: 0.71 }

StatePrompt built → Orchestrator detects boredom trigger

→ routes to Engagement Agent

Engagement Agent → FastRouter → GPT-4o
generates: "If you had a chocolate bar with 8 pieces and you ate 3,
            what fraction did you eat?"

WebSocket sends: { type: "engagement_card", content: "..." }

Zustand → showEngagementCard = true
UI → EngagementCard renders with the generated challenge
TTS → "Hey Riya, let's try something fun! 🎯"
```

Student engages with the card → card dismisses → lesson resumes.

---

### Step 8 — Struggle Loop Fires
Later, Riya gets a fraction addition question wrong twice.

```
last_responses: ["wrong", "wrong"]
emotion: "confused", confidence: 0.80

Orchestrator → routes to Hint Agent (Tier 1)
```

> *"Here's a hint — before adding fractions, check if the bottom numbers are the same. Are they the same in your problem?"*

Still wrong → Hint Tier 2 → Hint Tier 3 → difficulty drops to remedial.

```
Mastery Agent → mastery_score -= 0.1
NeonDB → UPDATE mastery_scores SET score = ...
```

---

### Step 9 — Session End
Student clicks **"End Session"** or closes the tab.

```
Frontend → PATCH /api/v1/sessions/{session_id}/end

FastAPI → FastRouter → GPT-4o
        → summarize conversation_history into 2-3 sentences
        → "Riya showed understanding of basic fraction concepts.
           Struggled with fraction addition. Mastered fraction identification."

NeonDB → UPDATE sessions SET
           ended_at = now(),
           summary = "...",
           total_turns = 14

NeonDB → final mastery_scores flush (all topic scores written)

SessionContext object → destroyed (memory freed)
WebSocket connections → closed
```

UI shows a session summary card:
- Topics covered
- Mastery gained
- "Great session, Riya! 🎉"

---

### Step 10 — Next Visit
When Riya comes back, she enters her name + grade again (no login). The frontend queries:

```
GET /api/v1/students?name=Riya&grade=3
→ finds existing student_id by name + grade match
→ loads mastery_scores from NeonDB
→ loads last session summary from NeonDB
→ Dashboard shows her progress from last time
```

The session picks up exactly where she left off in terms of mastery and difficulty level.

---

This is the complete flow. The only assumptions baked in are that name + grade is enough to identify a returning student (no auth), and that all AI calls go through FastRouter without exception.

## 13. Implementation Phases & Milestones

### Phase 1 — Foundation & RAG Pipeline

- [ ] NeonDB setup: define and migrate all schemas
- [ ] Pinecone index creation + seeding pipeline (NCERT PDFs → Pinecone)
- [ ] FastRouter integration
- [ ] FastAPI project scaffolding: project structure, config, env management
- [ ] Basic `/api/v1/students` and `/api/v1/sessions` REST endpoints
- [ ] RAG Agent: end-to-end retrieval + LLM augmented prompt → response
- [ ] Simple chat UI to test RAG Agent responses

**Deliverable:** Working RAG-powered math Q&A with curriculum grounding.

### Phase 2 — Perception Engine

- [ ] WebRTC video + audio capture in React
- [ ] Lightweight JSON WebSocket streaming (perception updates) to FastAPI backend
- [ ] MediaPipe FaceLandmarker integration on the client-side (gaze/face tracking)
- [ ] Threshold-based emotion classification using facial blendshapes
- [ ] STT integration for audio chunks
- [ ] Emotion + gaze signal display in UI (badge + indicator)
- [ ] `session_events` recording pipeline operational

**Deliverable:** Real-time perception pipeline (emotion, gaze, STT) with signals displayed on UI.

### Phase 3 — Multi-Agent Orchestration

- [ ] LangGraph Orchestrator graph definition
- [ ] All 6 agents implemented (RAG, Mastery, Engagement, Dialogue, Hint, Quiz)
- [ ] StatePrompt builder + Context Aggregator
- [ ] Adaptive feedback loops (Struggle, Boredom, Mastery) wired to agent routing
- [ ] Mastery score update pipeline (NeonDB reads/writes after each interaction)
- [ ] Response Validator (math correctness + tone audit)

**Deliverable:** Fully adaptive tutoring session with all agents operational.

### Phase 4 — Output, UI Polish & Integration

- [ ] ElevenLabs TTS integration (audio response playback in React)
- [ ] KaTeX math rendering in chat messages
- [ ] Re-engagement card UI (Engagement Agent output rendered in UI)
- [ ] Dashboard page (mastery heatmap, topic progress, session history)
- [ ] Progress report page
- [ ] Framer Motion animations (celebrations, avatar)
- [ ] End-to-end integration tests (full Perception–Action Cycle)

**Deliverable:** Production-ready full system with polished UI and complete integration.

### Phase 5 — Testing, Evaluation & Documentation
- [ ] RAGAS evaluation of RAG pipeline (Faithfulness, Answer Relevance)
- [ ] Emotion model evaluation (F1 score on test split)
- [ ] Latency profiling and optimization (FastRouter, WebSocket throughput)
- [ ] User testing with target-age students
- [ ] Stage 2 report documentation

---