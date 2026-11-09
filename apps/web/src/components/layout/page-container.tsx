import React from "react";
import { cn } from "@/lib/utils";

interface PageContainerProps {
  title?: string;
  description?: string;
  badge?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function PageContainer({
  title,
  description,
  badge,
  actions,
  children,
  className,
}: PageContainerProps) {
  return (
    <div className={cn("mx-auto w-full max-w-[1440px] space-y-6 p-4 sm:p-6 lg:p-8", className)}>
      {(title || description || actions) && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-croplens-border-subtle pb-5">
          <div>
            <div className="flex items-center gap-2.5">
              {title && (
                <h2 className="text-xl font-bold tracking-tight text-zinc-100">{title}</h2>
              )}
              {badge && (
                <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                  {badge}
                </span>
              )}
            </div>
            {description && (
              <p className="mt-1 text-xs text-zinc-400 max-w-3xl leading-relaxed">
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2.5">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

