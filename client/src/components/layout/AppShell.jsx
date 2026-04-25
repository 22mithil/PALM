import { NavLink, Outlet, useLocation, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Home as HomeIcon, Flame } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { usePalmStore } from "@/store/usePalmStore";

const navItems = [{ to: "/dashboard", label: "Home", icon: HomeIcon, end: true }];

const AppShell = () => {
  const { learnerName, streak, xp, onboarded } = usePalmStore();
  const location = useLocation();

  if (!onboarded) return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
          <NavLink to="/dashboard" className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-xl bg-primary text-primary-foreground grid place-items-center font-bold">
              P
            </div>
            <div className="leading-tight">
              <p className="font-semibold tracking-tight">PALM</p>
              <p className="text-[11px] text-muted-foreground -mt-0.5">Learning Mentor</p>
            </div>
          </NavLink>

          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "px-3 py-2 rounded-md text-sm font-medium transition-colors",
                    "text-muted-foreground hover:text-foreground hover:bg-accent",
                    isActive && "text-foreground bg-accent"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="gap-1">
              <Flame className="h-3.5 w-3.5" /> {streak}
            </Badge>
            <Badge variant="outline" className="hidden sm:inline-flex">
              {xp} XP
            </Badge>
            <Avatar className="h-9 w-9">
              <AvatarFallback>{learnerName[0]?.toUpperCase() || "P"}</AvatarFallback>
            </Avatar>
          </div>
        </div>
      </header>

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
