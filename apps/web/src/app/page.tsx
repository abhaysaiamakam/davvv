"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Layers,
  Database,
  ShieldCheck,
  BarChart2,
  GitCompare,
  UploadCloud,
  FileCheck2,
  Server,
  ArrowRight,
  HardDrive,
  Cpu,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { DatasetListResponse, HealthResponse } from "@croplens/shared-types";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";

export default function OverviewPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [datasetsData, setDatasetsData] = useState<DatasetListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, d] = await Promise.all([
        apiClient.getHealth().catch(() => null),
        apiClient.getDatasets().catch(() => null),
      ]);
      setHealth(h);
      setDatasetsData(d);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load platform data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <PageContainer
      title="Platform Overview"
      description="CropLens is an agricultural dataset intelligence platform for NIErnaya Phase 2. This milestone establishes the monorepo foundation, typed contracts, local storage abstraction, and Next.js/FastAPI connectivity."
      badge="Milestone 1: Project Foundation"
    >
      {error && (
        <ErrorState
          title="Connectivity Alert"
          message={error}
          onRetry={loadData}
          className="mb-4"
        />
      )}

      {/* Top Architecture Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <DashboardCard
          title="API Engine Status"
          icon={<Server className="h-4 w-4" />}
          badge={{
            text: health ? "Connected" : "Offline / Mock",
            variant: health ? "emerald" : "amber",
          }}
          description="FastAPI application factory with versioned routing"
        >
          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-croplens-border-subtle">
              <span className="text-zinc-400">Application:</span>
              <span className="font-mono text-zinc-200">{health?.app_name || "CropLens API"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-croplens-border-subtle">
              <span className="text-zinc-400">API Version:</span>
              <span className="font-mono text-zinc-200">{health?.version || "0.1.0"}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-zinc-400">Environment:</span>
              <span className="font-mono text-emerald-400 uppercase">{health?.environment || "Development"}</span>
            </div>
          </div>
        </DashboardCard>

        <DashboardCard
          title="Storage Abstraction"
          icon={<HardDrive className="h-4 w-4" />}
          badge={{ text: "Local Filesystem", variant: "default" }}
          description="Sanitized storage provider isolated from client exposure"
        >
          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-croplens-border-subtle">
              <span className="text-zinc-400">Storage Backend:</span>
              <span className="text-zinc-200">LocalStorageBackend</span>
            </div>
            <div className="flex justify-between py-1 border-b border-croplens-border-subtle">
              <span className="text-zinc-400">Directories:</span>
              <span className="font-mono text-zinc-200">uploads / extract / results</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-zinc-400">Path Guard:</span>
              <span className="text-emerald-400">Traversal Protected</span>
            </div>
          </div>
        </DashboardCard>

        <DashboardCard
          title="Analysis Layer Prep"
          icon={<Cpu className="h-4 w-4" />}
          badge={{ text: "M2 Ready", variant: "neutral" }}
          description="Python analysis engine interfaces reserved for M2"
        >
          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-croplens-border-subtle">
              <span className="text-zinc-400">Core Engines:</span>
              <span className="text-zinc-200">Pandas, NumPy, Pillow</span>
            </div>
            <div className="flex justify-between py-1 border-b border-croplens-border-subtle">
              <span className="text-zinc-400">Deduplication:</span>
              <span className="text-zinc-200">SHA-256 + Perceptual Hash</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-zinc-400">Shared Pipeline:</span>
              <span className="text-emerald-400">Curated & Evaluator Uploads</span>
            </div>
          </div>
        </DashboardCard>
      </div>

      {/* Primary Dataset & Registered Catalog Overview */}
      <DashboardCard
        title="Agricultural Dataset Registry"
        icon={<Database className="h-4 w-4" />}
        badge={{ text: "Curated Benchmarks", variant: "emerald" }}
        description="Initial primary dataset is the ICAR Rice & Maize dataset, complemented by 6 supplementary agricultural benchmarks."
        headerAction={
          <Link
            href="/datasets"
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-900/50 transition-colors"
          >
            <span>Open Explorer</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        }
      >
        {loading ? (
          <LoadingState label="Querying FastAPI dataset catalog..." rows={3} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-croplens-border-subtle text-zinc-400">
                  <th className="pb-2.5 font-medium">Dataset Name</th>
                  <th className="pb-2.5 font-medium">Source / Role</th>
                  <th className="pb-2.5 font-medium">Target Crops</th>
                  <th className="pb-2.5 font-medium">Status</th>
                  <th className="pb-2.5 font-medium text-right">Metrics Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-croplens-border-subtle/50">
                {(datasetsData?.items || []).map((ds) => (
                  <tr key={ds.id} className="hover:bg-croplens-card-hover/40 transition-colors">
                    <td className="py-2.5 font-medium text-zinc-200">
                      <div className="flex items-center gap-2">
                        {ds.id === "icar-rice-maize" && (
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        )}
                        <span>{ds.name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 text-zinc-400">
                      {ds.id === "icar-rice-maize" ? (
                        <span className="rounded bg-emerald-950/80 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-800/60">
                          Primary Anchor
                        </span>
                      ) : (
                        <span className="rounded bg-zinc-800/60 px-1.5 py-0.5 text-[10px] text-zinc-400 border border-zinc-700/50">
                          Supplementary
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-zinc-300">{ds.crops.join(", ")}</td>
                    <td className="py-2.5">
                      <span className="font-mono text-[11px] text-emerald-400">
                        {ds.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-mono text-[11px] text-zinc-400">
                      Pending M2 Ingestion
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3.5 flex items-center justify-between text-[11px] text-zinc-400 border-t border-croplens-border-subtle pt-2.5">
              <span>Note: Quantitative counts remain uncalculated in M1 to preserve analytical integrity.</span>
              <span className="font-mono text-zinc-400">{datasetsData?.total || 0} datasets registered</span>
            </div>
          </div>
        )}
      </DashboardCard>

      {/* Feature Modules Quick Access */}
      <div>
        <h3 className="text-sm font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Layers className="h-4 w-4 text-emerald-400" />
          <span>Platform Modules Navigation</span>
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            {
              title: "Data Quality Lab",
              href: "/quality",
              icon: ShieldCheck,
              desc: "Corrupt file verification, SHA-256 duplicate detection, and perceptual near-duplicate hashing.",
            },
            {
              title: "EDA & Visualizations",
              href: "/eda",
              icon: BarChart2,
              desc: "Class imbalance inspection, resolution distribution, aspect ratio analysis, and color histograms.",
            },
            {
              title: "Dataset Comparison",
              href: "/comparison",
              icon: GitCompare,
              desc: "Benchmark ICAR Rice & Maize against Paddy Doctor, PlantVillage, and field-condition datasets.",
            },
            {
              title: "Findings & Insights",
              href: "/insights",
              icon: FileCheck2,
              desc: "Curated dataset critique, field condition anomalies, and label noise documentation.",
            },
            {
              title: "Methodology & Reports",
              href: "/reports",
              icon: FileCheck2,
              desc: "Formal evaluation reports and evidence artifacts for NIErnaya Phase 2 evaluation.",
            },
            {
              title: "Evaluator Upload Portal",
              href: "/analyze",
              icon: UploadCloud,
              desc: "Self-service upload staging for evaluator-provided agricultural datasets using shared pipeline.",
            },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="group rounded-xl border border-croplens-border bg-croplens-card p-4 transition-all duration-150 hover:border-emerald-700/60 hover:bg-croplens-card-hover"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-800/40 bg-emerald-950/40 text-emerald-400">
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-xs font-semibold text-zinc-100 group-hover:text-emerald-300 transition-colors">
                      {item.title}
                    </span>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-zinc-400 group-hover:text-emerald-300 group-hover:translate-x-0.5 transition-all" />
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed">{item.desc}</p>
              </Link>
            );
          })}
        </div>
      </div>
    </PageContainer>
  );
}

