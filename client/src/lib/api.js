/**
 * API client — centralized backend calls with JWT auth headers.
 */

const API = "/api/v1";

function headers(token) {
  const h = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

// ── Topics ──────────────────────────────────────────────────────────────

export async function getTopics(grade) {
  const res = await fetch(`${API}/topics/?grade=${grade}`, {
    headers: headers(),
  });
  if (!res.ok) return [];
  return res.json(); // [{ id, grade, topic, subtopic, difficulty, description }]
}

// ── Auth ────────────────────────────────────────────────────────────────

export async function register({ name, email, password, grade, age }) {
  const res = await fetch(`${API}/auth/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ name, email, password, grade, age: age || null }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Registration failed");
  return data; // { access_token, token_type, student }
}

export async function login({ email, password }) {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Login failed");
  return data; // { access_token, token_type, student }
}

// ── Mastery ─────────────────────────────────────────────────────────────

export async function getMastery(studentId, token) {
  const res = await fetch(`${API}/mastery/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ topic, grade, score, attempts, last_updated }]
}

// ── Sessions ────────────────────────────────────────────────────────────

export async function getStudentSessions(studentId, token) {
  const res = await fetch(`${API}/sessions/student/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ id, grade, topic, started_at, ended_at, total_turns, summary }]
}

export async function getSessionEvents(sessionId, token) {
  const res = await fetch(`${API}/sessions/${sessionId}/events`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ event_type, query_text, response_text, agent_used, ... }]
}

export async function createSession({ studentId, grade, topic }, token) {
  const res = await fetch(`${API}/sessions/`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({ student_id: studentId, grade, topic }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to create session");
  return data;
}

export async function endSession(sessionId, { durationSeconds, masteryScore, summary } = {}, token) {
  const body = {};
  if (durationSeconds != null) body.duration_seconds = durationSeconds;
  if (masteryScore != null) body.mastery_score = masteryScore;
  if (summary) body.summary = summary;

  const res = await fetch(`${API}/sessions/${sessionId}/end`, {
    method: "PATCH",
    headers: headers(token),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to end session");
  return data;
}

// ── Student ─────────────────────────────────────────────────────────────

export async function getStudent(studentId, token) {
  const res = await fetch(`${API}/students/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return null;
  return res.json();
}
