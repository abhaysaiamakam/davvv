"use client";

import React, { useState } from "react";
import {
  UploadCloud,
  FileArchive,
  AlertCircle,
  HardDrive,
  Info,
} from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";

export default function AnalyzeUploadPage() {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  return (
    <PageContainer
      title="Evaluator Dataset Upload"
      description="Upload portal interface for evaluator-provided agricultural datasets. Evaluator datasets are processed through the identical Python analysis engine used for curated benchmarks."
      badge="Shared Engine Staging"
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload Dropzone Form */}
        <div className="lg:col-span-2 space-y-5">
          <DashboardCard
            title="Dataset Archive Upload"
            icon={<UploadCloud className="h-4 w-4" />}
            badge={{ text: "M2 Pipeline Staging", variant: "emerald" }}
            description="Supports compressed ZIP archives containing folder-per-class agricultural image structures."
          >
            <div className="space-y-4">
              {/* Dropzone Area */}
              <div
                className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-croplens-border bg-croplens-bg/60 p-8 text-center transition-colors hover:border-emerald-700/50"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-croplens-border bg-croplens-card text-emerald-400 mb-3 shadow-inner">
                  <FileArchive className="h-6 w-6" />
                </div>
                <h4 className="text-sm font-semibold text-zinc-100">
                  Select or Drag Agricultural Dataset ZIP
                </h4>
                <p className="mt-1 max-w-sm text-xs text-zinc-400 leading-relaxed">
                  Recommended: Structured ZIP with subfolders representing disease classes (e.g. rice_blast/, brown_spot/).
                </p>

                <div className="mt-4 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setSelectedFile("evaluator_sample_batch_01.zip")}
                    className="rounded-lg border border-emerald-700/60 bg-emerald-950/40 px-3.5 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-900/50 transition-colors"
                  >
                    Select Local Archive
                  </button>
                  {selectedFile && (
                    <span className="font-mono text-xs text-zinc-300">
                      Selected: {selectedFile}
                    </span>
                  )}
                </div>
              </div>

              {/* Form Metadata fields */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-zinc-400 mb-1">Dataset Label / Name</label>
                  <input
                    type="text"
                    placeholder="e.g. Evaluator Rice Blind Test 2026"
                    className="w-full rounded-lg border border-croplens-border bg-zinc-950/40 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-600 focus:outline-none"
                    disabled
                  />
                </div>
                <div>
                  <label className="block text-zinc-400 mb-1">Crop Classification</label>
                  <input
                    type="text"
                    placeholder="e.g. Rice, Maize, Foliar Mix"
                    className="w-full rounded-lg border border-croplens-border bg-zinc-950/40 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-600 focus:outline-none"
                    disabled
                  />
                </div>
              </div>

              {/* Action Button */}
              <div className="pt-2">
                <button
                  disabled
                  className="w-full rounded-lg border border-zinc-700/40 bg-zinc-800/40 px-4 py-2 text-xs font-semibold text-zinc-400 cursor-not-allowed opacity-60"
                >
                  Upload & Trigger Analysis Engine (Active in Milestone 2)
                </button>
              </div>
            </div>
          </DashboardCard>
        </div>

        {/* Validation Specifications and Storage Isolation Note */}
        <div className="space-y-5">
          <DashboardCard
            title="Validation Criteria"
            icon={<Info className="h-4 w-4" />}
            badge={{ text: "Rules", variant: "default" }}
          >
            <ul className="space-y-2 text-xs text-zinc-300">
              <li className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                <span>Archive format: Standard ZIP (uncompressed or deflate).</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                <span>Supported file types: .jpg, .jpeg, .png, .webp.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                <span>Zero path traversal tolerance (all paths validated).</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                <span>Extracted safely into isolated temporary directory.</span>
              </li>
            </ul>
          </DashboardCard>

          <DashboardCard
            title="Storage Isolation Guarantee"
            icon={<HardDrive className="h-4 w-4" />}
            badge={{ text: "Protected", variant: "emerald" }}
          >
            <p className="text-xs text-zinc-400 leading-relaxed">
              Storage directories are managed by the <code className="text-emerald-300 font-mono">LocalStorageBackend</code>. File uploads are quarantined in designated upload directories and verified before extraction. Raw server paths are strictly masked from the client.
            </p>
          </DashboardCard>
        </div>
      </div>
    </PageContainer>
  );
}

