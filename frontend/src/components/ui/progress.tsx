import * as Progress from "@radix-ui/react-progress";
import { cn } from "@/lib/utils";

export function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <Progress.Root
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-[var(--color-hover)]", className)}
      value={value}
    >
      <Progress.Indicator
        className="h-full w-full flex-1 rounded-full bg-[var(--color-brand)] transition-transform duration-300"
        style={{ transform: `translateX(-${100 - value}%)` }}
      />
    </Progress.Root>
  );
}
