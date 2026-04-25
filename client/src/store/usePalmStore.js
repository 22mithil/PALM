import { create } from "zustand";

export const usePalmStore = create((set) => ({
  onboarded: false,
  learnerName: "",
  grade: 3,
  streak: 7,
  xp: 1240,
  mood: "happy",
  subjects: [
    { id: "math", name: "Math", emoji: "🧮", mastery: 72, lessonsCompleted: 18, totalLessons: 25 },
    { id: "reading", name: "Reading", emoji: "📚", mastery: 84, lessonsCompleted: 21, totalLessons: 25 },
    { id: "science", name: "Science", emoji: "🔬", mastery: 56, lessonsCompleted: 14, totalLessons: 25 },
    { id: "writing", name: "Writing", emoji: "✏️", mastery: 63, lessonsCompleted: 15, totalLessons: 24 },
  ],
  lessons: [
    { id: "l1", subjectId: "math", title: "Multiplying by 3 & 4", description: "Quick patterns and tricks for times tables.", duration: 12, difficulty: "Medium", completed: false },
    { id: "l2", subjectId: "reading", title: "Finding the Main Idea", description: "Spot the most important sentence in a story.", duration: 10, difficulty: "Easy", completed: true },
    { id: "l3", subjectId: "science", title: "States of Matter", description: "Solid, liquid, gas — see how they change.", duration: 15, difficulty: "Medium", completed: false },
    { id: "l4", subjectId: "writing", title: "Strong Sentences", description: "Use vivid words to bring sentences alive.", duration: 8, difficulty: "Easy", completed: false },
    { id: "l5", subjectId: "math", title: "Fractions of Shapes", description: "Halves, thirds, and quarters with pictures.", duration: 14, difficulty: "Hard", completed: false },
    { id: "l6", subjectId: "science", title: "Plant Life Cycle", description: "From seed to flower step by step.", duration: 11, difficulty: "Easy", completed: true },
  ],
  setMood: (mood) => set({ mood }),
  completeLesson: (id) =>
    set((s) => ({
      lessons: s.lessons.map((l) => (l.id === id ? { ...l, completed: true } : l)),
      xp: s.xp + 25,
    })),
  completeOnboarding: (name, grade) =>
    set({ onboarded: true, learnerName: name, grade }),
}));
