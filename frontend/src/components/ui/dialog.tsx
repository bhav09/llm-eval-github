import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export function DialogRoot(props: Dialog.DialogProps) {
  return <Dialog.Root {...props} />;
}

export function DialogContent({
  className,
  children,
  ...props
}: Dialog.DialogContentProps) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
      <Dialog.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(640px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl",
          className,
        )}
        {...props}
      >
        {children}
        <Dialog.Close className="absolute right-4 top-4 rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-hover)] hover:text-[var(--color-foreground)]">
          <X size={16} />
        </Dialog.Close>
      </Dialog.Content>
    </Dialog.Portal>
  );
}

export const DialogTitle = Dialog.Title;
export const DialogDescription = Dialog.Description;
export const DialogTrigger = Dialog.Trigger;
export const DialogClose = Dialog.Close;
