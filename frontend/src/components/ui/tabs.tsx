import * as Tabs from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export function TabsRoot({ className, ...props }: Tabs.TabsProps) {
  return <Tabs.Root className={cn("space-y-4", className)} {...props} />;
}

export function TabsList({ className, ...props }: Tabs.TabsListProps) {
  return (
    <Tabs.List
      className={cn(
        "inline-flex h-11 items-center rounded-full bg-[var(--color-surface-muted)] dark:bg-[var(--color-input-bg)] p-1 text-[var(--color-muted)] border border-[var(--color-border)] shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: Tabs.TabsTriggerProps) {
  return (
    <Tabs.Trigger
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-full px-5 py-1.5 text-xs font-bold uppercase tracking-wider transition-all duration-200 cursor-pointer",
        "data-[state=active]:bg-gradient-to-r data-[state=active]:from-[var(--color-brand)] data-[state=active]:to-[#4f46e5] data-[state=active]:text-white data-[state=active]:shadow-md data-[state=active]:shadow-blue-500/10",
        "data-[state=inactive]:hover:text-[var(--color-foreground)]",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: Tabs.TabsContentProps) {
  return <Tabs.Content className={cn("focus:outline-none", className)} {...props} />;
}
