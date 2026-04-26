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
  return res.json(); // [{ id, grade, topic, subject, section_count }]
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

// ── Mastery / Progress ──────────────────────────────────────────────────

export async function getMastery(studentId, token) {
  const res = await fetch(`${API}/mastery/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ chapter_id, current_section_id, section_statuses, completion_percent, last_updated }]
}

// ── Sessions ────────────────────────────────────────────────────────────

export async function getStudentSessions(studentId, token) {
  const res = await fetch(`${API}/sessions/student/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ id, chapter_id, grade, started_at, turn_count, session_summary }]
}

export async function getSessionEvents(sessionId, token) {
  const res = await fetch(`${API}/sessions/${sessionId}/events`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ role, content }] — last_10_messages JSONB
}

export async function createSession({ studentId, grade, topic }, token) {
  // Find chapter_id from topic name — fetch topics first
  let chapter_id = 2; // default: Fractions
  try {
    const topics = await getTopics(grade);
    const match = topics.find((t) => t.topic === topic);
    if (match) chapter_id = match.id;
  } catch (_) {}

  const res = await fetch(`${API}/sessions/`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({ student_id: studentId, grade, chapter_id }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to create session");
  return data;
}

export async function endSession(sessionId, { durationSeconds, masteryScore, summary } = {}, token) {
  // End session is now a no-op PATCH — session data is already persisted by the pipeline.
  // We keep the call so the frontend doesn't break, but there's nothing to update.
  // Just return the session data.
  try {
    const res = await fetch(`${API}/sessions/${sessionId}`, {
      headers: headers(token),
    });
    if (res.ok) return res.json();
  } catch (_) {}
  return {};
}

// ── Chat History ────────────────────────────────────────────────────────

export async function getChatHistory(studentId, chapterId, token) {
  // Fetch all sessions for this student, filter by chapter, collect messages
  const sessions = await getStudentSessions(studentId, token);
  const chapterSessions = sessions.filter((s) => s.chapter_id === chapterId);

  const allMessages = [];
  for (const sess of chapterSessions) {
    const events = await getSessionEvents(sess.id, token);
    if (events && events.length > 0) {
      allMessages.push({
        sessionId: sess.id,
        startedAt: sess.started_at,
        messages: events,
      });
    }
  }
  return allMessages; // [{ sessionId, startedAt, messages: [{role, content}] }]
}

// ── Student ─────────────────────────────────────────────────────────────

export async function getStudent(studentId, token) {
  const res = await fetch(`${API}/students/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return null;
  return res.json();
}
