import { useState, useRef, useEffect, useCallback } from "react"
import useVideoStream from "../hooks/useVideoStream"
import useAudioStream from "../hooks/useAudioStream"
import PerceptionHUD from "./PerceptionHUD"
import "./WebcamCapture.css"

/**
 * WebcamCapture — WebRTC media capture + live preview.
 *
 * Responsibilities:
 *   • Captures video + audio via navigator.mediaDevices.getUserMedia
 *   • Renders a mirrored webcam preview in a <video> element
 *   • Stores the MediaStream in local React state
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

export default function WebcamCapture({ sessionId = crypto.randomUUID() }) {
  /* ── state ────────────────────────────────────────────── */
  const [stream, setStream] = useState(null)
  const [isCapturing, setIsCapturing] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState(null)
  const [isMuted, setIsMuted] = useState(false)
  const [devices, setDevices] = useState([])
  const [selectedDeviceId, setSelectedDeviceId] = useState("")

  const videoRef = useRef(null)

  /* ── video stream transport ────────────────────────────── */
  const {
    setVideoElement,
    startStreaming: startVideoStreaming,
    stopStreaming: stopVideoStreaming,
    wsState: videoWsState,
    framesSent,
    perception,
  } = useVideoStream(sessionId)

  /* ── audio stream transport ────────────────────────────── */
  const {
    startStreaming: startAudioStreaming,
    stopStreaming: stopAudioStreaming,
    wsState: audioWsState,
    chunksSent,
  } = useAudioStream(sessionId)

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

      // Start streaming frames + audio to backend
      startVideoStreaming()
      startAudioStreaming(mediaStream)
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
  }, [selectedDeviceId, enumerateDevices])

  /* ── stop capture ─────────────────────────────────────── */
  const stopCapture = useCallback(() => {
    // Stop streaming first
    stopVideoStreaming()
    stopAudioStreaming()
    setIsStreaming(false)

    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setStream(null)
    setIsCapturing(false)
  }, [stream, stopVideoStreaming, stopAudioStreaming])

  /* ── toggle mic mute ──────────────────────────────────── */
  const toggleMute = useCallback(() => {
    if (!stream) return
    const audioTracks = stream.getAudioTracks()
    audioTracks.forEach((t) => (t.enabled = !t.enabled))
    setIsMuted((prev) => !prev)
  }, [stream])

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
      setVideoElement(videoRef.current)
    }
  }, [stream, setVideoElement])

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

            {/* Live badge */}
            <span className="webcam-capture__live-badge">
              <span className="webcam-capture__live-dot" />
              LIVE
            </span>

            {/* Streaming badge */}
            {isStreaming && (
              <span className={`webcam-capture__stream-badge webcam-capture__stream-badge--${videoWsState}`}>
                {videoWsState === "open" ? "⬆ STREAMING" : videoWsState === "connecting" ? "CONNECTING…" : "RECONNECTING…"}
              </span>
            )}

            {/* Perception HUD overlay */}
            {perception && isStreaming && (
              <div className="webcam-capture__perception-hud">
                <PerceptionHUD perception={perception} />
              </div>
            )}

            {/* Resolution badge */}
            {videoSettings && (
              <span className="webcam-capture__res-badge">
                {videoSettings.width}×{videoSettings.height}
                {isStreaming && videoWsState === "open" && (
                  <span className="webcam-capture__frame-counter"> · {framesSent} frames</span>
                )}
              </span>
            )}
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
          {/* Mute / unmute */}
          {isCapturing && (
            <button
              onClick={toggleMute}
              className={`webcam-capture__btn webcam-capture__btn--icon ${
                isMuted ? "webcam-capture__btn--muted" : ""
              }`}
              title={isMuted ? "Unmute microphone" : "Mute microphone"}
              id="webcam-toggle-mute"
            >
              {isMuted ? (
                /* Mic off icon */
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="2" y1="2" x2="22" y2="22" />
                  <path d="M18.89 13.23A7.12 7.12 0 0 0 19 12" />
                  <path d="M5 10v2a7 7 0 0 0 12 5" />
                  <path d="M15 9.34V5a3 3 0 0 0-5.68-1.33" />
                  <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
                  <line x1="12" y1="19" x2="12" y2="22" />
                </svg>
              ) : (
                /* Mic on icon */
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
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
              {audioTrack?.label || "—"}{" "}
              {isMuted && (
                <span className="webcam-capture__meta-muted">(muted)</span>
              )}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Tracks</span>
            <span className="webcam-capture__meta-value">
              {stream?.getTracks().length || 0} active
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Video WS</span>
            <span className={`webcam-capture__meta-value webcam-capture__ws-${videoWsState}`}>
              {videoWsState}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Audio WS</span>
            <span className={`webcam-capture__meta-value webcam-capture__ws-${audioWsState}`}>
              {audioWsState}
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Frames</span>
            <span className="webcam-capture__meta-value">
              {framesSent} sent
            </span>
          </div>
          <div className="webcam-capture__meta-item">
            <span className="webcam-capture__meta-label">Audio Chunks</span>
            <span className="webcam-capture__meta-value">
              {chunksSent} sent
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
