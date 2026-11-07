import React from "react";
import { cn } from "@/lib/utils";

interface DashboardCardProps {
  title?: string;
  description?: string;
  badge?: {
    text: string;
    variant?: "default" | "emerald" | "amber" | "neutral";
  };
  icon?: React.ReactNode;
  headerAction?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}

export function DashboardCard({
  title,
  description,
  badge,
  icon,
  headerAction,
  children,
  className,
  contentClassName,
}: DashboardCardProps) {
  const badgeStyles = {
    default: "bg-emerald-950/60 text-emerald-300 border-emerald-800/50",
    emerald: "bg-emerald-900/40 text-emerald-300 border-emerald-700/60",
    amber: "bg-amber-950/60 text-amber-300 border-amber-800/50",
    neutral: "bg-zinc-800/60 text-zinc-300 border-zinc-700/50",
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-croplens-border bg-croplens-card p-5 text-zinc-100 shadow-sm transition-all duration-150 hover:border-emerald-900/60",
        className
      )}
    >
      {(title || icon || headerAction) && (
        <div className="mb-4 flex items-start justify-between gap-4 border-b border-croplens-border-subtle pb-3.5">
          <div className="flex items-center gap-3">
            {icon && (
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-800/40 bg-emerald-950/40 text-emerald-400">
                {icon}
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                {title && <h3 className="text-base font-semibold text-zinc-100 tracking-tight">{title}</h3>}
                {badge && (
                  <span
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-xs font-medium",
                      badgeStyles[badge.variant || "default"]
                    )}
                  >
                    {badge.text}
                  </span>
                )}
              </div>
              {description && (
                <p className="mt-0.5 text-xs text-zinc-400 leading-relaxed">{description}</p>
              )}
            </div>
          </div>
          {headerAction && <div className="shrink-0">{headerAction}</div>}
        </div>
      )}
      <div className={cn("text-sm text-zinc-300", contentClassName)}>{children}</div>
    </div>
  );
}

