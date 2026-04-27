import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRight, ArrowRight, Sparkles, BookOpen, Clock, Target,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { usePalmStore } from "@/store/usePalmStore";
import { getTopics, getMastery, getStudentSessions, createSession } from "@/lib/api";

/* ── difficulty label helper ──────────────────────────────────────────── */

const diffLabel = (d) =>
  d <= 1 ? "Easy" : d <= 2 ? "Medium" : "Hard";

const difficultyClasses = {
  Easy: "bg-emerald-100 text-emerald-700 border-transparent hover:bg-emerald-100",
  Medium: "bg-amber-100 text-amber-700 border-transparent hover:bg-amber-100",
  Hard: "bg-rose-100 text-rose-700 border-transparent hover:bg-rose-100",
};

const filters = [
  { key: "all", label: "All" },
  { key: "inprogress", label: "In Progress" },
  { key: "notstarted", label: "Not Started" },
  { key: "completed", label: "Completed" },
];

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};

const Dashboard = () => {
  const { learnerName, grade, studentId, token } = usePalmStore();
  const navigate = useNavigate();
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState(null);
  const [loadingSession, setLoadingSession] = useState(false);

  // ── Data from backend ─────────────────────────────────────────────
  const [topics, setTopics] = useState([]);
  const [masteryMap, setMasteryMap] = useState({});
  const [allSessions, setAllSessions] = useState([]);
  const [recentSessions, setRecentSessions] = useState([]);

  // Fetch curriculum topics for the student's grade
  useEffect(() => {
    getTopics(grade).then(setTopics).catch(() => {});
  }, [grade]);

  // Fetch mastery + sessions
  useEffect(() => {
    if (!studentId) return;
    getMastery(studentId, token).then((scores) => {
      const map = {};
      scores.forEach((s) => {
        map[s.chapter_id] = {
          percent: Math.round(s.completion_percent || 0),
          was_completed: s.was_completed || false,
        };
      });
      setMasteryMap(map);
    }).catch(() => {});
    getStudentSessions(studentId, token).then((sessions) => {
      setAllSessions(sessions);
      setRecentSessions(sessions.slice(0, 6));
    }).catch(() => {});
  }, [studentId, token]);

  // ── Derived state ─────────────────────────────────────────────────

  // Enrich topics with mastery data
  const enrichedTopics = useMemo(() => {
    const startedChapters = new Set(allSessions.map(s => s.chapter_id));
    return topics.map((t) => {
      const data = masteryMap[t.id];
      const m = data ? data.percent : 0;
      const wasCompleted = data ? data.was_completed : false;
      const hasStarted = startedChapters.has(t.id);
      // Issue 8: was_completed keeps "completed" status even if section was reset
      const status = (m >= 100 || wasCompleted) ? "completed" : (m > 0 || hasStarted) ? "inprogress" : "notstarted";
      return {
        id: t.id,
        name: t.topic,
        description: "",
        difficulty: "Medium",
        status,
        mastery: m,
        wasCompleted,
        recommended: m > 0 && m < 50,
      };
    });
  }, [topics, masteryMap, allSessions]);

  const overall = useMemo(() => {
    if (enrichedTopics.length === 0) return 0;
    const total = enrichedTopics.reduce((a, t) => a + t.mastery, 0);
    return Math.round(total / enrichedTopics.length);
  }, [enrichedTopics]);

  const completedCount = useMemo(
    () => enrichedTopics.filter((t) => t.status === "completed").length,
    [enrichedTopics]
  );

  const focusAreas = useMemo(() =>
    enrichedTopics.filter((t) => t.mastery > 0 && t.mastery < 50).slice(0, 3).map((t, i) => ({
      id: `f${i}`, topic: t.name, mastery: t.mastery,
    })),
    [enrichedTopics]
  );

  // Format recent sessions for display
  const displaySessions = useMemo(() => {
    // Build chapter_id → topic name lookup
    const chapterNames = {};
    topics.forEach((t) => { chapterNames[t.id] = t.topic; });

    return recentSessions.map((s, i) => {
      const started = s.started_at ? new Date(s.started_at) : new Date();
      const days = Math.max(1, Math.round((Date.now() - started.getTime()) / 86400000));
      const mins = s.duration_seconds ? Math.round(s.duration_seconds / 60) : 0;
      return {
        id: s.id || i,
        topic: chapterNames[s.chapter_id] || "Practice",
        days,
        mins,
        questions: s.turn_count || 0,
        status: s.ended_at ? "Completed" : "In Progress",
      };
    });
  }, [recentSessions, topics]);

  // Animations
  const [animatedOverall, setAnimatedOverall] = useState(0);
  const [animatedMastery, setAnimatedMastery] = useState({});
  const [animatedFocus, setAnimatedFocus] = useState({});

  useEffect(() => {
    const t = setTimeout(() => {
      setAnimatedOverall(overall);
      setAnimatedMastery(Object.fromEntries(enrichedTopics.map((t) => [t.id, t.mastery])));
      setAnimatedFocus(Object.fromEntries(focusAreas.map((f) => [f.id, f.mastery])));
    }, 250);
    return () => clearTimeout(t);
  }, [overall, enrichedTopics, focusAreas]);

  const filtered = useMemo(
    () => (filter === "all" ? enrichedTopics : enrichedTopics.filter((t) => t.status === filter)),
    [filter, enrichedTopics]
  );

  const handleStartSession = async (topicName) => {
    if (loadingSession || !studentId) return;
    setLoadingSession(true);
    try {
      const session = await createSession({ studentId, grade, topic: topicName }, token);
      navigate(`/session/${session.id}`);
    } catch {
      navigate(`/session/${crypto.randomUUID()}`);
    } finally {
      setLoadingSession(false);
    }
  };

  const actionLabel = (s) =>
    s === "completed" ? "Review" : s === "inprogress" ? "Continue →" : "Start →";

  return (
    <div className="space-y-8">


      {/* Progress card */}
      <motion.section {...fadeUp} transition={{ duration: 0.35, ease: "easeOut", delay: 0.05 }}>
        <Card>
          <CardContent className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <p className="font-medium">Your Progress</p>
              <Button asChild variant="outline" size="sm">
                <Link to="/progress">View Details →</Link>
              </Button>
            </div>
            <Progress value={animatedOverall} className="h-2 [&>div]:bg-emerald-500 [&>div]:transition-all [&>div]:duration-700" />
            <p className="text-sm text-muted-foreground">
              {overall === 0 && allSessions.length === 0
                ? "Start a topic to begin your learning journey!"
                : `You've completed ${overall}% of your learning journey`}
            </p>
            <div className="grid grid-cols-3 gap-3 pt-1">
              {[
                { label: "Topics Done", value: completedCount, icon: BookOpen },
                { label: "Sessions", value: allSessions.length, icon: Sparkles },
                { label: "Total Topics", value: enrichedTopics.length, icon: Target },
              ].map((s) => {
                const Icon = s.icon;
                return (
                  <div key={s.label} className="rounded-lg bg-secondary p-3 flex items-center gap-3">
                    <div className="h-9 w-9 rounded-md bg-background grid place-items-center"><Icon className="h-4 w-4" /></div>
                    <div>
                      <p className="font-semibold leading-none">{s.value}</p>
                      <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </motion.section>

      {/* Topics */}
      <motion.section {...fadeUp} transition={{ duration: 0.35, ease: "easeOut", delay: 0.1 }} className="space-y-4">
        <div className="flex items-end justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Topics</h2>
          <p className="text-xs text-muted-foreground">Tap a card to see details</p>
        </div>

        <div className="flex flex-wrap gap-2">
          {filters.map((f) => {
            const active = filter === f.key;
            return (
              <button key={f.key} onClick={() => setFilter(f.key)} className={cn("rounded-full px-4 py-1.5 text-xs font-medium border transition-all", active ? "bg-teal-500 text-white border-teal-500 shadow-sm" : "bg-background text-muted-foreground border-border hover:bg-accent hover:text-foreground")}>
                {f.label}
              </button>
            );
          })}
        </div>

        {enrichedTopics.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground">
              <p className="text-sm">Loading topics for Grade {grade}...</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <AnimatePresence mode="popLayout">
              {filtered.map((t, idx) => {
                const isOpen = expanded === t.id;
                const isCompleted = t.status === "completed";
                return (
                  <motion.div key={t.id} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25, delay: idx * 0.04 }} className="relative">
                    {t.recommended && (
                      <span className="absolute -top-2 left-3 z-10 rounded-full bg-emerald-500 text-white text-[10px] font-semibold px-2 py-0.5 shadow-sm">Recommended</span>
                    )}
                    <div onClick={() => setExpanded(isOpen ? null : t.id)} className={cn("group cursor-pointer rounded-2xl border bg-card p-4 transition-all duration-200", "hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-sm", isCompleted && "opacity-65", t.recommended && "border-teal-500/60")}>
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-medium leading-tight">{t.name}</p>
                        <Badge className={cn("text-[10px]", difficultyClasses[t.difficulty])}>{t.difficulty}</Badge>
                      </div>
                      {t.description && (
                        <p className="text-xs text-muted-foreground mt-1">{t.description}</p>
                      )}
                      <div className="mt-3">
                        <Progress value={animatedMastery[t.id] ?? 0} className={cn("h-1.5 [&>div]:transition-all [&>div]:duration-700", isCompleted ? "[&>div]:bg-emerald-500" : "[&>div]:bg-teal-500", t.status === "notstarted" && "[&>div]:bg-muted-foreground/20")} />
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">{t.mastery}% mastered</span>
                        <Button size="sm" variant={isCompleted ? "secondary" : "outline"} onClick={(e) => { e.stopPropagation(); handleStartSession(t.name); }} className="h-7 text-xs" disabled={loadingSession}>{actionLabel(t.status)}</Button>
                      </div>
                      <AnimatePresence initial={false}>
                        {isOpen && (
                          <motion.div key="panel" initial={{ maxHeight: 0, opacity: 0 }} animate={{ maxHeight: 240, opacity: 1 }} exit={{ maxHeight: 0, opacity: 0 }} transition={{ duration: 0.35, ease: "easeOut" }} className="overflow-hidden">
                            <div className="mt-4 pt-4 border-t space-y-3">
                              <div className="grid grid-cols-2 gap-2">
                                <Stat label="Difficulty" value={t.difficulty} />
                                <Stat label="Mastery" value={`${t.mastery}%`} />
                              </div>
                              <div className="flex gap-2">
                                <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleStartSession(t.name); }} className="flex-1 border-teal-500 text-teal-700 hover:bg-teal-50 hover:text-teal-700" disabled={loadingSession}>Start Practice</Button>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </motion.section>

      {/* Bottom section */}
      <motion.section {...fadeUp} transition={{ duration: 0.35, ease: "easeOut", delay: 0.15 }} className="grid lg:grid-cols-2 gap-6">
        {/* Recent sessions */}
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div className="px-6 py-4 border-b">
              <p className="font-medium">Recent Sessions</p>
              <p className="text-xs text-muted-foreground mt-0.5">Your latest practice runs</p>
            </div>
            {displaySessions.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-muted-foreground">
                No sessions yet. Start a topic to begin!
              </div>
            ) : (
              <ul>
                {displaySessions.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 px-6 py-3 border-b last:border-b-0 hover:bg-secondary transition-colors cursor-pointer">
                    <div className="min-w-0">
                      <p className="font-semibold text-sm truncate">{s.topic}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{s.days} day{s.days > 1 ? "s" : ""} ago · {s.mins} mins · {s.questions} questions</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge className={cn("text-[10px]", s.status === "Improved" ? "bg-teal-100 text-teal-700 border-transparent hover:bg-teal-100" : "bg-amber-100 text-amber-700 border-transparent hover:bg-amber-100")}>{s.status}</Badge>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Focus areas */}
        <Card>
          <CardContent className="p-6 space-y-1">
            <div className="flex items-center justify-between mb-2">
              <div>
                <p className="font-medium">Focus Areas</p>
                <p className="text-xs text-muted-foreground mt-0.5">Topics that need a little extra love</p>
              </div>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
            {focusAreas.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                {overall === 0 ? "Start learning to see focus areas here!" : "Great job — no weak areas right now!"}
              </p>
            ) : (
              <div className="divide-y">
                {focusAreas.map((f) => (
                  <div key={f.id} className="py-3 flex items-center gap-4">
                    <div className="flex-1 min-w-0 space-y-2">
                      <p className="text-sm font-medium truncate">{f.topic}</p>
                      <Progress value={animatedFocus[f.id] ?? 0} className="h-1.5 [&>div]:bg-teal-500 [&>div]:transition-all [&>div]:duration-700" />
                    </div>
                    <Button size="sm" variant="outline" className="border-teal-500 text-teal-700 hover:bg-teal-50 hover:text-teal-700" onClick={() => handleStartSession(f.topic)} disabled={loadingSession}>Practice <ArrowRight className="ml-1 h-3 w-3" /></Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.section>
    </div>
  );
};

const Stat = ({ label, value }) => (
  <div className="rounded-lg bg-secondary p-2 text-center">
    <p className="text-sm font-semibold leading-none">{value}</p>
    <p className="text-[10px] text-muted-foreground mt-1">{label}</p>
  </div>
);

export default Dashboard;
