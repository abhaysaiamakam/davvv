import React from "react";
import { GitCompare, Layers, Split, Microscope } from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function ComparisonPage() {
  const comparisonAxes = [
    {
      title: "Field vs Laboratory Domain Shift",
      icon: Microscope,
      desc: "Comparing the controlled-environment imagery of PlantVillage against real in-the-wild agricultural field conditions of ICAR and Paddy Doctor.",
    },
    {
      title: "Class Taxonomy & Nomenclature Alignment",
      icon: Split,
      desc: "Cross-mapping pathogen classifications across datasets (e.g. Rice Blast vs Pyricularia oryzae, Brown Spot vs Bipolaris oryzae) to identify semantic labeling divergence.",
    },
    {
      title: "Resolution & Optical Device Uniformity",
      icon: Layers,
      desc: "Evaluating sensor resolution variance across datasets, contrasting high-end DSLR captures with farmer-sourced mobile smartphone captures.",
    },
  ];

  return (
    <PageContainer
      title="Dataset Comparison"
      description="Cross-dataset intelligence comparing ICAR Rice & Maize reference standards with supplementary global and regional datasets."
      badge="Benchmarking Suite"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {comparisonAxes.map((axis) => {
          const Icon = axis.icon;
          return (
            <DashboardCard
              key={axis.title}
              title={axis.title}
              icon={<Icon className="h-4 w-4" />}
              badge={{ text: "Cross-Domain", variant: "default" }}
            >
              <p className="text-xs text-zinc-300 leading-relaxed">{axis.desc}</p>
            </DashboardCard>
          );
        })}
      </div>

      <DashboardCard
        title="Comparative Cohort Matrix (Planned M3 Milestone)"
        icon={<GitCompare className="h-4 w-4" />}
        badge={{ text: "Architecture Staged", variant: "neutral" }}
        description="Dataset pairs queued for comparative domain generalization analysis."
      >
        <div className="overflow-x-auto text-xs">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-croplens-border-subtle text-zinc-400">
                <th className="pb-2.5 font-medium">Primary Reference</th>
                <th className="pb-2.5 font-medium">Comparison Target</th>
                <th className="pb-2.5 font-medium">Comparison Focus</th>
                <th className="pb-2.5 font-medium">Planned Pipeline</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-croplens-border-subtle/50 text-zinc-300">
              <tr className="hover:bg-croplens-card-hover/40">
                <td className="py-2.5 font-medium text-emerald-300">ICAR Rice</td>
                <td className="py-2.5">Paddy Doctor</td>
                <td className="py-2.5 text-zinc-400">Field condition mobile capture vs ICAR field stations</td>
                <td className="py-2.5 font-mono text-[11px] text-zinc-400">pHash + Feature Embeddings</td>
              </tr>
              <tr className="hover:bg-croplens-card-hover/40">
                <td className="py-2.5 font-medium text-emerald-300">ICAR Rice</td>
                <td className="py-2.5">Mendeley Rice</td>
                <td className="py-2.5 text-zinc-400">Laboratory controlled background vs field pathology</td>
                <td className="py-2.5 font-mono text-[11px] text-zinc-400">Color Space + Histogram Shift</td>
              </tr>
              <tr className="hover:bg-croplens-card-hover/40">
                <td className="py-2.5 font-medium text-emerald-300">ICAR Maize</td>
                <td className="py-2.5">PlantVillage Maize</td>
                <td className="py-2.5 text-zinc-400">Leaf blight lesion morphology & leaf segmentation</td>
                <td className="py-2.5 font-mono text-[11px] text-zinc-400">Geometry + Resolution Matrix</td>
              </tr>
            </tbody>
          </table>
        </div>
      </DashboardCard>
    </PageContainer>
  );
}

