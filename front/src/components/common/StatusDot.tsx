import { cn } from "@/utils/cn";

type Props = {
  status: string;
  className?: string;
};

export function StatusDot({ status, className }: Props) {
  const color =
    status === "online"
      ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
      : status === "error"
        ? "bg-red-400"
        : status === "connecting" || status === "reconnecting"
          ? "bg-amber-400 animate-pulse"
          : "bg-[var(--color-text-muted)]";

  return (
    <span
      className={cn("inline-block h-2 w-2 rounded-full", color, className)}
      aria-hidden
    />
  );
}
