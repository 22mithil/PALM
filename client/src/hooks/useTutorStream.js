import { useRef, useCallback, useEffect, useState } from "react"

/**
 * useTutorStream — Tutor WebSocket hook.
 *
 * Connects to /ws/tutor/{session_id} and sends trigger messages
 * containing the student's transcribed speech.  Receives streamed
 * tutor responses (token-by-token) and a final response_complete.
 *
 * Client → Server:
 *   { "type": "trigger", "payload": { "student_id": "...", "query": "..." } }
 *
 * Server → Client:
 *   { "type": "token",             "payload": { "token": "word ", "done": false } }
 *   { "type": "token",             "payload": { "token": "",      "done": true  } }
 *   { "type": "response_complete", "payload": { "full_text": "...", "agent_used": "...", "mastery_delta": 0.05 } }
 *   { "type": "error",             "payload": { "message": "..." } }
 *
 * @param {string} sessionId — unique session identifier
 */

const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
}

const RECONNECT_DELAY_MS = 3000
const MAX_RECONNECTS = 5

export default function useTutorStream(sessionId) {
  /* ── refs ──────────────────────────────────────────────── */
  const wsRef = useRef(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const isActiveRef = useRef(false)

  /* ── state (for UI consumption) ────────────────────────── */
  const [wsState, setWsState] = useState("idle") // idle | connecting | open | closed | error
  const [isStreaming, setIsStreaming] = useState(false) // true while tokens are arriving
  const [streamingText, setStreamingText] = useState("") // accumulates tokens in real-time
  const [lastResponse, setLastResponse] = useState(null) // { full_text, agent_used, mastery_delta }
  const [tutorError, setTutorError] = useState(null)

  /* ── WebSocket URL builder ─────────────────────────────── */
  const buildWsUrl = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}/ws/tutor/${sessionId}`
  }, [sessionId])

  /* ── WebSocket lifecycle ───────────────────────────────── */
  const connect = useCallback(() => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WS_READY_STATE.OPEN ||
        wsRef.current.readyState === WS_READY_STATE.CONNECTING)
    ) {
      return
    }

    setWsState("connecting")
    const ws = new WebSocket(buildWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      setWsState("open")
      reconnectCountRef.current = 0
      console.log("[useTutorStream] WS connected")
    }

    ws.onclose = () => {
      setWsState("closed")

      // Auto-reconnect if still active
      if (
        isActiveRef.current &&
        reconnectCountRef.current < MAX_RECONNECTS
      ) {
        reconnectCountRef.current += 1
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    ws.onerror = () => {
      setWsState("error")
      // onclose will fire next — reconnect logic lives there
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        const { type, payload } = msg

        switch (type) {
          case "token": {
            if (payload.done) {
              setIsStreaming(false)
            } else {
              setIsStreaming(true)
              setStreamingText((prev) => prev + payload.token)
            }
            break
          }

          case "response_complete": {
            setLastResponse(payload)
            setStreamingText("") // reset for next cycle
            setIsStreaming(false)
            console.log(
              "[useTutorStream] Response complete:",
              payload.agent_used,
              `(${payload.full_text.length} chars)`
            )
            break
          }

          case "error": {
            setTutorError(payload.message)
            setIsStreaming(false)
            console.error("[useTutorStream] Server error:", payload.message)
            break
          }

          default:
            console.warn("[useTutorStream] Unknown message type:", type)
        }
      } catch {
        // non-JSON or malformed — ignore
      }
    }
  }, [buildWsUrl])

  const disconnect = useCallback(() => {
    isActiveRef.current = false

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.onclose = null // prevent reconnect on intentional close
      wsRef.current.close()
      wsRef.current = null
    }

    setWsState("idle")
    setIsStreaming(false)
    setStreamingText("")
    reconnectCountRef.current = 0
  }, [])

  /* ── public API ────────────────────────────────────────── */

  /** Start the Tutor WebSocket connection. */
  const startStream = useCallback(() => {
    isActiveRef.current = true
    connect()
  }, [connect])

  /** Stop the Tutor WebSocket connection. */
  const stopStream = useCallback(() => {
    disconnect()
  }, [disconnect])

  /**
   * Send a trigger message with the student's query to the tutor.
   * @param {string} studentId — the student UUID
   * @param {string} query     — the transcribed speech text
   */
  const sendTrigger = useCallback((studentId, query) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WS_READY_STATE.OPEN) {
      console.warn("[useTutorStream] Cannot send trigger — WS not open")
      return
    }

    if (!query || !query.trim()) return

    const msg = JSON.stringify({
      type: "trigger",
      payload: {
        student_id: studentId,
        query: query.trim(),
      },
    })

    ws.send(msg)
    setTutorError(null) // clear previous error on new trigger
    setStreamingText("") // reset streaming text for new response
    console.log("[useTutorStream] Trigger sent:", query.trim().slice(0, 80))
  }, [])

  /** Dismiss the current tutor error. */
  const clearTutorError = useCallback(() => {
    setTutorError(null)
  }, [])

  /* ── cleanup on unmount ────────────────────────────────── */
  useEffect(() => {
    return () => {
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    /** Open WS connection to tutor endpoint. */
    startStream,
    /** Close WS connection. */
    stopStream,
    /** Send a trigger message with transcript query. */
    sendTrigger,
    /** Current WebSocket state: idle | connecting | open | closed | error */
    wsState,
    /** True while tokens are being streamed from the tutor. */
    isStreaming,
    /** Accumulated streaming text (resets on response_complete). */
    streamingText,
    /** Last complete response payload: { full_text, agent_used, mastery_delta } */
    lastResponse,
    /** Current error message from the tutor, if any. */
    tutorError,
    /** Clear the current tutor error. */
    clearTutorError,
  }
}
