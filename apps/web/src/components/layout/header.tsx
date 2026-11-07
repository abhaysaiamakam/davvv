"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { Terminal, Shield, RefreshCw } from "lucide-react";
import { useApiHealth } from "@/hooks/use-api-health";

const ROUTE_TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": {
    title: "System Overview",
    subtitle: "Agricultural Dataset Intelligence Platform Foundation",
  },
  "/datasets": {
    title: "Dataset Explorer",
    subtitle: "Curated Benchmarks & Ingestion Registry",
  },
  "/quality": {
    title: "Data Quality Lab",
    subtitle: "Corrupt File, Duplicate & Perceptual Hash Verification",
  },
  "/eda": {
    title: "EDA & Visualizations",
    subtitle: "Class Distributions, Pixel Geometries & Aspect Ratios",
  },
  "/comparison": {
    title: "Dataset Comparison",
    subtitle: "Cross-Dataset Benchmarking & Domain Divergence",
  },
  "/insights": {
    title: "Findings & Insights",
    subtitle: "Dataset Critique, Anomalies & Quality Findings",
  },
  "/reports": {
    title: "Methodology & Reports",
    subtitle: "NIErnaya Phase 2 Evidence & Verification Artifacts",
  },
  "/analyze": {
    title: "Evaluator Dataset Upload",
    subtitle: "Upload Engine Staging & Pipeline Readiness",
  },
};

export function Header() {
  const pathname = usePathname();
  const { status, data, refresh } = useApiHealth();
  const currentRoute = ROUTE_TITLES[pathname] || {
    title: "CropLens Platform",
    subtitle: "Interactive Agricultural Dataset Intelligence",
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-croplens-border bg-croplens-sidebar/90 px-6 backdrop-blur-md">
      {/* Route Title */}
      <div>
        <h1 className="text-sm font-semibold tracking-tight text-zinc-100">
          {currentRoute.title}
        </h1>
        <p className="text-[11px] text-zinc-400">{currentRoute.subtitle}</p>
      </div>

      {/* Header Actions & API Status */}
      <div className="flex items-center gap-3">
        {/* Curated Anchor Badge */}
        <div className="hidden sm:flex items-center gap-1.5 rounded-lg border border-croplens-border bg-croplens-card px-2.5 py-1 text-[11px] text-zinc-300">
          <Shield className="h-3.5 w-3.5 text-emerald-400" />
          <span>Anchor:</span>
          <span className="font-medium text-emerald-300">ICAR Rice & Maize</span>
        </div>

        {/* API Connection Indicator */}
        <button
          onClick={refresh}
          title="Click to re-verify backend connectivity"
          className="flex items-center gap-2 rounded-lg border border-croplens-border bg-croplens-card px-3 py-1.5 text-xs transition-colors hover:border-emerald-700/50"
        >
          <span
            className={`h-2 w-2 rounded-full ${
              status === "connected"
                ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]"
                : status === "checking"
                ? "bg-amber-400 animate-pulse"
                : "bg-red-400"
            }`}
          />
          <span className="text-[11px] font-medium text-zinc-300">
            {status === "connected"
              ? `FastAPI ${data?.version || "Online"}`
              : status === "checking"
              ? "Checking API..."
              : "Backend Offline"}
          </span>
          <RefreshCw className="h-3 w-3 text-zinc-400 hover:text-zinc-200" />
        </button>

        {/* Swagger / OpenAPI link */}
        <a
          href="http://127.0.0.1:8000/api/v1/docs"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 rounded-lg border border-croplens-border bg-croplens-card px-2.5 py-1.5 text-[11px] font-medium text-zinc-300 hover:bg-croplens-card-hover hover:text-white transition-colors"
        >
          <Terminal className="h-3.5 w-3.5 text-emerald-400" />
          <span className="hidden md:inline">API Docs</span>
        </a>
      </div>
    </header>
  );
}

