import { cn } from "@/lib/utils";

interface LoadingStateProps {
  label?: string;
  rows?: number;
  className?: string;
}

export function LoadingState({
  label = "Loading dataset data...",
  rows = 3,
  className,
}: LoadingStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-croplens-border bg-croplens-card/60 p-6 animate-pulse",
        className
      )}
    >
      <div className="flex items-center gap-3">
        <div className="h-4 w-4 rounded-full bg-emerald-600/30 animate-spin border-2 border-emerald-500 border-t-transparent" />
        <span className="text-xs font-medium text-emerald-400/90">{label}</span>
      </div>

      <div className="mt-2 space-y-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="h-4 rounded bg-zinc-800/40"
            style={{ width: `${100 - i * 15}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-xl border border-croplens-border bg-croplens-card p-5 animate-pulse">
      <div className="flex items-center justify-between pb-4">
        <div className="h-5 w-32 rounded bg-zinc-800/60" />
        <div className="h-5 w-16 rounded bg-emerald-950/40" />
      </div>
      <div className="mt-4 space-y-2">
        <div className="h-4 w-full rounded bg-zinc-800/40" />
        <div className="h-4 w-3/4 rounded bg-zinc-800/40" />
      </div>
    </div>
  );
}

