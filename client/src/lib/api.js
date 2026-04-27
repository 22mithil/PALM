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

export async function getChapterSections(chapterId, token) {
  const res = await fetch(`${API}/topics/${chapterId}/sections`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ section_id, order, concept, title, difficulty }]
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
  return res.json(); // [{ chapter_id, current_section_id, section_statuses, completion_percent, was_completed, last_updated }]
}

export async function resetSection(studentId, chapterId, sectionId, token) {
  const res = await fetch(`${API}/mastery/${studentId}/${chapterId}/reset-section`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({ section_id: sectionId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to reset section");
  return data;
}

// ── Sessions ────────────────────────────────────────────────────────────

export async function getStudentSessions(studentId, token) {
  const res = await fetch(`${API}/sessions/student/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // [{ id, chapter_id, grade, started_at, ended_at, turn_count, duration_seconds, session_summary, message_count }]
}

export async function getSessionEvents(sessionId, token) {
  const res = await fetch(`${API}/sessions/${sessionId}/events`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  return res.json(); // { total, messages: [{role, content}] }
}

export async function getSessionMessages(sessionId, offset = 0, limit = 20, token) {
  const res = await fetch(`${API}/sessions/${sessionId}/events?offset=${offset}&limit=${limit}`, {
    headers: headers(token),
  });
  if (!res.ok) return { total: 0, messages: [] };
  return res.json(); // { total, messages }
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

export async function endSession(sessionId, { durationSeconds } = {}, token) {
  // Issue 9: PATCH to set ended_at and compute duration
  try {
    const res = await fetch(`${API}/sessions/${sessionId}/end`, {
      method: "PATCH",
      headers: headers(token),
    });
    if (res.ok) return res.json();
  } catch (_) {}
  return {};
}

// ── Chat History (legacy — kept for compatibility) ───────────────────────

export async function getChatHistory(studentId, chapterId, token) {
  const sessions = await getStudentSessions(studentId, token);
  const chapterSessions = sessions.filter((s) => s.chapter_id === chapterId);
  const allMessages = [];
  for (const sess of chapterSessions) {
    const events = await getSessionEvents(sess.id, token);
    const msgs = events.messages || events || [];
    if (msgs.length > 0) {
      allMessages.push({
        sessionId: sess.id,
        startedAt: sess.started_at,
        messages: msgs,
      });
    }
  }
  return allMessages;
}

// ── Session History (new lazy approach) ──────────────────────────────────

export async function getSessionHistory(studentId, chapterId, token) {
  const sessions = await getStudentSessions(studentId, token);
  return sessions.filter((s) => s.chapter_id === chapterId);
}

// ── Student ─────────────────────────────────────────────────────────────

export async function getStudent(studentId, token) {
  const res = await fetch(`${API}/students/${studentId}`, {
    headers: headers(token),
  });
  if (!res.ok) return null;
  return res.json();
}
