import { Outlet, useLocation, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { usePalmStore } from "@/store/usePalmStore";
import Navbar from "./Navbar";

const AppShell = () => {
  const { onboarded } = usePalmStore();
  const location = useLocation();

  if (!onboarded) return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-muted/30">
      <Navbar />

      <main className="max-w-6xl mx-auto px-4 py-6 pb-10">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        >
          <Outlet />
        </motion.div>
      </main>
    </div>
  );
};

export default AppShell;
