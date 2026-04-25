import { TooltipProvider } from "@/components/ui/tooltip"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import ProgressPage from "./pages/ProgressPage";
import Session from "./pages/Session";
import AppShell from "./components/layout/AppShell";
import NotFound from "./pages/NotFound";
import { Toaster } from "@/components/ui/sonner";


function App() {
  return (
    <TooltipProvider>
      <Toaster />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/progress" element={<ProgressPage />} />
          </Route>
          <Route path="/session/:sessionId" element={<Session />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  )
}

export default App