import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  message?: string;
  errorCode?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Connection or Retrieval Error",
  message = "Failed to communicate with the CropLens API service.",
  errorCode,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-red-900/40 bg-red-950/20 p-5 text-red-200",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 text-red-400 shrink-0" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-red-200">{title}</h4>
            {errorCode && (
              <span className="rounded bg-red-950/80 px-1.5 py-0.5 font-mono text-[10px] text-red-300 border border-red-800/60">
                {errorCode}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-red-300/80 leading-relaxed">{message}</p>

          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3.5 inline-flex items-center gap-1.5 rounded-lg border border-red-800/60 bg-red-900/30 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-900/50 hover:text-white transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry Connection
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

