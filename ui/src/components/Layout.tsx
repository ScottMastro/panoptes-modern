import { Link, NavLink, Outlet } from "react-router-dom";
import { Activity, Info } from "lucide-react";
import { cn } from "@/lib/utils";

const navItem = "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition";

export function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r bg-card/40 flex flex-col">
        <div className="p-4 border-b">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <Activity className="h-5 w-5" />
            panoptes
          </Link>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          <NavLink to="/workflows"
            className={({ isActive }) => cn(navItem, isActive && "bg-accent text-foreground")}>
            <Activity className="h-4 w-4" />
            Workflows
          </NavLink>
          <NavLink to="/about"
            className={({ isActive }) => cn(navItem, isActive && "bg-accent text-foreground")}>
            <Info className="h-4 w-4" />
            About
          </NavLink>
        </nav>
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
