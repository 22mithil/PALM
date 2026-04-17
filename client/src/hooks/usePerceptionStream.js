import { useRef, useCallback, useEffect, useState } from "react"

/**
 * usePerceptionStream — Lightweight perception sender.
 *
 * Sends client-side perception results (emotion + gaze) to the backend
 * via WebSocket as a tiny JSON message. Replaces the old useVideoStream
 * hook that streamed JPEG frames at ~5 FPS (~50KB/s).
 *
 * Wire format (outbound):
 *   { "type": "perception_update", "emotion": "...", "gaze": "...", "timestamp": ... }
 *
 * Throttled: sends at most once per second, and only when values change.
 * Bandwidth: ~100 bytes/sec (500x reduction vs JPEG streaming).
 *
 * @param {string} sessionId — unique session identifier
 */

const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
}

const SEND_INTERVAL_MS = 1000 // max 1 perception update per second
const RECONNECT_DELAY_MS = 3000
const MAX_RECONNECTS = 5

export default function usePerceptionStream(sessionId) {
  /* ── refs ──────────────────────────────────────────────── */
  const wsRef = useRef(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const isActiveRef = useRef(false)

  // Change detection + throttle refs
  const lastSentRef = useRef({ emotion: null, gaze: null })
  const lastSentTimeRef = useRef(0)

  /* ── state (for UI consumption) ────────────────────────── */
  const [wsState, setWsState] = useState("idle") // idle | connecting | open | closed | error

  /* ── WebSocket URL builder ─────────────────────────────── */
  const buildWsUrl = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}/ws/video/${sessionId}`
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

    ws.onmessage = () => {
      // Server may send acks or updates — currently unused
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
    reconnectCountRef.current = 0
    lastSentRef.current = { emotion: null, gaze: null }
    lastSentTimeRef.current = 0
  }, [])

  /* ── public API ────────────────────────────────────────── */

  /** Start the perception stream WebSocket connection. */
  const startStream = useCallback(() => {
    isActiveRef.current = true
    connect()
  }, [connect])

  /** Stop the perception stream and close WebSocket. */
  const stopStream = useCallback(() => {
    disconnect()
  }, [disconnect])

  /**
   * Send a perception update to the backend.
   * Throttled (max 1/sec) and change-detected (skips if same as last).
   * Call this on every frame from useFaceMesh.
   */
  const sendPerception = useCallback((emotion, gaze) => {
    const now = Date.now()
    const changed =
      emotion !== lastSentRef.current.emotion ||
      gaze !== lastSentRef.current.gaze
    const throttled = now - lastSentTimeRef.current < SEND_INTERVAL_MS

    if (!changed || throttled) return
    if (!wsRef.current || wsRef.current.readyState !== WS_READY_STATE.OPEN)
      return

    const payload = JSON.stringify({
      type: "perception_update",
      emotion,
      gaze,
      timestamp: now,
    })

    wsRef.current.send(payload)
    lastSentRef.current = { emotion, gaze }
    lastSentTimeRef.current = now
  }, [])

  /* ── cleanup on unmount ────────────────────────────────── */
  useEffect(() => {
    return () => {
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    /** Open WS connection for perception stream. */
    startStream,
    /** Close WS + stop perception stream. */
    stopStream,
    /** Send perception update (throttled + change-detected). */
    sendPerception,
    /** Current WebSocket state: idle | connecting | open | closed | error */
    wsState,
  }
}
