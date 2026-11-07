import React from "react";
import {
  BarChart3,
  PieChart,
  ScatterChart,
  Palette,
  ActivitySquare,
  Sparkles,
} from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function EDAPage() {
  const visualizationPlans = [
    {
      title: "Class Distribution & Imbalance",
      icon: BarChart3,
      desc: "Interactive distribution charts showing sample balance across rice and maize disease classes, highlighting severe underrepresented foliar pathogen classes.",
      engine: "Apache ECharts Bar / Treemap",
    },
    {
      title: "Resolution & Aspect Ratio Scatter",
      icon: ScatterChart,
      desc: "2D scatter plot mapping pixel width vs height, with kernel density contours to identify multi-camera clustering and resolution outliers.",
      engine: "Apache ECharts Scatter + Density Contours",
    },
    {
      title: "Color Space & Foliar Hue Profiling",
      icon: Palette,
      desc: "RGB, HSV, and LAB color space distributions to evaluate lighting variability, shadow intensity, and background green/brown foliar hue separation.",
      engine: "NumPy / OpenCV Histogram Engine",
    },
    {
      title: "Foliar Lesion Spatial Distribution",
      icon: ActivitySquare,
      desc: "Bounding box spatial density maps for annotated disease spots, revealing photographer center-bias and edge-clipping tendencies.",
      engine: "Apache ECharts Heatmap Matrix",
    },
  ];

  return (
    <PageContainer
      title="EDA & Visualizations"
      description="Exploratory Data Analysis workbench for agricultural disease datasets. Visualizations will be powered by Apache ECharts once the Python data engine computes feature distributions."
      badge="Visualization Workbench"
    >
      <div className="rounded-xl border border-croplens-border bg-croplens-card p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-emerald-800/40 bg-emerald-950/40 text-emerald-400">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">
              Data Science Visualization Foundation
            </h3>
            <p className="mt-1 text-xs text-zinc-300 leading-relaxed">
              In accordance with Milestone 1 specifications, charts with fabricated analytical data are strictly omitted. The visualization engine is prepared to ingest verified Pandas/NumPy distributions computed by the backend service.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {visualizationPlans.map((plan) => {
          const Icon = plan.icon;
          return (
            <DashboardCard
              key={plan.title}
              title={plan.title}
              icon={<Icon className="h-4 w-4" />}
              badge={{ text: "ECharts Specification", variant: "default" }}
            >
              <div className="space-y-3">
                <p className="text-xs text-zinc-300 leading-relaxed">{plan.desc}</p>
                <div className="flex items-center justify-between rounded border border-croplens-border-subtle bg-zinc-950/40 px-3 py-2 text-[11px]">
                  <span className="text-zinc-400">Chart Technology:</span>
                  <span className="font-mono text-emerald-300">{plan.engine}</span>
                </div>
              </div>
            </DashboardCard>
          );
        })}
      </div>

      {/* Primary ICAR Target Focus */}
      <DashboardCard
        title="Primary Analytical Target: ICAR Rice & Maize"
        icon={<PieChart className="h-4 w-4" />}
        badge={{ text: "Primary Benchmark", variant: "emerald" }}
      >
        <p className="text-xs text-zinc-300 leading-relaxed">
          The exploratory analysis workbench will provide in-depth comparative profiling between ICAR Rice (Bacterial Blight, Brown Spot, Leaf Blast) and ICAR Maize (Maydis Leaf Blight, Turcicum Leaf Blight, Banded Leaf and Sheath Blight) against laboratory benchmarks like PlantVillage.
        </p>
      </DashboardCard>
    </PageContainer>
  );
}

