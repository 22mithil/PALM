import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { ArrowLeft, Clock, Target, TrendingUp, Activity } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion";
import { usePalmStore } from "@/store/usePalmStore";
import { getTopics, getMastery, getStudentSessions } from "@/lib/api";

const masteryStatus = (m, hasStarted) => {
  if (m >= 80) return { label: "Strong", variant: "default" };
  if (m >= 50) return { label: "Progressing", variant: "secondary" };
  if (m > 0 || hasStarted) return { label: "Needs Practice", variant: "outline" };
  return { label: "Not Started", variant: "outline" };
};

const ProgressPage = () => {
  const { learnerName, studentId, token, grade } = usePalmStore();
  const [animate, setAnimate] = useState(false);

  // ── Data from backend ──────────────────────────────────────────────
  const [topics, setTopics] = useState([]);
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    const t = setTimeout(() => setAnimate(true), 150);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!studentId) return;

    // Fetch topics + mastery and merge
    Promise.all([
      getTopics(grade),
      getMastery(studentId, token),
    ]).then(([currTopics, scores]) => {
      const masteryMap = {};
      scores.forEach((s) => { masteryMap[s.chapter_id] = Math.round(s.completion_percent || 0); });

      setTopics(currTopics.map((t) => ({
        id: t.id,
        name: t.topic,
        mastery: masteryMap[t.id] ?? 0,
      })));
    }).catch(() => {});

    // Fetch sessions
    getTopics(grade).then((currTopics) => {
      const chapterNames = {};
      currTopics.forEach((t) => { chapterNames[t.id] = t.topic; });

      getStudentSessions(studentId, token).then((sess) => {
        setSessions(sess.map((s) => {
          const d = s.started_at ? new Date(s.started_at) : new Date();
          const mins = s.duration_seconds ? Math.round(s.duration_seconds / 60) : 0;
          return {
            id: s.id,
            topic: chapterNames[s.chapter_id] || "Practice",
            date: d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
            duration: `${mins > 0 ? mins : 1} min`,
            result: s.ended_at ? "Completed" : "In Progress",
            summary: s.session_summary || "Session completed.",
            mastery_score: 0,
            learnings: [],
            mistakes: [],
          };
        }));
      }).catch(() => {});
    }).catch(() => {});
  }, [studentId, token, grade]);

  // ── Poll for background summaries ──────────────────────────────────
  useEffect(() => {
    if (!studentId || !token) return;
    const hasLoading = sessions.some(s => s.summary === "Loading summary...");
    if (!hasLoading) return;

    const interval = setInterval(() => {
      Promise.all([
        getTopics(grade),
        getStudentSessions(studentId, token),
      ]).then(([currTopics, sess]) => {
        const chapterNames = {};
        currTopics.forEach((t) => { chapterNames[t.id] = t.topic; });
        setSessions(sess.map((s) => {
          const d = s.started_at ? new Date(s.started_at) : new Date();
          const mins = s.duration_seconds ? Math.round(s.duration_seconds / 60) : 0;
          return {
            id: s.id,
            topic: chapterNames[s.chapter_id] || "Practice",
            date: d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
            duration: `${mins > 0 ? mins : 1} min`,
            result: s.ended_at ? "Completed" : "In Progress",
            summary: s.session_summary || "Session completed.",
            mastery_score: 0,
            learnings: [],
            mistakes: [],
          };
        }));
      }).catch(() => {});
    }, 3000);

    return () => clearInterval(interval);
  }, [sessions, studentId, token]);

  // ── Derived state ──────────────────────────────────────────────────
  const totalSessions = sessions.length;
  const overallMastery = useMemo(() => {
    if (topics.length === 0) return 0;
    return Math.round(topics.reduce((a, t) => a + t.mastery, 0) / topics.length);
  }, [topics]);

  const focusAreas = useMemo(() => topics.filter((t) => t.mastery < 50 && t.mastery > 0).slice(0, 4), [topics]);

  // Growth data from sessions
  const growthData = useMemo(() => {
    if (sessions.length === 0) return [];
    return sessions.slice(-7).reverse().map((s, i) => ({
      session: `S${i + 1}`,
      mastery: s.mastery_score || 0,
    }));
  }, [sessions]);

  const stats = [
    { label: "Total Sessions", value: totalSessions, icon: Activity },
    { label: "Topics", value: topics.length, icon: Clock },
    { label: "Topics Mastered", value: topics.filter((t) => t.mastery >= 80).length, icon: Target },
    { label: "Overall Mastery", value: `${overallMastery}%`, icon: TrendingUp },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
            Your Progress
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {learnerName ? `${learnerName}, track ` : "Track "}your learning journey
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/dashboard">
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
        </Button>
      </div>

      {/* Section 1 — Overall Performance */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <Card className="rounded-2xl">
          <CardContent className="p-6 space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {stats.map(({ label, value, icon: Icon }) => (
                <div
                  key={label}
                  className="rounded-xl border bg-muted/30 p-4 transition-all hover:shadow-sm hover:scale-[1.02]"
                >
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Icon className="h-4 w-4" />
                    <p className="text-sm">{label}</p>
                  </div>
                  <p className="mt-2 text-xl font-semibold">{value}</p>
                </div>
              ))}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Overall Learning Progress</p>
                <p className="text-sm text-muted-foreground">{overallMastery}%</p>
              </div>
              <Progress value={animate ? overallMastery : 0} className="h-3" />
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Section 2 — Topic Mastery */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.05 }}
        className="space-y-4"
      >
        <div className="flex items-end justify-between">
          <h2 className="text-xl font-semibold">Topic Mastery</h2>
        </div>

        {topics.length === 0 ? (
          <Card className="rounded-2xl">
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              Loading topics...
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {topics.map((t) => {
              const hasStarted = sessions.some(s => s.topic === t.name);
              const status = masteryStatus(t.mastery, hasStarted);
              const muted = t.mastery < 30 && !hasStarted;
              return (
                <div key={t.id}>
                  <Card
                    className={`rounded-2xl transition-all hover:shadow-md hover:scale-[1.02] ${
                      muted ? "opacity-80" : ""
                    }`}
                  >
                    <CardContent className="p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="font-medium">{t.name}</p>
                        <Badge variant={t.mastery >= 80 ? "default" : "secondary"}>
                          {t.mastery}%
                        </Badge>
                      </div>
                      <Progress value={animate ? t.mastery : 0} className="h-2" />
                      <p className="text-xs text-muted-foreground">{status.label}</p>
                    </CardContent>
                  </Card>
                </div>
              );
            })}
          </div>
        )}
      </motion.div>

      {/* Section 3 — Session History */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.1 }}
        className="space-y-4"
      >
        <h2 className="text-xl font-semibold">Session History</h2>

        {sessions.length === 0 ? (
          <Card className="rounded-2xl">
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              No sessions yet. Start learning to see your history here!
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Card key={s.id} className="rounded-2xl">
                <Accordion type="single" collapsible>
                  <AccordionItem value={s.id} className="border-b-0">
                    <AccordionTrigger className="px-5 py-4 hover:no-underline">
                      <div className="flex flex-1 items-center justify-between gap-4 pr-3">
                        <div className="text-left">
                          <p className="font-medium">{s.topic}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {s.date} · {s.duration}
                          </p>
                        </div>
                        <Badge variant={s.result === "Improved" ? "default" : "secondary"}>
                          {s.result}
                        </Badge>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-5">
                      <div className="space-y-3 text-sm">
                        <div>
                          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Summary</p>
                          <p>{s.summary}</p>
                        </div>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              </Card>
            ))}
          </div>
        )}
      </motion.div>

      {/* Section 4 — Focus Areas */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.15 }}
        className="space-y-4"
      >
        <h2 className="text-xl font-semibold">Focus Areas</h2>

        <Card className="rounded-2xl">
          <CardContent className="p-5 space-y-4">
            {focusAreas.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {overallMastery === 0 ? "Start learning to see focus areas!" : "Great job — no weak areas right now!"}
              </p>
            ) : (
              focusAreas.map((t) => (
                <div key={t.id} className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                  <div className="flex-1 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">{t.name}</p>
                      <p className="text-xs text-muted-foreground">{t.mastery}%</p>
                    </div>
                    <Progress value={animate ? t.mastery : 0} className="h-2" />
                  </div>
                  <Button asChild size="sm" variant="outline">
                    <Link to={`/session/${t.id}`}>Practice Again</Link>
                  </Button>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Section 5 — Growth Chart */}
      {growthData.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.2 }}
          className="space-y-4"
        >
          <h2 className="text-xl font-semibold">Your Growth</h2>

          <Card className="rounded-2xl">
            <CardHeader className="pb-0">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Mastery over recent sessions
              </CardTitle>
            </CardHeader>
            <CardContent className="p-5">
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={growthData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="session" stroke="hsl(var(--muted-foreground))" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} tickLine={false} axisLine={false} domain={[0, 100]} />
                    <Tooltip contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                    <Line type="monotone" dataKey="mastery" stroke="hsl(var(--primary))" strokeWidth={2.5} dot={{ r: 3, fill: "hsl(var(--primary))" }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </div>
  );
};

export default ProgressPage;
