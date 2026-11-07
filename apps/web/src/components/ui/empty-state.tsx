import React from "react";
import { FolderX } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-croplens-border bg-croplens-card/40 px-6 py-12 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-croplens-border bg-croplens-card text-emerald-400/80 mb-3.5 shadow-inner">
        {icon || <FolderX className="h-6 w-6" />}
      </div>
      <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
      <p className="mt-1.5 max-w-sm text-xs text-zinc-400 leading-relaxed">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 rounded-lg border border-emerald-700/60 bg-emerald-950/40 px-3.5 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-900/60 hover:text-emerald-100 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

