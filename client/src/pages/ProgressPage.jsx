import { useEffect, useState } from "react";
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

const topics = [
  { id: "addition", name: "Addition", mastery: 92 },
  { id: "subtraction", name: "Subtraction", mastery: 85 },
  { id: "multiplication", name: "Multiplication", mastery: 70 },
  { id: "division", name: "Division", mastery: 48 },
  { id: "fractions", name: "Fractions", mastery: 35 },
  { id: "decimals", name: "Decimals", mastery: 100 },
  { id: "geometry", name: "Geometry", mastery: 12 },
  { id: "measurement", name: "Measurement", mastery: 0 },
  { id: "wordproblems", name: "Word Problems", mastery: 22 },
];

const sessions = [
  {
    id: "s1", topic: "Fractions", date: "Apr 22, 2026", duration: "18 min", result: "Improved",
    summary: "Worked on identifying equivalent fractions with visual models.",
    learnings: ["Recognized halves and quarters", "Compared fractions with same denominator"],
    mistakes: ["Confused 1/3 vs 1/4 in two problems"],
  },
  {
    id: "s2", topic: "Multiplication", date: "Apr 21, 2026", duration: "22 min", result: "Improved",
    summary: "Practiced 3× and 4× tables with mixed problems.",
    learnings: ["Mastered 3× table", "Used skip counting strategy"],
    mistakes: ["Slipped on 4×7"],
  },
  {
    id: "s3", topic: "Geometry", date: "Apr 20, 2026", duration: "14 min", result: "Needs Practice",
    summary: "Introduction to 2D shapes and their properties.",
    learnings: ["Named common polygons"],
    mistakes: ["Mixed up rhombus and parallelogram"],
  },
  {
    id: "s4", topic: "Division", date: "Apr 19, 2026", duration: "20 min", result: "Needs Practice",
    summary: "Long division with single-digit divisors.",
    learnings: ["Understood remainder concept"],
    mistakes: ["Skipped a step in 84÷6"],
  },
];

const growthData = [
  { session: "S1", mastery: 32 },
  { session: "S2", mastery: 41 },
  { session: "S3", mastery: 48 },
  { session: "S4", mastery: 55 },
  { session: "S5", mastery: 60 },
  { session: "S6", mastery: 67 },
  { session: "S7", mastery: 74 },
];

const masteryStatus = (m) => {
  if (m >= 80) return { label: "Strong", variant: "default" };
  if (m >= 50) return { label: "Progressing", variant: "secondary" };
  if (m > 0) return { label: "Needs Practice", variant: "outline" };
  return { label: "Just Started", variant: "outline" };
};

const ProgressPage = () => {
  const { learnerName } = usePalmStore();
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setAnimate(true), 150);
    return () => clearTimeout(t);
  }, []);

  const totalSessions = 24;
  const totalTime = "6h 42m";
  const accuracy = 78;
  const overallMastery = Math.round(
    topics.reduce((a, t) => a + t.mastery, 0) / topics.length,
  );

  const focusAreas = topics.filter((t) => t.mastery < 50).slice(0, 4);

  const stats = [
    { label: "Total Sessions", value: totalSessions, icon: Activity },
    { label: "Total Time Spent", value: totalTime, icon: Clock },
    { label: "Average Accuracy", value: `${accuracy}%`, icon: Target },
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

      {/* Section 2 — Mastery Heatmap */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.05 }}
        className="space-y-4"
      >
        <div className="flex items-end justify-between">
          <h2 className="text-xl font-semibold">Topic Mastery</h2>
          <p className="text-xs text-muted-foreground">Click a topic to start a session</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {topics.map((t) => {
            const status = masteryStatus(t.mastery);
            const muted = t.mastery < 30;
            return (
              <Link key={t.id} to={`/session/${t.id}`}>
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
              </Link>
            );
          })}
        </div>
      </motion.div>

      {/* Section 3 — Session History */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.1 }}
        className="space-y-4"
      >
        <h2 className="text-xl font-semibold">Session History</h2>

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
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Key Learnings</p>
                        <ul className="list-disc list-inside space-y-0.5">
                          {s.learnings.map((l) => (<li key={l}>{l}</li>))}
                        </ul>
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Mistakes</p>
                        <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                          {s.mistakes.map((m) => (<li key={m}>{m}</li>))}
                        </ul>
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </Card>
          ))}
        </div>
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
                Great job — no weak areas right now!
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

      {/* Section 5 — Improvement Trend */}
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
    </div>
  );
};

export default ProgressPage;
