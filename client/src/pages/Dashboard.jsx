import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Flame, Star, ChevronRight, ArrowRight, Sparkles, BookOpen, Clock, Target,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { usePalmStore } from "@/store/usePalmStore";

const topics = [
  { id: "fractions", name: "Fractions", description: "Halves, thirds & quarters made simple.", difficulty: "Medium", status: "inprogress", mastery: 55, recommended: true, sessions: 6, accuracy: 72, timeSpent: "1h 20m", subtopics: 5, estTime: "45m" },
  { id: "multiplication", name: "Multiplication", description: "Times tables and quick patterns.", difficulty: "Easy", status: "inprogress", mastery: 30, recommended: false, sessions: 3, accuracy: 65, timeSpent: "40m", subtopics: 4, estTime: "30m" },
  { id: "addition", name: "Addition & Subtraction", description: "Build a strong number sense foundation.", difficulty: "Easy", status: "completed", mastery: 100, recommended: false, sessions: 8, accuracy: 92, timeSpent: "2h 10m", subtopics: 4, estTime: "—" },
  { id: "geometry", name: "Geometry", description: "Shapes, sides and angles around us.", difficulty: "Medium", status: "notstarted", mastery: 0, recommended: false, sessions: 0, accuracy: 0, timeSpent: "0m", subtopics: 6, estTime: "50m" },
  { id: "measurement", name: "Measurement", description: "Length, weight and time units.", difficulty: "Hard", status: "notstarted", mastery: 0, recommended: false, sessions: 0, accuracy: 0, timeSpent: "0m", subtopics: 5, estTime: "1h" },
  { id: "wordproblems", name: "Word Problems", description: "Turn stories into math step-by-step.", difficulty: "Hard", status: "notstarted", mastery: 0, recommended: false, sessions: 0, accuracy: 0, timeSpent: "0m", subtopics: 7, estTime: "1h 15m" },
];

const sessions = [
  { id: 1, topic: "Fractions", days: 1, mins: 18, questions: 12, status: "Improved" },
  { id: 2, topic: "Multiplication", days: 2, mins: 14, questions: 10, status: "Needs Practice" },
  { id: 3, topic: "Addition & Subtraction", days: 3, mins: 22, questions: 15, status: "Improved" },
  { id: 4, topic: "Fractions", days: 5, mins: 12, questions: 8, status: "Needs Practice" },
];

const focusAreas = [
  { id: "f1", topic: "Fraction comparisons", mastery: 42 },
  { id: "f2", topic: "Multi-digit multiplication", mastery: 35 },
  { id: "f3", topic: "Word problem setup", mastery: 28 },
];

const filters = [
  { key: "all", label: "All" },
  { key: "inprogress", label: "In Progress" },
  { key: "notstarted", label: "Not Started" },
  { key: "completed", label: "Completed" },
];

const difficultyClasses = {
  Easy: "bg-emerald-100 text-emerald-700 border-transparent hover:bg-emerald-100",
  Medium: "bg-amber-100 text-amber-700 border-transparent hover:bg-amber-100",
  Hard: "bg-rose-100 text-rose-700 border-transparent hover:bg-rose-100",
};

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};

const Dashboard = () => {
  const { learnerName, grade } = usePalmStore();
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState(null);

  const overall = 20;
  const [animatedOverall, setAnimatedOverall] = useState(0);
  const [animatedMastery, setAnimatedMastery] = useState({});
  const [animatedFocus, setAnimatedFocus] = useState({});

  useEffect(() => {
    const t = setTimeout(() => {
      setAnimatedOverall(overall);
      setAnimatedMastery(Object.fromEntries(topics.map((t) => [t.id, t.mastery])));
      setAnimatedFocus(Object.fromEntries(focusAreas.map((f) => [f.id, f.mastery])));
    }, 250);
    return () => clearTimeout(t);
  }, []);

  const filtered = useMemo(
    () => (filter === "all" ? topics : topics.filter((t) => t.status === filter)),
    [filter]
  );

  const actionLabel = (s) =>
    s === "completed" ? "Review" : s === "inprogress" ? "Continue →" : "Start →";

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.section {...fadeUp} transition={{ duration: 0.35, ease: "easeOut" }} className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight">Hi, {learnerName || "Learner"} 👋</h1>
          <p className="text-sm text-muted-foreground mt-1">Let's continue your learning journey</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 text-emerald-700 px-3 py-1.5 text-xs font-medium"><Flame className="h-3.5 w-3.5" /> 5 day streak</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 text-emerald-700 px-3 py-1.5 text-xs font-medium"><Star className="h-3.5 w-3.5" /> 340 XP</span>
        </div>
      </motion.section>

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
            <p className="text-sm text-muted-foreground">You've completed {overall}% of your learning journey</p>
            <div className="grid grid-cols-3 gap-3 pt-1">
              {[
                { label: "Topics Done", value: 2, icon: BookOpen },
                { label: "Sessions", value: 5, icon: Sparkles },
                { label: "Accuracy", value: "70%", icon: Target },
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
                    <p className="text-xs text-muted-foreground mt-1">{t.description}</p>
                    <div className="mt-3">
                      <Progress value={animatedMastery[t.id] ?? 0} className={cn("h-1.5 [&>div]:transition-all [&>div]:duration-700", isCompleted ? "[&>div]:bg-emerald-500" : "[&>div]:bg-teal-500", t.status === "notstarted" && "[&>div]:bg-muted-foreground/20")} />
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">{t.mastery}% mastered</span>
                      <Button size="sm" variant={isCompleted ? "secondary" : "outline"} onClick={(e) => e.stopPropagation()} className="h-7 text-xs">{actionLabel(t.status)}</Button>
                    </div>
                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.div key="panel" initial={{ maxHeight: 0, opacity: 0 }} animate={{ maxHeight: 240, opacity: 1 }} exit={{ maxHeight: 0, opacity: 0 }} transition={{ duration: 0.35, ease: "easeOut" }} className="overflow-hidden">
                          <div className="mt-4 pt-4 border-t space-y-3">
                            <div className="grid grid-cols-3 gap-2">
                              {t.status === "notstarted" ? (
                                <>
                                  <Stat label="Subtopics" value={t.subtopics} />
                                  <Stat label="Est. Time" value={t.estTime} />
                                  <Stat label="Difficulty" value={t.difficulty} />
                                </>
                              ) : (
                                <>
                                  <Stat label="Sessions" value={t.sessions} />
                                  <Stat label="Accuracy" value={`${t.accuracy}%`} />
                                  <Stat label="Time Spent" value={t.timeSpent} />
                                </>
                              )}
                            </div>
                            <div className="flex gap-2">
                              <Button size="sm" variant="outline" onClick={(e) => e.stopPropagation()} className="flex-1 border-teal-500 text-teal-700 hover:bg-teal-50 hover:text-teal-700">Start Practice</Button>
                              <Button size="sm" variant="outline" onClick={(e) => e.stopPropagation()} className="flex-1">View Notes</Button>
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
            <ul>
              {sessions.map((s) => (
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
            <div className="divide-y">
              {focusAreas.map((f) => (
                <div key={f.id} className="py-3 flex items-center gap-4">
                  <div className="flex-1 min-w-0 space-y-2">
                    <p className="text-sm font-medium truncate">{f.topic}</p>
                    <Progress value={animatedFocus[f.id] ?? 0} className="h-1.5 [&>div]:bg-teal-500 [&>div]:transition-all [&>div]:duration-700" />
                  </div>
                  <Button size="sm" variant="outline" className="border-teal-500 text-teal-700 hover:bg-teal-50 hover:text-teal-700">Practice <ArrowRight className="ml-1 h-3 w-3" /></Button>
                </div>
              ))}
            </div>
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
