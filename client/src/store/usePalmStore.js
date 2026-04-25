import { create } from "zustand";
import { persist } from "zustand/middleware";

export const usePalmStore = create(
  persist(
    (set) => ({
      // ── Auth state ────────────────────────────────────────────────────
      onboarded: false,
      learnerName: "",
      studentId: null,
      email: "",
      token: null,
      grade: 3,

      // ── Gamification (local) ──────────────────────────────────────────
      streak: 0,
      xp: 0,
      mood: "happy",

      // ── Actions ───────────────────────────────────────────────────────
      login: (student, token) =>
        set({
          onboarded: true,
          learnerName: student.name,
          studentId: student.id,
          email: student.email,
          grade: student.grade,
          token,
        }),

      logout: () =>
        set({
          onboarded: false,
          learnerName: "",
          studentId: null,
          email: "",
          token: null,
          grade: 3,
          streak: 0,
          xp: 0,
        }),

      completeOnboarding: (name, grade) =>
        set({ onboarded: true, learnerName: name, grade }),

      setMood: (mood) => set({ mood }),

      addXp: (amount) => set((s) => ({ xp: s.xp + amount })),
    }),
    {
      name: "palm-storage",
      partialize: (state) => ({
        onboarded: state.onboarded,
        learnerName: state.learnerName,
        studentId: state.studentId,
        email: state.email,
        token: state.token,
        grade: state.grade,
        streak: state.streak,
        xp: state.xp,
      }),
    }
  )
);
