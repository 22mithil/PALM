import { useState, useRef, useEffect, useCallback } from "react"
import {
  FaceLandmarker,
  FilesetResolver,
  DrawingUtils,
} from "@mediapipe/tasks-vision"

/**
 * useFaceMesh — Client-side face mesh overlay + emotion classification
 * using MediaPipe FaceLandmarker (Tasks Vision JS SDK).
 *
 * Renders face mesh landmarks onto a <canvas> overlaid on the video.
 * Classifies emotions from blendshape scores using threshold logic
 * matching the backend EmotionModel.
 *
 * Usage:
 *   const { canvasRef, emotion, fps, isReady } = useFaceMesh(videoRef, isActive)
 */

const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

const WASM_URL =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm"

// ── Thresholds (matched with backend emotion_model.py + App.tsx) ──
function classifyEmotion(blendshapes) {
  const s = {}
  blendshapes.forEach((b) => {
    s[b.categoryName] = b.score
  })

  if (
    (s.mouthSmileLeft > 0.25 || s.mouthSmileRight > 0.25) &&
    s.eyeSquintLeft < 0.5
  )
    return "confident"
  if (
    (s.browDownLeft > 0.3 && s.eyeSquintLeft > 0.3) ||
    (s.browDownRight > 0.3 && s.eyeSquintRight > 0.3)
  )
    return "confused"
  if (
    s.eyeLookDownLeft > 0.5 &&
    s.eyeLookDownRight > 0.5 &&
    s.mouthSmileLeft < 0.2
  )
    return "bored"
  if (
    (s.browInnerUp > 0.2 || s.browDownLeft > 0.2 || s.browDownRight > 0.2) &&
    (s.mouthFrownLeft > 0.15 || s.mouthFrownRight > 0.15)
  )
    return "frustrated"

  return "neutral"
}

export default function useFaceMesh(videoRef, isActive) {
  const canvasRef = useRef(null)
  const [emotion, setEmotion] = useState("neutral")
  const [fps, setFps] = useState(0)
  const [isReady, setIsReady] = useState(false)

  // Refs for animation loop
  const landmarkerRef = useRef(null)
  const rafRef = useRef(0)
  const fpsCounterRef = useRef(0)
  const fpsTimeRef = useRef(performance.now())

  // ── Init MediaPipe FaceLandmarker ────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        const filesetResolver = await FilesetResolver.forVisionTasks(WASM_URL)

        const landmarker = await FaceLandmarker.createFromOptions(
          filesetResolver,
          {
            baseOptions: {
              modelAssetPath: MODEL_URL,
              delegate: "CPU",
            },
            outputFaceBlendshapes: true,
            runningMode: "VIDEO",
            numFaces: 1,
          }
        )

        if (!cancelled) {
          landmarkerRef.current = landmarker
          setIsReady(true)
        }
      } catch (err) {
        console.error("FaceLandmarker init failed:", err)
      }
    }

    init()

    return () => {
      cancelled = true
      if (landmarkerRef.current) {
        landmarkerRef.current.close()
        landmarkerRef.current = null
      }
      setIsReady(false)
    }
  }, [])

  // ── Animation loop: detect + draw ───────────────────────────
  const detect = useCallback(() => {
    const video = videoRef?.current
    const canvas = canvasRef.current
    const landmarker = landmarkerRef.current

    if (!video || !canvas || !landmarker || !isActive) {
      rafRef.current = requestAnimationFrame(detect)
      return
    }

    if (video.videoWidth === 0 || video.videoHeight === 0) {
      rafRef.current = requestAnimationFrame(detect)
      return
    }

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Match canvas size to video
    if (
      canvas.width !== video.videoWidth ||
      canvas.height !== video.videoHeight
    ) {
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
    }

    const now = performance.now()

    try {
      const results = landmarker.detectForVideo(video, now)

      // Clear previous frame
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      if (
        results.faceBlendshapes &&
        results.faceBlendshapes.length > 0
      ) {
        const detected = classifyEmotion(
          results.faceBlendshapes[0].categories
        )
        setEmotion(detected)

        // Draw face mesh
        const drawingUtils = new DrawingUtils(ctx)
        for (const landmarks of results.faceLandmarks) {
          // Tesselation — thin silver mesh
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_TESSELATION,
            { color: "#C0C0C030", lineWidth: 1 }
          )
          // Right eye — red
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE,
            { color: "#FF3030" }
          )
          // Right eyebrow — red
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_RIGHT_EYEBROW,
            { color: "#FF3030" }
          )
          // Left eye — green
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_LEFT_EYE,
            { color: "#30FF30" }
          )
          // Left eyebrow — green
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_LEFT_EYEBROW,
            { color: "#30FF30" }
          )
          // Face oval — white
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_FACE_OVAL,
            { color: "#E0E0E0" }
          )
          // Lips — white
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_LIPS,
            { color: "#E0E0E0" }
          )
          // Right iris — red
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_RIGHT_IRIS,
            { color: "#FF3030" }
          )
          // Left iris — green
          drawingUtils.drawConnectors(
            landmarks,
            FaceLandmarker.FACE_LANDMARKS_LEFT_IRIS,
            { color: "#30FF30" }
          )
        }
      } else {
        setEmotion("neutral")
      }
    } catch {
      // Silently skip frames that fail
    }

    // FPS calculation
    fpsCounterRef.current++
    if (now - fpsTimeRef.current >= 1000) {
      setFps(fpsCounterRef.current)
      fpsCounterRef.current = 0
      fpsTimeRef.current = now
    }

    rafRef.current = requestAnimationFrame(detect)
  }, [videoRef, isActive])

  // Start/stop the detection loop
  useEffect(() => {
    if (isReady && isActive) {
      rafRef.current = requestAnimationFrame(detect)
    }
    return () => cancelAnimationFrame(rafRef.current)
  }, [isReady, isActive, detect])

  return { canvasRef, emotion, fps, isReady }
}
