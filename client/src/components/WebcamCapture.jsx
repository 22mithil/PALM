import { useState, useRef, useEffect, useCallback } from "react"
import usePerceptionStream from "../hooks/usePerceptionStream"
import { useSpeechRecognition } from "../hooks/useSpeechRecognition"
import useTutorStream from "../hooks/useTutorStream"
import useFaceMesh from "../hooks/useFaceMesh"
import PerceptionHUD from "./PerceptionHUD"
import SubtitleOverlay from "./SubtitleOverlay"
import "./WebcamCapture.css"

/**
 * WebcamCapture — WebRTC media capture + live preview.
 *
 * Responsibilities:
 *   • Captures video + audio via navigator.mediaDevices.getUserMedia
 *   • Renders a mirrored webcam preview in a <video> element
 *   • Runs browser-native speech recognition via Web Speech API
 *   • Sends transcript text to the tutor backend via WebSocket
 *   • Provides start / stop controls
 *
 * Constraints:
 *   • Does NOT process frames — capture & preview only
 *   • Stream is cleaned up on unmount to avoid dangling tracks
 */

const VIDEO_CONSTRAINTS = {
  width: { ideal: 1280 },
  height: { ideal: 720 },
  facingMode: "user",
  frameRate: { ideal: 30 },
}

const AUDIO_CONSTRAINTS = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
}

// Placeholder student ID — should be passed as prop in production
const PLACEHOLDER_STUDENT_ID = "00000000-0000-0000-0000-000000000001"

export default function WebcamCapture({ sessionId = crypto.randomUUID(), studentId = PLACEHOLDER_STUDENT_ID }) {
  /* ── state ────────────────────────────────────────────── */
  const [stream, setStream] = useState(null)
  const [isCapturing, setIsCapturing] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState(null)
  const [sttErrorDismissed, setSttErrorDismissed] = useState(false)
  const [devices, setDevices] = useState([])
  const [selectedDeviceId, setSelectedDeviceId] = useState("")

  const videoRef = useRef(null)
  const prevFinalLengthRef = useRef(0) // tracks previous finalTranscript length for diff

  /* ── face mesh overlay + local emotion + gaze ──────────── */
  const { canvasRef, emotion, gaze, fps: meshFps, isReady: meshReady } = useFaceMesh(videoRef, isCapturing)

  /* ── perception stream (lightweight JSON to backend) ────── */
  const {
    startStream: startPerceptionStream,
    stopStream: stopPerceptionStream,
    sendPerception,
    wsState: perceptionWsState,
  } = usePerceptionStream(sessionId)

  /* ── speech recognition (Web Speech API) ────────────────── */
  const {
    start: startSTT,
    stop: stopSTT,
    isListening,
    interimTranscript,
    finalTranscript,
    clearTranscript,
    isSupported: sttSupported,
    error: sttError,
  } = useSpeechRecognition()

  /* ── tutor stream (WebSocket to /ws/tutor/) ─────────────── */
  const {
    startStream: startTutorStream,
    stopStream: stopTutorStream,
    sendTrigger,
    wsState: tutorWsState,
    isStreaming: tutorIsStreaming,
    streamingText: tutorStreamingText,
    lastResponse: tutorLastResponse,
    tutorError,
    clearTutorError,
  } = useTutorStream(sessionId)

  /* ── send new transcript segments to tutor on finalTranscript change ── */
  useEffect(() => {
    if (!finalTranscript) return

    const prevLength = prevFinalLengthRef.current
    const newSegment = finalTranscript.slice(prevLength)
    prevFinalLengthRef.current = finalTranscript.length

    if (newSegment.trim()) {
      sendTrigger(studentId, newSegment.trim())
    }
  }, [finalTranscript, sendTrigger, studentId])

  /* ── reset transcript length ref when transcript is cleared ── */
  useEffect(() => {
    if (!finalTranscript) {
      prevFinalLengthRef.current = 0
    }
  }, [finalTranscript])

  /* ── dismiss STT error when a new one arrives ─────────── */
  useEffect(() => {
    if (sttError) {
      setSttErrorDismissed(false)
    }
  }, [sttError])

  /* ── enumerate cameras ────────────────────────────────── */
  const enumerateDevices = useCallback(async () => {
    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices()
      const videoInputs = allDevices.filter((d) => d.kind === "videoinput")
      setDevices(videoInputs)
      if (videoInputs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(videoInputs[0].deviceId)
      }
    } catch {
      /* silently ignore — enumeration isn't critical */
    }
  }, [selectedDeviceId])

  useEffect(() => {
    enumerateDevices()
  }, [enumerateDevices])

  /* ── start capture ────────────────────────────────────── */
  const startCapture = useCallback(async () => {
    setError(null)

    const videoConstraints = {
      ...VIDEO_CONSTRAINTS,
      ...(selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : {}),
    }

    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: videoConstraints,
        audio: AUDIO_CONSTRAINTS,
      })

      setStream(mediaStream)
      setIsCapturing(true)

      // Start perception streaming to backend
      startPerceptionStream()

      // Start tutor WS connection
      startTutorStream()

      setIsStreaming(true)

      // Re-enumerate so we get labels now that permission is granted
      enumerateDevices()
    } catch (err) {
      const msg =
        err.name === "NotAllowedError"
          ? "Camera access was denied. Please allow camera & microphone permissions."
          : err.name === "NotFoundError"
          ? "No camera or microphone found on this device."
          : err.name === "NotReadableError"
          ? "Camera is already in use by another application."
          : `Could not access media devices: ${err.message}`
      setError(msg)
    }
  }, [selectedDeviceId, enumerateDevices, startPerceptionStream, startTutorStream])

  /* ── stop capture ─────────────────────────────────────── */
  const stopCapture = useCallback(() => {
    // Stop STT if listening
    stopSTT()
    clearTranscript()
    prevFinalLengthRef.current = 0

    // Stop streaming
    stopPerceptionStream()
    stopTutorStream()
    setIsStreaming(false)

    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setStream(null)
    setIsCapturing(false)
  }, [stream, stopPerceptionStream, stopTutorStream, stopSTT, clearTranscript])

  /* ── push-to-talk: hold spacebar to listen ──────────────── */
  useEffect(() => {
    if (!isCapturing || !sttSupported) return

    const isInputFocused = () => {
      const tag = document.activeElement?.tagName
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
    }

    const handleKeyDown = (e) => {
      if (e.code === "Space" && !e.repeat && !isInputFocused()) {
        e.preventDefault()
        startSTT()
      }
    }

    const handleKeyUp = (e) => {
      if (e.code === "Space" && !isInputFocused()) {
        e.preventDefault()
        stopSTT()
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    window.addEventListener("keyup", handleKeyUp)

    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      window.removeEventListener("keyup", handleKeyUp)
    }
  }, [isCapturing, sttSupported, startSTT, stopSTT])

  /* ── switch camera ────────────────────────────────────── */
  const switchCamera = useCallback(
    async (deviceId) => {
      setSelectedDeviceId(deviceId)
      if (isCapturing) {
        // Restart stream with the new device
        if (stream) {
          stream.getTracks().forEach((track) => track.stop())
        }
        try {
          const mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { ...VIDEO_CONSTRAINTS, deviceId: { exact: deviceId } },
            audio: AUDIO_CONSTRAINTS,
          })
          setStream(mediaStream)
          if (videoRef.current) {
            videoRef.current.srcObject = mediaStream
          }
        } catch (err) {
          setError(`Failed to switch camera: ${err.message}`)
        }
      }
    },
    [isCapturing, stream]
  )

  /* ── sync stream → video element after render ──────────── */
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream
    }
  }, [stream])

  /* ── send perception updates to backend on change ──────── */
  useEffect(() => {
    if (isCapturing && isStreaming) {
      sendPerception(emotion, gaze)
    }
  }, [emotion, gaze, isCapturing, isStreaming, sendPerception])

  /* ── cleanup on unmount ───────────────────────────────── */
  useEffect(() => {
    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop())
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ── derive track info ────────────────────────────────── */
  const videoTrack = stream?.getVideoTracks()[0]
  const audioTrack = stream?.getAudioTracks()[0]
  const videoSettings = videoTrack?.getSettings()

  /* ── render ───────────────────────────────────────────── */
  return (
    <div className="webcam-capture">
      {/* ─── Unsupported browser warning ────────────────── */}
      {!sttSupported && (
        <div className="webcam-capture__error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>Speech Recognition is not supported in this browser. Please use Chrome or Edge.</span>
        </div>
      )}

      {/* ─── Video viewport ─────────────────────────────── */}
      <div className="webcam-capture__viewport">
        {isCapturing ? (
          <>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted          /* mute playback to avoid echo — audio track still captured */
              className="webcam-capture__video"
            />

            {/* Face mesh canvas overlay */}
            <canvas
              ref={canvasRef}
              className="webcam-capture__mesh-canvas"
            />

            {/* Live badge */}
            <span className="webcam-capture__live-badge">
              <span className="webcam-capture__live-dot" />
              LIVE
            </span>

            {/* Emotion + Gaze badge */}
            {meshReady && (
              <span className={`webcam-capture__emotion-badge webcam-capture__emotion-badge--${emotion}`}>
                {emotion.toUpperCase()}
                {gaze !== "on_screen" && (
                  <span className="webcam-capture__gaze-indicator"> · {gaze === "closed_eyes" ? "EYES CLOSED" : "LOOKING AWAY"}</span>
                )}
                <span className="webcam-capture__mesh-fps">{meshFps} FPS</span>
              </span>
            )}

            {/* Perception HUD overlay */}
            {meshReady && isCapturing && (
              <div className="webcam-capture__perception-hud">
                <PerceptionHUD emotion={emotion} gaze={gaze} />
              </div>
            )}

            {/* Resolution badge */}
            {videoSettings && (
              <span className="webcam-capture__res-badge">
                {videoSettings.width}×{videoSettings.height}
              </span>
            )}

            {/* Subtitle overlay (speech recognition) */}
            <SubtitleOverlay
              interimTranscript={interimTranscript}
              finalTranscript={finalTranscript}
              isListening={isListening}
            />
          </>
        ) : (
          <div className="webcam-capture__placeholder">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="webcam-capture__placeholder-icon"
            >
              <path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.934a.5.5 0 0 0-.777-.416L16 11" />
              <rect x="2" y="6" width="14" height="12" rx="2" />
            </svg>
            <p className="webcam-capture__placeholder-text">
              Camera preview will appear here
            </p>
          </div>
        )}
      </div>

      {/* ─── Error message ──────────────────────────────── */}
      {error && (
        <div className="webcam-capture__error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* ─── STT error (dismissible) ────────────────────── */}
      {sttError && !sttErrorDismissed && (
        <div className="webcam-capture__error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{sttError}</span>
          <button
            onClick={() => setSttErrorDismissed(true)}
            className="webcam-capture__error-dismiss"
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      {/* ─── Controls ───────────────────────────────────── */}
      <div className="webcam-capture__controls">
        {/* Camera selector */}
        {devices.length > 1 && (
          <select
            value={selectedDeviceId}
            onChange={(e) => switchCamera(e.target.value)}
            className="webcam-capture__select"
            id="webcam-camera-select"
          >
            {devices.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        )}

        <div className="webcam-capture__btn-group">
          {/* STT indicator — hold spacebar to talk */}
          {isCapturing && sttSupported && (
            <button
              className={`webcam-capture__btn webcam-capture__btn--icon ${
                isListening ? "webcam-capture__btn--stt-active" : ""
              }`}
              title="Hold Spacebar to speak"
              id="webcam-toggle-stt"
              tabIndex={-1}
            >
              {isListening ? (
                /* Mic on (active) icon */
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="22" />
                </svg>
              ) : (
                /* Mic off icon */
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="2" y1="2" x2="22" y2="22" />
                  <path d="M18.89 13.23A7.12 7.12 0 0 0 19 12" />
                  <path d="M5 10v2a7 7 0 0 0 12 5" />
                  <path d="M15 9.34V5a3 3 0 0 0-5.68-1.33" />
                  <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
                  <line x1="12" y1="19" x2="12" y2="22" />
                </svg>
              )}
            </button>
          )}

          {/* Start / Stop */}
          <button
            onClick={isCapturing ? stopCapture : startCapture}
            className={`webcam-capture__btn ${
              isCapturing
                ? "webcam-capture__btn--stop"
                : "webcam-capture__btn--start"
            }`}
            id="webcam-toggle-capture"
          >
            {isCapturing ? (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
                Stop Camera
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.934a.5.5 0 0 0-.777-.416L16 11" />
                  <rect x="2" y="6" width="14" height="12" rx="2" />
                </svg>
                Start Camera
              </>
            )}
          </button>
        </div>
      </div>

      {/* ─── Stream metadata (debug) ────────────────────── */}
      {isCapturing && (
        <div className="webcam-capture__meta">
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Video</span>
            <span className="webcam-capture__meta-value">
              {videoTrack?.label || "—"}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Audio</span>
            <span className="webcam-capture__meta-value">
              {audioTrack?.label || "—"}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Tracks</span>
            <span className="webcam-capture__meta-value">
              {stream?.getTracks().length || 0} active
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Perception WS</span>
            <span className={`webcam-capture__meta-value webcam-capture__ws-${perceptionWsState}`}>
              {perceptionWsState}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Tutor WS</span>
            <span className={`webcam-capture__meta-value webcam-capture__ws-${tutorWsState}`}>
              {tutorWsState}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">STT</span>
            <span className={`webcam-capture__meta-value ${isListening ? "webcam-capture__ws-open" : "webcam-capture__ws-idle"}`}>
              {isListening ? "listening" : "idle"}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
