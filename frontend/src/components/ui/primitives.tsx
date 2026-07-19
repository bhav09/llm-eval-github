import * as React from "react";
import { cn } from "@/lib/utils";

export function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "outline" | "ghost";
  size?: "default" | "sm";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none hover:scale-[1.02] active:scale-[0.98] cursor-pointer",
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4",
        variant === "default" && "bg-gradient-to-r from-[var(--color-brand)] to-[#4f46e5] text-white shadow-md shadow-blue-500/10 hover:shadow-lg hover:shadow-blue-500/20",
        variant === "secondary" && "bg-[var(--color-hover)] text-[var(--color-foreground)] hover:bg-[var(--color-border)]",
        variant === "outline" &&
          "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-hover)] text-[var(--color-foreground)]",
        variant === "ghost" && "hover:bg-[var(--color-hover)] text-[var(--color-foreground)]",
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] card-glass shadow-sm transition-all duration-300 hover:shadow-md",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 pt-6 pb-2", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold tracking-tight text-[var(--color-foreground)]", className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-[var(--color-muted)]", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 pb-6", className)} {...props} />;
}

export function Badge({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: "default" | "success" | "warning" | "muted" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold border transition-colors",
        variant === "default" && "bg-blue-500/5 text-blue-600 dark:text-blue-400 border-blue-500/15",
        variant === "success" && "bg-emerald-500/5 text-emerald-600 dark:text-emerald-400 border-emerald-500/15",
        variant === "warning" && "bg-amber-500/5 text-amber-600 dark:text-amber-400 border-amber-500/15",
        variant === "muted" && "bg-[var(--color-hover)] text-[var(--color-muted)] border-[var(--color-border)]",
        className,
      )}
      {...props}
    />
  );
}
