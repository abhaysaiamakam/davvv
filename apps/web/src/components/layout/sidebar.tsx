"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Database,
  ShieldCheck,
  BarChart3,
  GitCompare,
  Lightbulb,
  FileText,
  UploadCloud,
  Sprout,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  {
    name: "Overview",
    href: "/",
    icon: LayoutDashboard,
    badge: null,
  },
  {
    name: "Dataset Explorer",
    href: "/datasets",
    icon: Database,
    badge: "ICAR Ref",
  },
  {
    name: "Data Quality Lab",
    href: "/quality",
    icon: ShieldCheck,
    badge: null,
  },
  {
    name: "EDA & Visualizations",
    href: "/eda",
    icon: BarChart3,
    badge: null,
  },
  {
    name: "Dataset Comparison",
    href: "/comparison",
    icon: GitCompare,
    badge: null,
  },
  {
    name: "Findings & Insights",
    href: "/insights",
    icon: Lightbulb,
    badge: null,
  },
  {
    name: "Methodology & Reports",
    href: "/reports",
    icon: FileText,
    badge: null,
  },
  {
    name: "Evaluator Upload",
    href: "/analyze",
    icon: UploadCloud,
    badge: "M2 Prep",
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-croplens-border bg-croplens-sidebar transition-all duration-200">
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-3 border-b border-croplens-border px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-950/60 text-emerald-400 shadow-sm">
          <Sprout className="h-5 w-5" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold tracking-tight text-white">CropLens</span>
            <span className="rounded bg-emerald-900/50 px-1.5 py-0.2 text-[10px] font-semibold uppercase tracking-wider text-emerald-300 border border-emerald-800/60">
              M1
            </span>
          </div>
          <p className="text-[10px] text-zinc-400">Agricultural Dataset Intelligence</p>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
          Core Workflows
        </div>
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center justify-between rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150",
                  isActive
                    ? "border border-emerald-700/50 bg-emerald-950/40 text-emerald-300 font-semibold"
                    : "text-zinc-400 hover:border hover:border-croplens-border hover:bg-croplens-card hover:text-zinc-200"
                )}
              >
                <div className="flex items-center gap-2.5">
                  <Icon
                    className={cn(
                      "h-4 w-4 transition-colors",
                      isActive
                        ? "text-emerald-400"
                        : "text-zinc-400 group-hover:text-zinc-200"
                    )}
                  />
                  <span>{item.name}</span>
                </div>
                {item.badge && (
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-medium border",
                      isActive
                        ? "bg-emerald-900/60 border-emerald-600/50 text-emerald-200"
                        : "bg-zinc-800/60 border-zinc-700/50 text-zinc-400"
                    )}
                  >
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Platform Architecture Status Badge */}
      <div className="border-t border-croplens-border p-4">
        <div className="rounded-lg border border-croplens-border bg-croplens-card/80 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-300">Phase 2 Target</span>
            <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-400">
              <Activity className="h-3 w-3" />
              NIErnaya
            </span>
          </div>
          <div className="mt-2 text-[10px] text-zinc-400 leading-snug">
            ICAR Rice & Maize primary anchor with shared Python engine architecture.
          </div>
        </div>
      </div>
    </aside>
  );
}

