import React from "react";
import {
  ShieldCheck,
  FileWarning,
  Copy,
  Hash,
  Maximize2,
  Tag,
  Cpu,
} from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function QualityLabPage() {
  const qualityPillars = [
    {
      id: "corruption",
      title: "1. Corrupt & Unreadable File Detection",
      icon: FileWarning,
      tech: "Pillow Image.verify() & load() decoding",
      description:
        "Validates byte-level decodability and header integrity. Detects zero-byte files, corrupted headers, truncated byte streams, and invalid dimensions.",
      status: "Engine Active (M2.2 Verified)",
    },
    {
      id: "exact-duplicates",
      title: "2. Exact Duplicate Detection",
      icon: Copy,
      tech: "SHA-256 Hash Collisions",
      description:
        "Detects byte-for-byte identical images placed in different split folders or incorrectly replicated across distinct disease classes.",
      status: "Pipeline Staged for M2",
    },
    {
      id: "near-duplicates",
      title: "3. Perceptual Near-Duplicate Hashing",
      icon: Hash,
      tech: "pHash & dHash with Hamming Distance Thresholding",
      description:
        "Flags candidate bursts of identical leaves photographed milliseconds apart, slight crops, rotations, or brightness adjustments.",
      status: "Pipeline Staged for M2",
    },
    {
      id: "geometry",
      title: "4. Resolution & Aspect Ratio Anomalies",
      icon: Maximize2,
      tech: "Dimension Outlier & Distribution Profiling",
      description:
        "Screens for extreme low-resolution thumbnails (e.g. <128px), extreme aspect ratio distortions, and accidental synthetic upscalings.",
      status: "Pipeline Staged for M2",
    },
    {
      id: "label-noise",
      title: "5. Label Consistency & Partition Leakage",
      icon: Tag,
      tech: "Class Hierarchy & Split Partition Validation",
      description:
        "Identifies cross-partition contamination between training and evaluation splits, as well as ambiguous healthy vs diseased class definitions.",
      status: "Pipeline Staged for M2",
    },
  ];

  return (
    <PageContainer
      title="Data Quality Lab"
      description="Quality assurance and dataset integrity workbench. Prepares the validation pipeline for ICAR Rice & Maize and evaluator-uploaded datasets."
      badge="Verification Engine"
    >
      {/* Overview Notice */}
      <div className="rounded-xl border border-croplens-border bg-croplens-card p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-emerald-800/40 bg-emerald-950/40 text-emerald-400">
            <Cpu className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">
              Data Quality Inspection Pipeline Architecture
            </h3>
            <p className="mt-0.5 text-xs text-zinc-400">
              In M1, the storage abstraction and analysis job contracts are established. In M2, the Python analysis engine executes these 5 validation routines.
            </p>
          </div>
        </div>
      </div>

      {/* 5 Quality Pillars Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {qualityPillars.map((pillar) => {
          const Icon = pillar.icon;
          return (
            <DashboardCard
              key={pillar.id}
              title={pillar.title}
              icon={<Icon className="h-4 w-4" />}
              badge={{ text: pillar.status, variant: "neutral" }}
            >
              <div className="space-y-3">
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {pillar.description}
                </p>
                <div className="rounded border border-croplens-border-subtle bg-zinc-950/40 px-3 py-2 text-[11px] flex items-center justify-between">
                  <span className="text-zinc-400">Engine / Technique:</span>
                  <span className="font-mono text-emerald-300">{pillar.tech}</span>
                </div>
              </div>
            </DashboardCard>
          );
        })}

        {/* Evaluation Metric Policy Card */}
        <DashboardCard
          title="Analytical Integrity Guarantee"
          icon={<ShieldCheck className="h-4 w-4" />}
          badge={{ text: "Policy Enforced", variant: "emerald" }}
          description="CropLens avoids synthetic or simulated quality metrics."
        >
          <div className="space-y-2 text-xs text-zinc-300">
            <p>
              To maintain scientific credibility for NIErnaya Phase 2 evaluation, this dashboard does not render mock corruption percentages or synthetic duplicate counts.
            </p>
            <p className="text-zinc-400">
              Verified metrics will be rendered directly from the Python analysis worker output once real dataset files are processed in Milestone 2.
            </p>
          </div>
        </DashboardCard>
      </div>
    </PageContainer>
  );
}

