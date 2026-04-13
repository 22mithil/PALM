import { memo, useMemo } from "react"
import { Eye } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

/**
 * PerceptionHUD — Real-time emotion + gaze indicators.
 *
 * Consumes the `perception` payload from the video WebSocket
 * and renders shadcn Badge + Tooltip widgets.
 *
 * Wrapped in React.memo to prevent re-renders from parent
 * state changes that don't affect perception.
 *
 * @param {Object}  perception — latest perception_update payload (or null)
 * @param {string}  className  — optional extra classes on the root container
 */

// ── Emotion config ──────────────────────────────────────────────────────

const EMOTION_MAP = {
  confused:   { emoji: "😕", label: "Confused",   color: "bg-amber-500/15 text-amber-400 border-amber-500/25" },
  bored:      { emoji: "😴", label: "Bored",      color: "bg-blue-500/15 text-blue-400 border-blue-500/25" },
  frustrated: { emoji: "😣", label: "Frustrated", color: "bg-red-500/15 text-red-400 border-red-500/25" },
  neutral:    { emoji: "🙂", label: "Neutral",    color: "bg-zinc-500/15 text-zinc-400 border-zinc-500/25" },
  confident:  { emoji: "😎", label: "Confident",  color: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" },
  happy:      { emoji: "😊", label: "Happy",      color: "bg-green-500/15 text-green-400 border-green-500/25" },
  sad:        { emoji: "😢", label: "Sad",        color: "bg-indigo-500/15 text-indigo-400 border-indigo-500/25" },
  surprise:   { emoji: "😲", label: "Surprise",   color: "bg-purple-500/15 text-purple-400 border-purple-500/25" },
  angry:      { emoji: "😠", label: "Angry",      color: "bg-rose-500/15 text-rose-400 border-rose-500/25" },
  fear:       { emoji: "😨", label: "Fear",        color: "bg-orange-500/15 text-orange-400 border-orange-500/25" },
}

const FALLBACK_EMOTION = { emoji: "🙂", label: "Unknown", color: "bg-zinc-500/15 text-zinc-400 border-zinc-500/25" }

function resolveEmotion(label) {
  if (!label) return FALLBACK_EMOTION
  const key = label.toLowerCase().trim()
  return EMOTION_MAP[key] || FALLBACK_EMOTION
}

// ── Component ───────────────────────────────────────────────────────────

function PerceptionHUD({ perception, className }) {
  // Derive emotion display values (memoised to avoid object churn)
  const emotionInfo = useMemo(
    () => resolveEmotion(perception?.emotion?.label),
    [perception?.emotion?.label],
  )

  const confidence = perception?.emotion?.confidence
  const confidencePct = confidence != null ? Math.round(confidence * 100) : null

  const gazeAway = perception?.gaze_tracking?.gaze_away_flag ?? false
  const gazeDuration = perception?.gaze_tracking?.gaze_duration ?? 0

  if (!perception) return null

  return (
    <div
      className={cn(
        "flex items-center gap-2 pointer-events-auto",
        className,
      )}
      id="perception-hud"
    >
      {/* ── Emotion badge ─────────────────────────────────── */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={cn(
              "gap-1.5 px-2.5 py-1 h-7 text-[0.8rem] font-semibold border cursor-default",
              "transition-all duration-300 ease-out",
              emotionInfo.color,
            )}
            id="perception-emotion-badge"
          >
            <span className="text-sm leading-none" aria-hidden="true">
              {emotionInfo.emoji}
            </span>
            {emotionInfo.label}
            {confidencePct != null && (
              <span className="ml-0.5 text-[0.65rem] opacity-60 font-mono tabular-nums">
                {confidencePct}%
              </span>
            )}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          <span>
            Detected emotion: <strong>{emotionInfo.label}</strong>
            {confidencePct != null && ` (${confidencePct}% confidence)`}
          </span>
        </TooltipContent>
      </Tooltip>

      {/* ── Gaze indicator ────────────────────────────────── */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={cn(
              "gap-1.5 px-2.5 py-1 h-7 text-[0.8rem] font-semibold border cursor-default",
              "transition-all duration-300 ease-out",
              gazeAway
                ? "bg-red-500/15 text-red-400 border-red-500/30 animate-pulse"
                : "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
            )}
            id="perception-gaze-badge"
          >
            <Eye
              className={cn(
                "size-3.5 transition-colors duration-300",
                gazeAway ? "text-red-400" : "text-zinc-400",
              )}
            />
            {gazeAway ? "Away" : "Focused"}
            {gazeAway && gazeDuration > 0 && (
              <span className="ml-0.5 text-[0.65rem] opacity-70 font-mono tabular-nums">
                {gazeDuration.toFixed(0)}s
              </span>
            )}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          {gazeAway ? (
            <span>
              Learner has been looking away for{" "}
              <strong>{gazeDuration.toFixed(1)}s</strong>
            </span>
          ) : (
            <span>Learner is focused on screen</span>
          )}
        </TooltipContent>
      </Tooltip>
    </div>
  )
}

export default memo(PerceptionHUD)
