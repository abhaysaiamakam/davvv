import React from "react";
import { FileText, Award, Download, CheckSquare, Layers } from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function ReportsPage() {
  const sections = [
    {
      title: "NIErnaya Phase 2 Evaluation Criteria",
      desc: "Methodological alignment with Phase 2 requirements: data cleanliness, deduplication rigor, comparative benchmarking, and evaluator reproducibility.",
    },
    {
      title: "Hash Verification Standard",
      desc: "Formal specification of SHA-256 collision detection and 64-bit DCT perceptual hash Hamming distances for identifying leaked validation pairs.",
    },
    {
      title: "Report Export Architecture",
      desc: "Structured JSON and PDF export schemas designed to serialize analysis results for automated evaluator grading and auditing.",
    },
  ];

  return (
    <PageContainer
      title="Methodology & Reports"
      description="Evaluation methodology, reproducible verification standards, and formal report generation for NIErnaya Phase 2."
      badge="Phase 2 Methodology"
      actions={
        <button
          disabled
          className="flex items-center gap-1.5 rounded-lg border border-croplens-border bg-croplens-card px-3 py-1.5 text-xs font-medium text-zinc-400 opacity-60 cursor-not-allowed"
        >
          <Download className="h-3.5 w-3.5" />
          <span>Export Dossier (M4)</span>
        </button>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {sections.map((sec) => (
          <DashboardCard
            key={sec.title}
            title={sec.title}
            icon={<Award className="h-4 w-4" />}
            badge={{ text: "Formal Standard", variant: "default" }}
          >
            <p className="text-xs text-zinc-300 leading-relaxed">{sec.desc}</p>
          </DashboardCard>
        ))}
      </div>

      <DashboardCard
        title="Verification Rubric & Audit Protocol"
        icon={<CheckSquare className="h-4 w-4" />}
        badge={{ text: "Auditing Checklist", variant: "emerald" }}
      >
        <div className="space-y-3 text-xs text-zinc-300">
          <div className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 font-mono text-[10px]">
              1
            </span>
            <div>
              <strong className="text-zinc-100">Zero Unverified Claims:</strong> All platform claims are backed by verifiable Python hash computations or NumPy matrix operations.
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 font-mono text-[10px]">
              2
            </span>
            <div>
              <strong className="text-zinc-100">Single Shared Engine:</strong> The exact same analysis engine handles curated benchmarks and newly uploaded evaluator datasets.
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 font-mono text-[10px]">
              3
            </span>
            <div>
              <strong className="text-zinc-100">Deterministic Reproducibility:</strong> Hashing algorithms operate deterministically with explicit configuration parameters.
            </div>
          </div>
        </div>
      </DashboardCard>
    </PageContainer>
  );
}

