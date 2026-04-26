import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, Send, X, Video, Square, Eye, EyeOff, Volume2, VolumeX } from "lucide-react";
import { useTextToSpeech } from "@/hooks/useTextToSpeech";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { usePalmStore } from "@/store/usePalmStore";
import useFaceMesh from "@/hooks/useFaceMesh";
import usePerceptionStream from "@/hooks/usePerceptionStream";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import PerceptionHUD from "@/components/PerceptionHUD";

import { getMastery, getStudentSessions, getSessionEvents, endSession } from "@/lib/api";

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

const cleanLatex = (text) =>
  text
    .replace(/\$\$(.*?)\$\$/g, "$1")       // $$...$$ → content
    .replace(/\$(.*?)\$/g, "$1")           // $...$ → content
    .replace(/\\text\{(.*?)\}/g, "$1")     // \text{kg} → kg
    .replace(/\\frac\{(.*?)\}\{(.*?)\}/g, "$1/$2")  // \frac{3}{8} → 3/8
    .replace(/\\\\/g, "");                 // stray backslashes

const renderInline = (text) => {
  const cleaned = cleanLatex(text);
  const parts = cleaned.split(/(`[^`]+`|\b\d+\/\d+\b)/g);
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
  const { learnerName, studentId: storeStudentId, grade: storeGrade, token } = usePalmStore();
  const initial = (learnerName?.[0] || "S").toUpperCase();
  const studentId = storeStudentId || "00000000-0000-0000-0000-000000000001";

  // ── Session metadata from backend ──────────────────────────────────
  const [sessionTopic, setSessionTopic] = useState("");
  const [sessionGrade, setSessionGrade] = useState(storeGrade || 3);

  // Fetch session info on mount
  useEffect(() => {
    if (!studentId || !sessionId) return;
    getStudentSessions(studentId, token).then((sessions) => {
      const match = sessions.find((s) => s.id === sessionId);
      if (match) {
        setSessionTopic(match.topic || "Practice");
        setSessionGrade(match.grade || storeGrade);
      }
    }).catch(() => {});
  }, [sessionId, studentId, token, storeGrade]);

  // Load previous chat history when resuming a session
  const historyLoadedRef = useRef(false);
  const hasHistoryRef = useRef(false);
  useEffect(() => {
    if (!sessionId || historyLoadedRef.current) return;
    historyLoadedRef.current = true;
    getSessionEvents(sessionId, token).then((events) => {
      if (!events || events.length === 0) return;
      const restored = [];
      for (const e of events) {
        if (e.query_text) {
          restored.push({ id: `h-q-${e.id}`, role: "student", text: e.query_text });
        }
        if (e.response_text) {
          restored.push({ id: `h-r-${e.id}`, role: "tutor", text: e.response_text, meta: e.agent_used });
        }
      }
      if (restored.length > 0) {
        hasHistoryRef.current = true;
        setMessages(restored);
      }
    }).catch(() => {});
  }, [sessionId, token]);

  // Timer — starts at 0
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  /* ══════════════════════════════════════════════════════════
     Webcam capture state
     ══════════════════════════════════════════════════════════ */
  const [stream, setStream] = useState(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [camError, setCamError] = useState(null);
  const [isCameraHidden, setIsCameraHidden] = useState(false);
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

  /* ── text-to-speech (Web Speech API) ─────────────────── */
  const {
    speak: ttsSpeak,
    stop: ttsStop,
    isSpeaking: ttsSpeaking,
    isSupported: ttsSupported,
  } = useTextToSpeech();
  const [isTtsEnabled, setIsTtsEnabled] = useState(true);
  // Track which message id is currently being spoken
  const ttsSpeakingIdRef = useRef(null);

  /* ── grade & topic for RAG queries ───────────────────────── */
  const [grade, setGrade] = useState(storeGrade || 3);
  const [topic, setTopic] = useState("");
  const [ragLoading, setRagLoading] = useState(false);

  // Sync topic when sessionTopic loads
  useEffect(() => {
    if (sessionTopic) setTopic(sessionTopic);
  }, [sessionTopic]);

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
  const sttTriggerRef = useRef(null); // 'spacebar' | 'button'
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
        sttTriggerRef.current = 'spacebar';
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

  /* ── mic button click toggle ─────────────────────────────── */
  const toggleMic = useCallback(() => {
    if (sttListening) {
      stopSTT();
    } else {
      sttTriggerRef.current = 'button';
      startSTT();
    }
  }, [sttListening, startSTT, stopSTT]);

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

  /* ── auto-start on mount ───────────────────────────────── */
  const initRef = useRef(false);
  useEffect(() => {
    if (!initRef.current) {
      initRef.current = true;
      startCapture();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── cleanup on unmount ───────────────────────────────── */
  useEffect(() => {
    return () => {
      ttsStop(); // Stop any ongoing TTS on navigation/unmount
      if (videoRef.current && videoRef.current.srcObject) {
        const str = videoRef.current.srcObject;
        str.getTracks().forEach((track) => track.stop());
      }
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [stream, ttsStop]);

  /* ══════════════════════════════════════════════════════════
     Chat state — connected to WebSocket orchestrator pipeline
     ══════════════════════════════════════════════════════════ */
  const [messages, setMessages] = useState([]);
  const [typing, setTyping] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);
  const wsRef = useRef(null);
  const streamingTextRef = useRef("");
  const streamingIdRef = useRef(null);

  // ── Mastery — fetched from backend, updated live via WS ────
  const [mastery, setMastery] = useState(0);
  useEffect(() => {
    if (!studentId || !topic) return;
    getMastery(studentId, token).then((scores) => {
      const match = scores.find((s) => s.topic === topic);
      if (match) setMastery(Math.round(match.score * 100));
    }).catch(() => {});
  }, [studentId, token, topic]);

  // hint
  const [hint, setHint] = useState(null);

  // ── WebSocket connection ───────────────────────────────────
  const wsReady = useRef(false);
  const pendingGreeting = useRef(false);

  useEffect(() => {
    if (!sessionId || !topic) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/tutor/${sessionId}?grade=${grade}&topic=${encodeURIComponent(topic)}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected to tutor");
      wsReady.current = true;
      // Only send greeting for new sessions (no prior history)
      if (!hasHistoryRef.current) {
        pendingGreeting.current = true;
        setTyping(true);
        ws.send(JSON.stringify({
          type: "trigger",
          payload: {
            student_id: studentId,
            query: `Greet the student named ${learnerName || "there"} and introduce today's topic: ${topic}. Keep it short and friendly (under 80 words).`,
          },
        }));
      }
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "token") {
        const { token: tok, done } = msg.payload;
        if (!done) {
          // Accumulate streaming text
          if (!streamingIdRef.current) {
            streamingIdRef.current = `t-${Date.now()}`;
            streamingTextRef.current = "";
          }
          streamingTextRef.current += tok;

          // Update or add the streaming message
          const id = streamingIdRef.current;
          const text = streamingTextRef.current;
          setMessages((prev) => {
            const existing = prev.find((m) => m.id === id);
            if (existing) {
              return prev.map((m) => m.id === id ? { ...m, text } : m);
            }
            return [...prev, { id, role: "tutor", text }];
          });
          setTyping(false);
        }
      }

      if (msg.type === "response_complete") {
        const { full_text, agent_used, mastery_delta } = msg.payload;
        // Finalize the message with full text
        if (streamingIdRef.current) {
          const id = streamingIdRef.current;
          setMessages((prev) =>
            prev.map((m) => m.id === id ? { ...m, text: full_text, meta: agent_used } : m)
          );
        }
        // Update mastery from delta
        if (mastery_delta && mastery_delta !== 0) {
          setMastery((prev) => Math.min(100, Math.max(0, Math.round(prev + mastery_delta * 100))));
        }
        // Speak the response via TTS if enabled
        if (isTtsEnabled && full_text) {
          try {
            ttsSpeakingIdRef.current = streamingIdRef.current;
            ttsSpeak(full_text);
          } catch (_) {
            // Silently fail if browser blocks autoplay audio
          }
        }
        // Reset streaming state
        streamingIdRef.current = null;
        streamingTextRef.current = "";
        setRagLoading(false);
        pendingGreeting.current = false;
      }

      if (msg.type === "error") {
        setTyping(false);
        setRagLoading(false);
        setMessages((prev) => [
          ...prev,
          { id: `e-${Date.now()}`, role: "tutor", text: `⚠️ ${msg.payload?.message || "Error"}` },
        ]);
        streamingIdRef.current = null;
        streamingTextRef.current = "";
      }
    };

    ws.onerror = () => {
      console.error("[WS] Connection error");
      wsReady.current = false;
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected");
      wsReady.current = false;
    };

    return () => {
      ws.close();
      wsRef.current = null;
      wsReady.current = false;
    };
  }, [sessionId, topic, grade, studentId, learnerName]);

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
      // Only auto-send when STT was triggered via spacebar push-to-talk
      if (sttTriggerRef.current === 'spacebar') {
        const t = setTimeout(() => {
          setInput((currentInput) => {
            if (currentInput.trim()) {
              sendStudentMessage(currentInput);
            }
            return "";
          });
        }, 300);
        sttTriggerRef.current = null;
        return () => clearTimeout(t);
      }
      sttTriggerRef.current = null;
    }
  }, [sttListening]);

  /* ── send message via WebSocket ───────────────────────── */
  const sendStudentMessage = (text) => {
    const trimmed = (typeof text === "string" ? text : input).trim();
    if (!trimmed || ragLoading) return;

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setMessages((m) => [
        ...m,
        { id: `e-${Date.now()}`, role: "tutor", text: "⚠️ Connection lost — please refresh the page." },
      ]);
      return;
    }

    setMessages((m) => [
      ...m,
      { id: `s-${Date.now()}`, role: "student", text: trimmed },
    ]);
    setInput("");
    setTyping(true);
    setRagLoading(true);

    ws.send(JSON.stringify({
      type: "trigger",
      payload: {
        student_id: studentId,
        query: trimmed,
      },
    }));
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendStudentMessage(input);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Top bar */}
      <div className="sticky top-0 z-20 flex items-center justify-between px-4 py-3 border-b bg-background">
        <div className="leading-tight">
          <p className="font-medium">{sessionTopic || "Loading..."}</p>
          <p className="text-xs text-muted-foreground">
            Grade {sessionGrade}
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
            onClick={async () => {
              ttsStop(); // Stop any ongoing TTS
              try {
                await endSession(sessionId, {
                  durationSeconds: elapsed,
                  masteryScore: mastery,
                }, token);
              } catch (err) {
                console.error("[Session] Failed to end session:", err);
              }
              navigate("/dashboard");
            }}
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
            <div className="relative aspect-[4/3] bg-neutral-900 group">
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
                    className={cn(
                      "absolute inset-0 w-full h-full pointer-events-none transition-opacity duration-300",
                      isCameraHidden ? "opacity-0" : "opacity-100"
                    )}
                    style={{ transform: "scaleX(-1)" }}
                  />
                  
                  {/* Hidden Camera Overlay */}
                  <AnimatePresence>
                    {isCameraHidden && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="absolute inset-0 bg-neutral-800 flex flex-col items-center justify-center z-10"
                      >
                        <div className="text-neutral-400 flex flex-col items-center mt-12">
                          <EyeOff className="h-8 w-8 opacity-40 mb-2" />

                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Hide/Show Camera Button Overlay */}
                  <div className={cn(
                    "absolute inset-0 flex items-center justify-center z-20 pointer-events-none transition-opacity duration-300",
                    isCameraHidden ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                  )}>
                    <button
                      onClick={() => setIsCameraHidden(!isCameraHidden)}
                      className="pointer-events-auto bg-black/60 hover:bg-black/80 text-white p-3.5 rounded-full backdrop-blur-md transition-all transform hover:scale-105 shadow-lg"
                      aria-label={isCameraHidden ? "Show camera" : "Hide camera"}
                    >
                      {isCameraHidden ? <Eye className="h-6 w-6" /> : <EyeOff className="h-6 w-6" />}
                    </button>
                  </div>

                  {/* Live badge */}
                  <div className="absolute top-2 left-2 flex items-center gap-1 bg-black/60 text-white text-[10px] font-medium px-2 py-0.5 rounded-full z-20">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75 animate-ping" />
                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500" />
                    </span>
                    LIVE
                  </div>

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
            {/* Bottom bar: emotion/gaze + camera status */}
            <div className="flex items-center px-3 py-2 gap-2">
              {isCapturing && meshReady && !isCameraHidden ? (
                <PerceptionHUD emotion={emotion} gaze={gaze} className="scale-[0.85] origin-left" />
              ) : (
                <span className="text-[11px] text-muted-foreground">
                  {!isCameraHidden && "No detection"}
                </span>
              )}
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
                    <div className="relative">
                      <TutorAvatar />
                      {/* Animated wave indicator while TTS is speaking this message */}
                      {ttsSpeaking && ttsSpeakingIdRef.current === m.id && (
                        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 flex items-end gap-[2px]">
                          <span className="w-[3px] h-2 bg-teal-500 rounded-full animate-pulse [animation-delay:-0.3s]" />
                          <span className="w-[3px] h-3 bg-teal-500 rounded-full animate-pulse [animation-delay:-0.15s]" />
                          <span className="w-[3px] h-2 bg-teal-500 rounded-full animate-pulse" />
                        </div>
                      )}
                    </div>
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
              <span className="text-muted-foreground">{sessionTopic || "Topic"} Mastery</span>
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
              onClick={toggleMic}
              className={cn(
                "relative h-10 w-10 rounded-full border grid place-items-center transition-colors shrink-0",
                sttListening
                  ? "border-teal-500 text-teal-600"
                  : "border-input text-muted-foreground hover:bg-accent",
              )}
              aria-label={sttListening ? "Stop listening" : "Click to speak"}
              title={sttListening ? "Stop listening" : "Click to speak (or hold Spacebar)"}
            >
              {sttListening && (
                <span className="absolute inset-0 rounded-full border-2 border-teal-400 animate-ping" />
              )}
              <Mic className="h-4 w-4" />
            </button>
            {/* TTS mute / unmute toggle */}
            {ttsSupported && (
              <button
                type="button"
                onClick={() => {
                  setIsTtsEnabled((prev) => {
                    if (prev) ttsStop(); // turning off → stop current speech
                    return !prev;
                  });
                }}
                className={cn(
                  "relative h-10 w-10 rounded-full border grid place-items-center transition-colors shrink-0",
                  isTtsEnabled
                    ? "border-teal-500 text-teal-600"
                    : "border-input text-muted-foreground hover:bg-accent",
                )}
                aria-label={isTtsEnabled ? "Mute tutor voice" : "Unmute tutor voice"}
                title={isTtsEnabled ? "Mute tutor voice" : "Unmute tutor voice"}
              >
                {isTtsEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </button>
            )}
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
        </section>
      </div>
    </div>
  );
};

export default Session;
