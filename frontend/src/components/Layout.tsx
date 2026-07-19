import { Link, Outlet, useLocation } from "react-router-dom";
import { History, Info, Sparkles, Trophy, Landmark } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

export function Layout() {
  const location = useLocation();
  const nav = [
    { to: "/selection", label: "Selection", icon: Trophy },
    { to: "/eval", label: "Eval", icon: Sparkles },
    { to: "/history", label: "History", icon: History },
    { to: "/about", label: "About", icon: Info },
  ];

  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-foreground)] animate-fade-slide">
      <header className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-card)] backdrop-blur-md bg-opacity-70 dark:bg-opacity-60 card-glass">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-8">
            <Link to="/selection" className="flex items-center gap-2 hover:opacity-90 transition-opacity">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-tr from-[var(--color-brand)] to-[#4f46e5] shadow-md shadow-blue-500/10 text-white">
                <Landmark size={14} />
              </div>
              <span className="text-[15px] font-extrabold tracking-tight bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400 bg-clip-text text-transparent">
                Colosseum
              </span>
            </Link>
            <nav className="flex gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-muted)] dark:bg-[var(--color-input-bg)] p-1">
              {nav.map(({ to, label, icon: Icon }) => {
                const isActive = location.pathname === to;
                return (
                  <Link
                    key={to}
                    to={to}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[13px] font-semibold transition-all duration-200 cursor-pointer",
                      isActive
                        ? "bg-gradient-to-r from-[var(--color-brand)] to-[#4f46e5] text-white shadow-sm shadow-blue-500/10 hover:shadow-md"
                        : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                    )}
                  >
                    <Icon size={13} />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <ThemeToggle />
        </div>
      </header>
      <Outlet />
    </div>
  );
}
