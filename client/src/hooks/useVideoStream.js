// ──────────────────────────────────────────────────────────────────────
// DEPRECATED: This hook is no longer used in the active code path.
// Emotion + gaze tracking are now handled entirely client-side by
// useFaceMesh.js. Perception results are sent to the backend via
// usePerceptionStream.js as lightweight JSON (~100 bytes/sec) instead
// of JPEG frames (~50KB/sec).
//
// Kept for reference only. Do not import in new code.
// ──────────────────────────────────────────────────────────────────────

import { useRef, useCallback, useEffect, useState } from "react"

/**
 * @deprecated Use usePerceptionStream.js instead.
 * useVideoStream — Transport + perception-receive hook.
 *
 * Captures JPEG frames from a <video> element via an offscreen canvas,
 * resizes to 320×240, compresses at quality ~0.6, and sends each frame
 * over a WebSocket at ~5 FPS (every 200 ms).
 *
 * Wire format (outbound):
 *   { "type": "frame", "data": "<base64>" }
 *
 * Receives real-time perception updates from the backend (max 1/sec):
 *   {
 *     "type": "perception_update",
 *     "payload": {
 *       "emotion": { "label": "...", "confidence": ... },
 *       "gaze": "..."
 *     }
 *   }
 *
 * @param {string}  sessionId   — unique session identifier
 * @param {Object}  options
 * @param {number}  [options.fps=5]           — target frames per second
 * @param {number}  [options.width=320]       — output frame width
 * @param {number}  [options.height=240]      — output frame height
 * @param {number}  [options.quality=0.6]     — JPEG quality 0-1
 * @param {number}  [options.reconnectDelay=3000] — ms before reconnect attempt
 * @param {number}  [options.maxReconnects=5]     — max consecutive reconnects
 * @param {Function} [options.onPerceptionUpdate] — optional callback fired on each perception update
 */

const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
}

export default function useVideoStream(sessionId, options = {}) {
  const {
    fps = 5,
    width = 320,
    height = 240,
    quality = 0.6,
    reconnectDelay = 3000,
    maxReconnects = 5,
    onPerceptionUpdate = null,
  } = options

  /* ── refs ──────────────────────────────────────────────── */
  const wsRef = useRef(null)
  const intervalRef = useRef(null)
  const canvasRef = useRef(null)            // offscreen canvas (reused)
  const videoElRef = useRef(null)           // populated by consumer via setVideoElement
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const isStreamingRef = useRef(false)
  const perceptionCbRef = useRef(onPerceptionUpdate)   // stable ref for callback

  // Keep the callback ref in sync without triggering re-memoisation
  useEffect(() => {
    perceptionCbRef.current = onPerceptionUpdate
  }, [onPerceptionUpdate])

  /* ── state (for UI consumption) ────────────────────────── */
  const [wsState, setWsState] = useState("idle")       // idle | connecting | open | closed | error
  const [framesSent, setFramesSent] = useState(0)

  /** Latest perception update received from the backend. */
  const [perception, setPerception] = useState(null)
  //  shape: { emotion: { label, confidence }, gaze: string }

  /* ── lazy-init the offscreen canvas ────────────────────── */
  const getCanvas = useCallback(() => {
    if (!canvasRef.current) {
      const c = document.createElement("canvas")
      c.width = width
      c.height = height
      canvasRef.current = c
    }
    return canvasRef.current
  }, [width, height])

  /* ── capture a single frame → base64 JPEG ──────────────── */
  const captureFrame = useCallback(() => {
    const video = videoElRef.current
    if (!video || video.readyState < 2) return null   // HAVE_CURRENT_DATA

    const canvas = getCanvas()
    const ctx = canvas.getContext("2d")
    ctx.drawImage(video, 0, 0, width, height)

    // toDataURL returns "data:image/jpeg;base64,<payload>"
    const dataUrl = canvas.toDataURL("image/jpeg", quality)
    // Strip the prefix to reduce payload size
    return dataUrl.split(",")[1]
  }, [getCanvas, width, height, quality])

  /* ── send loop ─────────────────────────────────────────── */
  const startSendLoop = useCallback(() => {
    stopSendLoop()
    const intervalMs = Math.round(1000 / fps)

    intervalRef.current = setInterval(() => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WS_READY_STATE.OPEN) return

      const base64 = captureFrame()
      if (!base64) return

      const msg = JSON.stringify({ type: "frame", data: base64 })
      ws.send(msg)
      setFramesSent((n) => n + 1)
    }, intervalMs)
  }, [fps, captureFrame])

  const stopSendLoop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  /* ── WebSocket lifecycle ───────────────────────────────── */
  const buildWsUrl = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}/ws/video/${sessionId}`
  }, [sessionId])

  const connect = useCallback(() => {
    // Guard: don't open if already open / connecting
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
      if (isStreamingRef.current) startSendLoop()
    }

    ws.onclose = () => {
      setWsState("closed")
      stopSendLoop()

      // Auto-reconnect if we were actively streaming
      if (
        isStreamingRef.current &&
        reconnectCountRef.current < maxReconnects
      ) {
        reconnectCountRef.current += 1
        reconnectTimerRef.current = setTimeout(connect, reconnectDelay)
      }
    }

    ws.onerror = () => {
      setWsState("error")
      // onclose will fire next — reconnect logic lives there
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === "perception_update" && msg.payload) {
          setPerception(msg.payload)
          perceptionCbRef.current?.(msg.payload)
        }
      } catch {
        // Ignore malformed messages — non-blocking
      }
    }
  }, [buildWsUrl, startSendLoop, stopSendLoop, maxReconnects, reconnectDelay])

  const disconnect = useCallback(() => {
    isStreamingRef.current = false
    stopSendLoop()

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.onclose = null   // prevent reconnect on intentional close
      wsRef.current.close()
      wsRef.current = null
    }

    setWsState("idle")
    setFramesSent(0)
    reconnectCountRef.current = 0
  }, [stopSendLoop])

  /* ── public API ────────────────────────────────────────── */

  /** Provide the <video> DOM element to capture frames from. */
  const setVideoElement = useCallback((el) => {
    videoElRef.current = el
  }, [])

  /** Begin streaming frames over WebSocket. */
  const startStreaming = useCallback(() => {
    isStreamingRef.current = true
    connect()
  }, [connect])

  /** Stop streaming and close the WebSocket. */
  const stopStreaming = useCallback(() => {
    disconnect()
  }, [disconnect])

  /* ── cleanup on unmount ────────────────────────────────── */
  useEffect(() => {
    return () => {
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    /** Call with the <video> ref.current to bind. */
    setVideoElement,
    /** Open WS + begin frame capture loop. */
    startStreaming,
    /** Stop capture + close WS. */
    stopStreaming,
    /** Current WebSocket state: idle | connecting | open | closed | error */
    wsState,
    /** Total frames sent this session. */
    framesSent,
    /**
     * Latest perception update from the backend.
     * Shape: { emotion: { label: string, confidence: number }, gaze: string } | null
     */
    perception,
  }
}
