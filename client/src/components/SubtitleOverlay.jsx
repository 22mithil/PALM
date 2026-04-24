import { useEffect, useState } from "react"
import "./SubtitleOverlay.css"

/**
 * SubtitleOverlay — fixed bottom-center pill showing live speech transcription.
 *
 * Displays interim (in-progress) text in dimmed italic and the latest final
 * sentence in bold white. Fades out shortly after listening stops.
 */
export default function SubtitleOverlay({ interimTranscript, finalTranscript, isListening }) {
  const [visible, setVisible] = useState(false)
  const [lastFinalSegment, setLastFinalSegment] = useState("")

  /* ── Extract the last sentence from the accumulated final transcript ── */
  useEffect(() => {
    if (finalTranscript) {
      const sentences = finalTranscript.trim().split(/(?<=[.!?])\s+(?=[a-zA-Z])/)
      const lastSentence = sentences[sentences.length - 1]
      setLastFinalSegment(lastSentence)
    } else {
      setLastFinalSegment("")
    }
  }, [finalTranscript])

  /* ── Show / hide logic ────────────────────────────────────────────────── */
  useEffect(() => {
    if ((isListening || interimTranscript) && (interimTranscript || lastFinalSegment)) {
      setVisible(true)
    } else if (!isListening && !interimTranscript) {
      const timer = setTimeout(() => setVisible(false), 2000)
      return () => clearTimeout(timer)
    }
  }, [isListening, interimTranscript, lastFinalSegment])

  if (!visible) return null

  return (
    <div
      className={`subtitle-overlay ${
        !isListening && !interimTranscript ? "subtitle-overlay--fade-out" : ""
      }`}
    >
      <div className="subtitle-overlay__pill">
        {lastFinalSegment && !interimTranscript && (
          <span className="subtitle-overlay__final">{lastFinalSegment}</span>
        )}
        {interimTranscript && (
          <span className="subtitle-overlay__interim">{interimTranscript}</span>
        )}
      </div>
    </div>
  )
}
