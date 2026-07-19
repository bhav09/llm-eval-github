import { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export function StatCard({
  title,
  value,
  hint,
  icon: Icon,
  accent = "brand",
}: {
  title: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  accent?: "brand" | "emerald" | "amber" | "slate";
}) {
  const accentMap = {
    brand: "bg-[var(--color-brand-muted)] text-[var(--color-brand)] border-blue-500/10",
    emerald: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/15",
    amber: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/15",
    slate: "bg-[var(--color-hover)] text-[var(--color-muted)] border-[var(--color-border)]",
  };

  const leftBorderMap = {
    brand: "border-l-[3px] border-l-[var(--color-brand)]",
    emerald: "border-l-[3px] border-l-emerald-500",
    amber: "border-l-[3px] border-l-amber-500",
    slate: "border-l-[3px] border-l-[var(--color-muted)]",
  };

  return (
    <Card className={cn("overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:shadow-md", leftBorderMap[accent])}>
      <CardContent className="pt-5 px-5 pb-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wider">{title}</p>
            <p className="mt-2 text-2xl font-extrabold tracking-tight text-[var(--color-foreground)]">{value}</p>
            {hint ? <p className="mt-1 text-xs text-[var(--color-muted)]/80 leading-normal">{hint}</p> : null}
          </div>
          <div className={cn("rounded-xl p-2.5 border shadow-sm", accentMap[accent])}>
            <Icon size={18} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
