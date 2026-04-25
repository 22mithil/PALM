import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, Send, X, Video, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { usePalmStore } from "@/store/usePalmStore";
import useFaceMesh from "@/hooks/useFaceMesh";
import usePerceptionStream from "@/hooks/usePerceptionStream";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import PerceptionHUD from "@/components/PerceptionHUD";
import SubtitleOverlay from "@/components/SubtitleOverlay";
import "@/components/WebcamCapture.css";

const sessionMeta = {
  topic: "Fractions",
  grade: "Grade 3",
  sessionNumber: 4,
  initialMastery: 55,
};

const challenge = {
  id: "q1",
  icon: "🍫",
  question:
    "You have a chocolate bar with 8 equal pieces. You eat 3 pieces. What fraction did you eat?",
  options: ["3/5", "3/8", "8/3", "5/8"],
  correct: "3/8",
};

const VIDEO_CONSTRAINTS = {
  width: { ideal: 640 },
  height: { ideal: 480 },
  facingMode: "user",
  frameRate: { ideal: 30 },
};

const AUDIO_CONSTRAINTS = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

const PLACEHOLDER_STUDENT_ID = "00000000-0000-0000-0000-000000000001";

const formatTime = (s) => {
  const m = Math.floor(s / 60).toString().padStart(2, "0");
  const sec = (s % 60).toString().padStart(2, "0");
  return `${m}:${sec}`;
};

const TutorAvatar = () => (
  <div className="h-8 w-8 shrink-0 rounded-full bg-muted grid place-items-center text-sm">
    🤖
  </div>
);

const StudentAvatar = ({ initial }) => (
  <div className="h-8 w-8 shrink-0 rounded-full bg-teal-100 text-teal-800 grid place-items-center text-xs font-semibold">
    {initial}
  </div>
);

const renderInline = (text) => {
  const parts = text.split(/(`[^`]+`|\b\d+\/\d+\b)/g);
  return parts.map((p, i) => {
    if (/^`[^`]+`$/.test(p)) {
      return (
        <span key={i} className="font-mono bg-muted px-1 rounded text-xs">
          {p.slice(1, -1)}
        </span>
      );
    }
    if (/^\d+\/\d+$/.test(p)) {
      return (
        <span key={i} className="font-mono bg-muted px-1 rounded text-xs">
          {p}
        </span>
      );
    }
    return <span key={i}>{p}</span>;
  });
};

const Session = () => {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { learnerName } = usePalmStore();
  const initial = (learnerName?.[0] || "S").toUpperCase();
  const studentId = PLACEHOLDER_STUDENT_ID;

  // timer
  const [elapsed, setElapsed] = useState(504);
  useEffect(() => {
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  /* ══════════════════════════════════════════════════════════
     Webcam capture state (replaces static camera placeholder)
     ══════════════════════════════════════════════════════════ */
  const [stream, setStream] = useState(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [camError, setCamError] = useState(null);
  const videoRef = useRef(null);
  const prevFinalLengthRef = useRef(0);

  /* ── face mesh overlay + local emotion + gaze ──────────── */
  const { canvasRef, emotion, gaze, fps: meshFps, isReady: meshReady } = useFaceMesh(videoRef, isCapturing);

  /* ── perception stream (lightweight JSON to backend) ────── */
  const {
    startStream: startPerceptionStream,
    stopStream: stopPerceptionStream,
    sendPerception,
  } = usePerceptionStream(sessionId);

  /* ── speech recognition (Web Speech API) ────────────────── */
  const {
    start: startSTT,
    stop: stopSTT,
    isListening: sttListening,
    interimTranscript,
    finalTranscript,
    clearTranscript,
    isSupported: sttSupported,
  } = useSpeechRecognition();

  /* ── grade & topic for RAG queries ───────────────────────── */
  const [grade, setGrade] = useState(3);
  const [topic, setTopic] = useState("Fractions");
  const [ragLoading, setRagLoading] = useState(false);

  /* ── start capture ────────────────────────────────────── */
  const startCapture = useCallback(async () => {
    setCamError(null);
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: VIDEO_CONSTRAINTS,
        audio: AUDIO_CONSTRAINTS,
      });
      setStream(mediaStream);
      const newSessionId = sessionId || crypto.randomUUID();
      startPerceptionStream(newSessionId);
      setIsStreaming(true);
    } catch (err) {
      const msg =
        err.name === "NotAllowedError"
          ? "Camera access was denied."
          : err.name === "NotFoundError"
          ? "No camera found."
          : err.name === "NotReadableError"
          ? "Camera is in use by another app."
          : `Could not access camera: ${err.message}`;
      setCamError(msg);
    }
  }, [sessionId, startPerceptionStream]);

  /* ── stop capture ─────────────────────────────────────── */
  const stopCapture = useCallback(() => {
    stopSTT();
    clearTranscript();
    prevFinalLengthRef.current = 0;
    stopPerceptionStream();
    setIsStreaming(false);
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStream(null);
    setIsCapturing(false);
  }, [stream, stopPerceptionStream, stopSTT, clearTranscript]);

  /* ── push-to-talk: hold spacebar → fill input, release → send ── */
  const sttActiveRef = useRef(false);
  useEffect(() => {
    if (!sttSupported) return;
    const isInputFocused = () => {
      const tag = document.activeElement?.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    };
    const handleKeyDown = (e) => {
      if (e.code === "Space" && !e.repeat && !isInputFocused()) {
        e.preventDefault();
        sttActiveRef.current = true;
        startSTT();
      }
    };
    const handleKeyUp = (e) => {
      if (e.code === "Space" && !isInputFocused() && sttActiveRef.current) {
        e.preventDefault();
        sttActiveRef.current = false;
        stopSTT();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [sttSupported, startSTT, stopSTT]);

  /* ── sync stream → video element ──────────────────────── */
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  /* ── attach onloadedmetadata to mark capturing ────────── */
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return;
    const handleLoaded = () => setIsCapturing(true);
    video.addEventListener("loadedmetadata", handleLoaded);
    return () => video.removeEventListener("loadedmetadata", handleLoaded);
  }, [stream]);

  /* ── send perception updates to backend ────────────────── */
  useEffect(() => {
    if (isCapturing && isStreaming) {
      sendPerception(emotion, gaze);
    }
  }, [emotion, gaze, isCapturing, isStreaming, sendPerception]);

  /* ── cleanup on unmount ───────────────────────────────── */
  useEffect(() => {
    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ══════════════════════════════════════════════════════════
     Chat / challenge state — integrated with backend RAG
     ══════════════════════════════════════════════════════════ */
  const [messages, setMessages] = useState([
    {
      id: "m1",
      role: "tutor",
      text: "Hi! Let's keep going with fractions. Remember, a fraction shows part of a whole — like 1/2 means one out of two equal parts.",
    },
  ]);
  const [typing, setTyping] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, typing]);

  /* ── sync STT interim/final transcript into input box ───── */
  useEffect(() => {
    if (sttListening && interimTranscript) {
      setInput(interimTranscript);
    }
  }, [sttListening, interimTranscript]);

  useEffect(() => {
    if (finalTranscript) {
      const prevLen = prevFinalLengthRef.current;
      const newSegment = finalTranscript.slice(prevLen);
      prevFinalLengthRef.current = finalTranscript.length;
      if (newSegment.trim()) {
        setInput(newSegment.trim());
      }
    }
  }, [finalTranscript]);

  /* ── auto-send when spacebar released (STT stops) ────────── */
  const wasSttActiveRef = useRef(false);
  useEffect(() => {
    if (sttListening) {
      wasSttActiveRef.current = true;
    } else if (wasSttActiveRef.current) {
      wasSttActiveRef.current = false;
      // Small delay to let final transcript arrive
      const t = setTimeout(() => {
        setInput((currentInput) => {
          if (currentInput.trim()) {
            sendStudentMessage(currentInput);
          }
          return "";
        });
      }, 300);
      return () => clearTimeout(t);
    }
  }, [sttListening]);

  // mastery
  const [mastery, setMastery] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setMastery(sessionMeta.initialMastery), 300);
    return () => clearTimeout(t);
  }, []);

  // hint
  const [hint, setHint] = useState(null);

  // challenge modal
  const [challengeOpen, setChallengeOpen] = useState(true);
  const [picked, setPicked] = useState(null);
  const [resolved, setResolved] = useState(false);

  /* ── send message to backend RAG endpoint ─────────────── */
  const sendStudentMessage = async (text) => {
    const trimmed = (typeof text === "string" ? text : input).trim();
    if (!trimmed || ragLoading) return;

    setMessages((m) => [
      ...m,
      { id: `s-${Date.now()}`, role: "student", text: trimmed },
    ]);
    setInput("");
    setTyping(true);
    setRagLoading(true);

    try {
      const res = await fetch("/api/v1/chat/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, grade, topic }),
      });
      const data = await res.json();
      setTyping(false);

      if (res.ok) {
        setMessages((m) => [
          ...m,
          {
            id: `t-${Date.now()}`,
            role: "tutor",
            text: data.reply,
            meta: `${data.chunks_used} chunks · ${data.model}`,
          },
        ]);
      } else {
        setMessages((m) => [
          ...m,
          {
            id: `e-${Date.now()}`,
            role: "tutor",
            text: `⚠️ ${data.detail || "Something went wrong"}`,
          },
        ]);
      }
    } catch (err) {
      setTyping(false);
      setMessages((m) => [
        ...m,
        {
          id: `e-${Date.now()}`,
          role: "tutor",
          text: "⚠️ Network error — is the backend running?",
        },
      ]);
    } finally {
      setRagLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendStudentMessage(input);
    }
  };

  const handlePick = (opt) => {
    if (resolved) return;
    setPicked(opt);
    if (opt === challenge.correct) {
      setResolved(true);
      setMastery((m) => Math.min(100, m + 10));
      setMessages((m) => [
        ...m,
        {
          id: `t-correct-${Date.now()}`,
          role: "tutor",
          text: "🎉 Correct! 3/8 it is — 3 eaten out of 8 equal pieces.",
        },
      ]);
      setTimeout(() => {
        setChallengeOpen(false);
        setTyping(true);
        setTimeout(() => {
          setTyping(false);
          setMessages((m) => [
            ...m,
            {
              id: `t-follow-${Date.now()}`,
              role: "tutor",
              text: "Now try this: if you eat 2 more pieces, what fraction have you eaten in total?",
            },
          ]);
        }, 1400);
      }, 1200);
    } else {
      setHint(
        "Count the pieces eaten (top number) and the total equal pieces (bottom number). Total pieces = 8.",
      );
    }
  };

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Top bar */}
      <div className="sticky top-0 z-20 flex items-center justify-between px-4 py-3 border-b bg-background">
        <div className="leading-tight">
          <p className="font-medium">{sessionMeta.topic}</p>
          <p className="text-xs text-muted-foreground">
            {sessionMeta.grade} · Session {sessionMeta.sessionNumber}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs px-3 py-1.5 rounded-full border bg-muted">
            {formatTime(elapsed)}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground"
            onClick={() => navigate("/dashboard")}
          >
            <X className="h-4 w-4" /> End Session
          </Button>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <aside className="hidden md:flex w-[300px] flex-col gap-3 p-3 border-r bg-background overflow-y-auto">
          {/* ─── Live Webcam Card ──────────────────────────── */}
          <div className="rounded-xl overflow-hidden border">
            <div className="relative aspect-[4/3] bg-neutral-900">
              {isCapturing ? (
                <>
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover"
                    style={{ transform: "scaleX(-1)" }}
                  />
                  {/* Face mesh canvas overlay */}
                  <canvas
                    ref={canvasRef}
                    className="absolute inset-0 w-full h-full pointer-events-none"
                    style={{ transform: "scaleX(-1)" }}
                  />
                  {/* Live badge */}
                  <div className="absolute top-2 left-2 flex items-center gap-1 bg-black/60 text-white text-[10px] font-medium px-2 py-0.5 rounded-full">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75 animate-ping" />
                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500" />
                    </span>
                    LIVE
                  </div>
                  {/* Subtitle overlay (speech recognition) */}
                  <SubtitleOverlay
                    interimTranscript={interimTranscript}
                    finalTranscript={finalTranscript}
                    isListening={sttListening}
                  />
                </>
              ) : (
                <>
                  {/* Hidden video element for stream attachment before metadata loads */}
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="hidden"
                  />
                  <div className="flex flex-col items-center justify-center h-full gap-2 text-neutral-500">
                    <Video className="h-8 w-8 opacity-40" />
                    <span className="text-xs">Camera off</span>
                  </div>
                </>
              )}
            </div>
            {/* Bottom bar: emotion/gaze + camera toggle */}
            <div className="flex items-center justify-between px-3 py-2 gap-2">
              {isCapturing && meshReady ? (
                <PerceptionHUD emotion={emotion} gaze={gaze} className="scale-[0.85] origin-left" />
              ) : (
                <span className="text-[11px] text-muted-foreground">No detection</span>
              )}
              <button
                onClick={isCapturing ? stopCapture : startCapture}
                className={cn(
                  "inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-colors",
                  isCapturing
                    ? "border-red-300 text-red-600 hover:bg-red-50"
                    : "border-teal-300 text-teal-600 hover:bg-teal-50",
                )}
              >
                {isCapturing ? (
                  <><Square className="h-3 w-3" /> Stop</>
                ) : (
                  <><Video className="h-3 w-3" /> Start</>
                )}
              </button>
            </div>
            {/* Camera error */}
            {camError && (
              <div className="px-3 pb-2">
                <p className="text-[11px] text-red-500">{camError}</p>
              </div>
            )}
          </div>

          {/* Hint pinned to bottom */}
          <AnimatePresence>
            {hint && (
              <motion.div
                key="hint"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.25 }}
                className="mt-auto bg-blue-50 border border-blue-200 rounded-xl p-3"
              >
                <p className="text-xs font-medium text-blue-700 mb-1">Hint 💡</p>
                <p className="text-xs text-blue-900 leading-relaxed">{hint}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </aside>

        {/* Chat panel */}
        <section className="flex-1 flex flex-col h-full relative">
          {/* Messages */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scroll-smooth"
          >
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className={cn(
                    "flex items-end gap-2",
                    m.role === "student" && "flex-row-reverse",
                  )}
                >
                  {m.role === "tutor" ? (
                    <TutorAvatar />
                  ) : (
                    <StudentAvatar initial={initial} />
                  )}
                  <div
                    className={cn(
                      "max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed border",
                      m.role === "tutor"
                        ? "bg-card"
                        : "bg-teal-50 border-teal-200 text-teal-900",
                    )}
                  >
                    {renderInline(m.text)}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>

            {typing && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-end gap-2"
              >
                <TutorAvatar />
                <div className="bg-card border rounded-2xl px-4 py-3">
                  <div className="flex gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-bounce" />
                  </div>
                </div>
              </motion.div>
            )}
          </div>

          {/* Mastery bar */}
          <div className="border-t px-4 pt-2 pb-0 bg-background flex-shrink-0">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{sessionMeta.topic} Mastery</span>
              <span className="font-mono text-teal-600">{mastery}%</span>
            </div>
            <div className="mt-1 h-1 w-full bg-muted rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-green-500"
                initial={{ width: 0 }}
                animate={{ width: `${mastery}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
              />
            </div>
          </div>

          {/* Input */}
          <div className="flex items-center gap-2 px-4 py-3 bg-background flex-shrink-0">
            <button
              type="button"
              className={cn(
                "relative h-10 w-10 rounded-full border grid place-items-center transition-colors shrink-0",
                sttListening
                  ? "border-teal-500 text-teal-600"
                  : "border-input text-muted-foreground hover:bg-accent",
              )}
              aria-label="Hold spacebar to speak"
              title="Hold Spacebar to speak"
              tabIndex={-1}
            >
              {sttListening && (
                <span className="absolute inset-0 rounded-full border-2 border-teal-400 animate-ping" />
              )}
              <Mic className="h-4 w-4" />
            </button>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder={sttListening ? "Listening…" : "Type your answer or hold Space to speak…"}
              className="rounded-full"
              disabled={ragLoading}
            />
            <button
              type="button"
              onClick={() => sendStudentMessage(input)}
              className="h-10 w-10 rounded-full bg-teal-600 hover:bg-teal-700 text-white grid place-items-center transition-colors disabled:opacity-50 shrink-0"
              disabled={!input.trim() || ragLoading}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>

          {/* Quick Challenge modal overlay */}
          <AnimatePresence>
            {challengeOpen && (
              <motion.div
                key="challenge"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="absolute inset-0 bg-background/60 backdrop-blur-sm flex items-center justify-center z-20"
              >
                <motion.div
                  initial={{ scale: 0.95, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.95, opacity: 0 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                  className="w-full max-w-sm mx-4"
                >
                  <Card className="rounded-2xl border-teal-300 border p-5 shadow-lg">
                    <div className="flex items-center gap-2 text-teal-600 text-sm font-medium">
                      <span>{challenge.icon}</span>
                      <span>Quick Challenge</span>
                    </div>
                    <p className="text-sm leading-relaxed mt-2 mb-4">
                      {challenge.question}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {challenge.options.map((opt) => {
                        const isPicked = picked === opt;
                        const isCorrect = opt === challenge.correct;
                        const showCorrect = resolved && isCorrect;
                        const showWrong = isPicked && !isCorrect;
                        const dimmed =
                          picked && !isPicked && !(resolved && isCorrect);
                        return (
                          <button
                            key={opt}
                            onClick={() => handlePick(opt)}
                            className={cn(
                              "px-4 py-1.5 rounded-full border text-sm font-medium transition-colors",
                              "hover:bg-accent",
                              showCorrect &&
                                "bg-green-50 border-green-400 text-green-800 hover:bg-green-50",
                              showWrong &&
                                "bg-red-50 border-red-300 text-red-700 hover:bg-red-50",
                              dimmed && "opacity-40",
                            )}
                            disabled={resolved}
                          >
                            {opt}
                          </button>
                        );
                      })}
                    </div>
                  </Card>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
      </div>
    </div>
  );
};

export default Session;
