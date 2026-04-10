import { useRef, useCallback, useEffect, useState } from "react"

/**
 * useAudioStream — Audio transport hook.
 *
 * Captures audio from a MediaStream via MediaRecorder,
 * chunks it every ~5 seconds, encodes each chunk as base64,
 * and sends it over a WebSocket to /ws/audio/{session_id}.
 *
 * Wire format:
 *   { "type": "audio_chunk", "data": "<base64>", "mimeType": "<mime>", "seq": <n> }
 *
 * Does NOT process or analyse audio on the frontend.
 *
 * @param {string}  sessionId               — unique session identifier
 * @param {Object}  options
 * @param {number}  [options.chunkInterval=5000]   — ms between audio chunks
 * @param {number}  [options.reconnectDelay=3000]  — ms before reconnect attempt
 * @param {number}  [options.maxReconnects=5]      — max consecutive reconnects
 */

const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
}

/**
 * Pick the best supported audio MIME type for MediaRecorder.
 * Prefer opus in WebM container — widely supported, efficient, low latency.
 */
function getSupportedMimeType() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ]
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  return "" // browser default
}

export default function useAudioStream(sessionId, options = {}) {
  const {
    chunkInterval = 5000,
    reconnectDelay = 3000,
    maxReconnects = 5,
  } = options

  /* ── refs ──────────────────────────────────────────────── */
  const wsRef = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)           // audio-only MediaStream clone
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const isStreamingRef = useRef(false)
  const chunkSeqRef = useRef(0)
  const mimeTypeRef = useRef("")
  const pendingChunksRef = useRef([])      // queue chunks until WS opens

  /* ── state (for UI consumption) ────────────────────────── */
  const [wsState, setWsState] = useState("idle")       // idle | connecting | open | closed | error
  const [chunksSent, setChunksSent] = useState(0)

  /* ── helpers ───────────────────────────────────────────── */

  /** Convert a Blob to a base64 string (without the data: prefix). */
  const blobToBase64 = useCallback((blob) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => {
        // result is "data:<mime>;base64,<payload>"
        const base64 = reader.result.split(",")[1]
        resolve(base64)
      }
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })
  }, [])

  /** Send a single audio chunk over WS. */
  const sendChunk = useCallback(
    async (blob) => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WS_READY_STATE.OPEN) {
        // Buffer chunk — will be flushed when WS opens
        pendingChunksRef.current.push(blob)
        return
      }

      try {
        const base64 = await blobToBase64(blob)
        if (!base64 || base64.length === 0) return // skip empty chunks

        const seq = chunkSeqRef.current++
        const msg = JSON.stringify({
          type: "audio_chunk",
          data: base64,
          mimeType: mimeTypeRef.current,
          seq,
        })
        ws.send(msg)
        setChunksSent((n) => n + 1)
      } catch {
        // encoding error — skip this chunk
      }
    },
    [blobToBase64]
  )

  /** Flush any chunks that were buffered while WS was connecting. */
  const flushPendingChunks = useCallback(async () => {
    const pending = pendingChunksRef.current.splice(0)
    for (const blob of pending) {
      await sendChunk(blob)
    }
  }, [sendChunk])

  /* ── MediaRecorder lifecycle ───────────────────────────── */

  const startRecorder = useCallback(
    (mediaStream) => {
      // Extract only audio tracks from the combined stream
      const audioTracks = mediaStream.getAudioTracks()
      if (audioTracks.length === 0) {
        console.warn("[useAudioStream] No audio tracks available on stream")
        return
      }

      // Create an audio-only stream so MediaRecorder doesn't touch video
      const audioOnlyStream = new MediaStream(audioTracks)
      streamRef.current = audioOnlyStream

      const mimeType = getSupportedMimeType()
      mimeTypeRef.current = mimeType

      const recorder = new MediaRecorder(audioOnlyStream, {
        mimeType: mimeType || undefined,
        audioBitsPerSecond: 64_000, // 64 kbps — good quality at low bandwidth
      })

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          sendChunk(e.data)
        }
      }

      recorder.onerror = (e) => {
        console.error("[useAudioStream] MediaRecorder error:", e.error)
      }

      recorder.start(chunkInterval) // emit data every ~chunkInterval ms
      recorderRef.current = recorder
    },
    [chunkInterval, sendChunk]
  )

  const stopRecorder = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop()
    }
    recorderRef.current = null
    streamRef.current = null
  }, [])

  /* ── WebSocket lifecycle ───────────────────────────────── */

  const buildWsUrl = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}/ws/audio/${sessionId}`
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
      flushPendingChunks()
    }

    ws.onclose = () => {
      setWsState("closed")

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
      // onclose fires next — reconnect logic lives there
    }

    ws.onmessage = () => {
      // no-op — server may send acks
    }
  }, [buildWsUrl, flushPendingChunks, maxReconnects, reconnectDelay])

  const disconnect = useCallback(() => {
    isStreamingRef.current = false
    stopRecorder()

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.onclose = null   // prevent reconnect on intentional close
      wsRef.current.close()
      wsRef.current = null
    }

    pendingChunksRef.current = []
    setWsState("idle")
    setChunksSent(0)
    chunkSeqRef.current = 0
    reconnectCountRef.current = 0
  }, [stopRecorder])

  /* ── public API ────────────────────────────────────────── */

  /**
   * Begin streaming audio chunks over WebSocket.
   * @param {MediaStream} mediaStream — the stream that contains audio tracks
   */
  const startStreaming = useCallback(
    (mediaStream) => {
      if (!mediaStream) {
        console.warn("[useAudioStream] startStreaming called without a MediaStream")
        return
      }
      isStreamingRef.current = true
      connect()
      startRecorder(mediaStream)
    },
    [connect, startRecorder]
  )

  /** Stop streaming and close WebSocket. */
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
    /** Open WS + begin audio capture. Pass the MediaStream from getUserMedia. */
    startStreaming,
    /** Stop capture + close WS. */
    stopStreaming,
    /** Current WebSocket state: idle | connecting | open | closed | error */
    wsState,
    /** Total audio chunks sent this session. */
    chunksSent,
  }
}
