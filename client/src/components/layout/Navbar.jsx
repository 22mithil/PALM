import { NavLink, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { usePalmStore } from "@/store/usePalmStore";

const Navbar = () => {
  const { learnerName, streak, logout } = usePalmStore();
  const navigate = useNavigate();

  return (
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

        <div className="flex items-center gap-2">
          <Badge variant="outline" className="flex items-center gap-1 text-orange-600 border-orange-200 bg-orange-50/50 font-medium px-2 py-0.5">
            🔥 {streak}
          </Badge>
          <Avatar className="h-9 w-9">
            <AvatarFallback>{learnerName[0]?.toUpperCase() || "P"}</AvatarFallback>
          </Avatar>
          <button
            onClick={() => { logout(); navigate("/", { replace: true }); }}
            className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
