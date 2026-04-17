import { memo, useMemo } from "react"
import { Eye, EyeOff } from "lucide-react"
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
 * Consumes client-side perception state (emotion string + gaze string)
 * from useFaceMesh and renders shadcn Badge + Tooltip widgets.
 *
 * Wrapped in React.memo to prevent re-renders from parent
 * state changes that don't affect perception.
 *
 * @param {string}  emotion   — current emotion label ("neutral", "confused", etc.)
 * @param {string}  gaze      — gaze state: "on_screen" | "off_screen" | "closed_eyes"
 * @param {string}  className — optional extra classes on the root container
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

// ── Gaze config ─────────────────────────────────────────────────────────

const GAZE_CONFIG = {
  on_screen:   { label: "Focused",     away: false },
  off_screen:  { label: "Looking Away", away: true },
  closed_eyes: { label: "Eyes Closed",  away: true },
}

function resolveGaze(gaze) {
  return GAZE_CONFIG[gaze] || GAZE_CONFIG.on_screen
}

// ── Component ───────────────────────────────────────────────────────────

function PerceptionHUD({ emotion, gaze, className }) {
  // Derive emotion display values (memoised to avoid object churn)
  const emotionInfo = useMemo(
    () => resolveEmotion(emotion),
    [emotion],
  )

  const gazeInfo = useMemo(
    () => resolveGaze(gaze),
    [gaze],
  )

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
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          <span>
            Detected emotion: <strong>{emotionInfo.label}</strong>
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
              gazeInfo.away
                ? "bg-red-500/15 text-red-400 border-red-500/30 animate-pulse"
                : "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
            )}
            id="perception-gaze-badge"
          >
            {gazeInfo.away ? (
              <EyeOff
                className="size-3.5 text-red-400 transition-colors duration-300"
              />
            ) : (
              <Eye
                className="size-3.5 text-zinc-400 transition-colors duration-300"
              />
            )}
            {gazeInfo.label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          {gazeInfo.away ? (
            <span>
              Learner is <strong>{gazeInfo.label.toLowerCase()}</strong>
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
