import React from "react";
import { Lightbulb, AlertTriangle, CheckCircle, FileText, Compass } from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function InsightsPage() {
  const challengeTopics = [
    {
      title: "Co-Infection & Multi-Pathogen Foliage",
      icon: AlertTriangle,
      level: "Methodological Challenge",
      desc: "Agricultural field imagery frequently contains simultaneous symptoms (e.g. Rice Blast alongside Brown Spot on the same leaf blade), causing single-label classifier confusion.",
    },
    {
      title: "Background Greenery & Foliar Contrast",
      icon: Compass,
      level: "Optical Challenge",
      desc: "In field conditions, background healthy canopy vegetation interferes with edge detection and lesion segmentation, unlike clean white or grey laboratory staging.",
    },
    {
      title: "Variable Diurnal Sun Exposure & Wetness",
      icon: Lightbulb,
      level: "Environmental Challenge",
      desc: "Morning dew, specular sunlight reflection on wet leaves, and deep shadow gradients introduce high intra-class variance not captured in lab datasets.",
    },
  ];

  return (
    <PageContainer
      title="Findings & Insights"
      description="Evidence-based agricultural pathology critiques and automated anomaly detection findings for NIErnaya Phase 2 evaluation."
      badge="Dataset Critique"
    >
      <div className="rounded-xl border border-croplens-border bg-croplens-card p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-emerald-800/40 bg-emerald-950/40 text-emerald-400">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">
              Scientific Dataset Critique Framework
            </h3>
            <p className="mt-1 text-xs text-zinc-300 leading-relaxed">
              CropLens bridges the gap between raw agronomic datasets and production AI deployment by cataloging genuine real-world impediments found in foliar vision datasets.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {challengeTopics.map((item) => {
          const Icon = item.icon;
          return (
            <DashboardCard
              key={item.title}
              title={item.title}
              icon={<Icon className="h-4 w-4" />}
              badge={{ text: item.level, variant: "neutral" }}
            >
              <p className="text-xs text-zinc-300 leading-relaxed">{item.desc}</p>
            </DashboardCard>
          );
        })}
      </div>

      <DashboardCard
        title="Live Anomaly Findings Log"
        icon={<CheckCircle className="h-4 w-4" />}
        badge={{ text: "Engine Pipeline Status", variant: "emerald" }}
      >
        <div className="rounded-lg border border-croplens-border-subtle bg-zinc-950/40 p-4 text-xs text-zinc-400">
          <p>
            The automated findings generator is connected to the backend analysis pipeline. As analysis runs are triggered against the ICAR repository in Milestone 2, discovered duplicate pairs, corrupted images, and outlier aspect ratios will appear here as actionable evidence records.
          </p>
        </div>
      </DashboardCard>
    </PageContainer>
  );
}

