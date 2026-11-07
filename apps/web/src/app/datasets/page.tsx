"use client";

import React, { useEffect, useState } from "react";
import {
  Database,
  Filter,
  Tag,
  Calendar,
  CheckCircle2,
  FolderSearch,
  AlertCircle,
  Layers,
  RefreshCw,
  FolderOpen,
  ShieldCheck,
  FileCheck,
  FileWarning,
  Maximize2,
  Palette,
  Copy,
  Files,
  GitCompare,
} from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  DatasetListResponse,
  DatasetMetadata,
  DatasetDiscoveryResult,
  DatasetValidationResult,
  DuplicateAnalysisResult,
} from "@croplens/shared-types";
import { PageContainer } from "@/components/layout/page-container";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { LoadingState } from "@/components/ui/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatDate } from "@/lib/utils";

export default function DatasetsPage() {
  const [datasetsData, setDatasetsData] = useState<DatasetListResponse | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("icar-rice-maize");
  const [filterCrop, setFilterCrop] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Discovery state
  const [discovering, setDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [discoveryResult, setDiscoveryResult] = useState<DatasetDiscoveryResult | null>(null);

  // Validation state
  const [validating, setValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<DatasetValidationResult | null>(null);

  // Exact duplicate detection state
  const [detectingDuplicates, setDetectingDuplicates] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const [duplicateResult, setDuplicateResult] = useState<DuplicateAnalysisResult | null>(null);

  const fetchDatasets = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getDatasets();
      setDatasetsData(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load datasets registry");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  const items = datasetsData?.items || [];
  const selectedDataset: DatasetMetadata | undefined =
    items.find((d) => d.id === selectedDatasetId) || items[0];

  // Sync existing discovery and validation from dataset state
  useEffect(() => {
    if (selectedDataset?.discovery) {
      setDiscoveryResult(selectedDataset.discovery);
    } else {
      setDiscoveryResult(null);
    }
    if (selectedDataset?.validation) {
      setValidationResult(selectedDataset.validation);
    } else {
      setValidationResult(null);
    }
    if (selectedDataset?.duplicates) {
      setDuplicateResult(selectedDataset.duplicates);
    } else {
      setDuplicateResult(null);
    }
    setDiscoveryError(null);
    setValidationError(null);
    setDuplicateError(null);
  }, [selectedDatasetId, selectedDataset]);

  const handleRunDiscovery = async () => {
    if (!selectedDataset) return;
    setDiscovering(true);
    setDiscoveryError(null);
    try {
      const result = await apiClient.discoverDataset(selectedDataset.id);
      setDiscoveryResult(result);
      await fetchDatasets();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDiscoveryError(`[${err.errorCode}] ${err.message}`);
      } else {
        setDiscoveryError(err instanceof Error ? err.message : "Discovery request failed");
      }
    } finally {
      setDiscovering(false);
    }
  };

  const handleRunValidation = async () => {
    if (!selectedDataset) return;
    setValidating(true);
    setValidationError(null);
    try {
      const result = await apiClient.validateDataset(selectedDataset.id);
      setValidationResult(result);
      await fetchDatasets();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setValidationError(`[${err.errorCode}] ${err.message}`);
      } else {
        setValidationError(err instanceof Error ? err.message : "Validation request failed");
      }
    } finally {
      setValidating(false);
    }
  };

  const handleRunDuplicateDetection = async () => {
    if (!selectedDataset) return;
    setDetectingDuplicates(true);
    setDuplicateError(null);
    try {
      const result = await apiClient.detectDuplicates(selectedDataset.id);
      setDuplicateResult(result);
      await fetchDatasets();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDuplicateError(`[${err.errorCode}] ${err.message}`);
      } else {
        setDuplicateError(
          err instanceof Error ? err.message : "Duplicate detection failed"
        );
      }
    } finally {
      setDetectingDuplicates(false);
    }
  };

  const filteredItems = items.filter((d) => {
    if (filterCrop === "all") return true;
    return d.crops.some((c) => c.toLowerCase().includes(filterCrop.toLowerCase()));
  });

  const isDiscovered =
    selectedDataset?.status === "discovered" ||
    selectedDataset?.status === "validating" ||
    selectedDataset?.status === "validated" ||
    !!discoveryResult;

  const isValidated =
    selectedDataset?.status === "validated" ||
    (validationResult !== null && validationResult.total_validated_images > 0);

  return (
    <PageContainer
      title="Dataset Explorer"
      description="Registry of curated agricultural benchmarks and evaluator-uploaded datasets. Initial primary dataset is the ICAR Rice & Maize dataset, supported by supplementary domain benchmarks."
      badge="Curated Catalog"
    >
      {error && (
        <ErrorState
          title="API Connection Error"
          message={error}
          onRetry={fetchDatasets}
          className="mb-4"
        />
      )}

      {/* Filter and Status Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-croplens-border bg-croplens-card p-4">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-emerald-400" />
          <span className="text-xs font-medium text-zinc-300">Filter by Crop:</span>
          <div className="flex flex-wrap gap-1.5 ml-2">
            {["all", "rice", "maize", "paddy", "chilli"].map((crop) => (
              <button
                key={crop}
                onClick={() => setFilterCrop(crop)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                  filterCrop === crop
                    ? "bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 font-semibold"
                    : "bg-zinc-800/40 text-zinc-400 border border-zinc-700/40 hover:text-zinc-200"
                }`}
              >
                {crop}
              </button>
            ))}
          </div>
        </div>

        <div className="text-[11px] text-zinc-400 font-mono">
          Showing {filteredItems.length} of {items.length} registered datasets
        </div>
      </div>

      {loading ? (
        <LoadingState label="Loading registered dataset schemas..." rows={4} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Dataset List Column */}
          <div className="lg:col-span-1 space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 px-1">
              Registered Benchmarks
            </h3>
            <div className="space-y-2">
              {filteredItems.map((ds) => {
                const isSelected = selectedDataset?.id === ds.id;
                const isPrimary = ds.id === "icar-rice-maize";

                return (
                  <div
                    key={ds.id}
                    onClick={() => setSelectedDatasetId(ds.id)}
                    className={`cursor-pointer rounded-xl border p-4 transition-all duration-150 ${
                      isSelected
                        ? "border-emerald-600/70 bg-emerald-950/30 text-white shadow-sm"
                        : "border-croplens-border bg-croplens-card text-zinc-300 hover:border-emerald-900/50 hover:bg-croplens-card-hover"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Database
                          className={`h-4 w-4 shrink-0 ${
                            isSelected ? "text-emerald-400" : "text-zinc-400"
                          }`}
                        />
                        <span className="text-xs font-semibold leading-tight">
                          {ds.name}
                        </span>
                      </div>
                      {isPrimary && (
                        <span className="rounded bg-emerald-900/70 px-1.5 py-0.5 text-[9px] font-bold text-emerald-200 uppercase tracking-wide border border-emerald-600/60 shrink-0">
                          Primary
                        </span>
                      )}
                    </div>
                    <div className="mt-2.5 flex items-center justify-between text-[11px] text-zinc-400">
                      <span>{ds.crops.join(", ")}</span>
                      <span
                        className={`font-mono text-[10px] uppercase font-semibold ${
                          ds.status === "validated"
                            ? "text-emerald-300"
                            : ds.status === "discovered"
                            ? "text-emerald-400/90"
                            : ds.status === "invalid"
                            ? "text-amber-400"
                            : "text-zinc-400"
                        }`}
                      >
                        {ds.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Selected Dataset Detail Inspection */}
          <div className="lg:col-span-2 space-y-5">
            {selectedDataset ? (
              <>
                <DashboardCard
                  title={selectedDataset.name}
                  badge={{
                    text:
                      selectedDataset.status === "validated"
                        ? "Validated & Verified"
                        : selectedDataset.id === "icar-rice-maize"
                        ? "Primary Anchor"
                        : "Supplementary Benchmark",
                    variant: selectedDataset.id === "icar-rice-maize" ? "emerald" : "neutral",
                  }}
                  icon={<Database className="h-5 w-5" />}
                  description={selectedDataset.description}
                  headerAction={
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleRunDiscovery}
                        disabled={discovering || validating}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-700/60 bg-emerald-950/40 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/60 hover:text-white transition-colors disabled:opacity-50"
                      >
                        {discovering ? (
                          <>
                            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                            <span>Discovering...</span>
                          </>
                        ) : (
                          <>
                            <FolderSearch className="h-3.5 w-3.5" />
                            <span>{isDiscovered ? "Re-scan Files" : "Discover Dataset"}</span>
                          </>
                        )}
                      </button>

                      {isDiscovered && (
                        <button
                          onClick={handleRunValidation}
                          disabled={validating || discovering || detectingDuplicates}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/80 bg-emerald-600/30 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-600/50 hover:text-white transition-colors disabled:opacity-50"
                        >
                          {validating ? (
                            <>
                              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                              <span>Validating Images...</span>
                            </>
                          ) : (
                            <>
                              <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />
                              <span>Validate Images</span>
                            </>
                          )}
                        </button>
                      )}

                      {isValidated && (
                        <button
                          onClick={handleRunDuplicateDetection}
                          disabled={detectingDuplicates || validating || discovering}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-teal-500/80 bg-teal-600/30 px-3 py-1.5 text-xs font-semibold text-teal-200 hover:bg-teal-600/50 hover:text-white transition-colors disabled:opacity-50"
                        >
                          {detectingDuplicates ? (
                            <>
                              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                              <span>Hashing SHA-256...</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3.5 w-3.5 text-teal-300" />
                              <span>Detect Duplicates</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  }
                >
                  <div className="space-y-4">
                    {discoveryError && (
                      <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-3.5 text-xs text-red-300 flex items-start gap-2.5">
                        <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-red-200 block">Discovery Error</strong>
                          <span>{discoveryError}</span>
                        </div>
                      </div>
                    )}

                    {validationError && (
                      <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-3.5 text-xs text-red-300 flex items-start gap-2.5">
                        <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-red-200 block">Validation Error</strong>
                          <span>{validationError}</span>
                        </div>
                      </div>
                    )}

                    {duplicateError && (
                      <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-3.5 text-xs text-red-300 flex items-start gap-2.5">
                        <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-red-200 block">Duplicate Detection Error</strong>
                          <span>{duplicateError}</span>
                        </div>
                      </div>
                    )}

                    {/* Metadata Key-Value Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg border border-croplens-border bg-zinc-950/40 p-4 text-xs">
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Dataset Identifier / Slug:</span>
                        <span className="font-mono text-zinc-200">{selectedDataset.slug}</span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Source Registry:</span>
                        <span className="font-mono text-zinc-200">{selectedDataset.source}</span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Target Crops:</span>
                        <span className="text-emerald-300 font-medium">
                          {selectedDataset.crops.join(" • ")}
                        </span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Pipeline Status:</span>
                        <span className="font-mono text-emerald-400 uppercase font-semibold">
                          {selectedDataset.status}
                        </span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Discovered Images:</span>
                        <span className="font-mono text-zinc-200">
                          {selectedDataset.total_images ?? "Pending Discovery"}
                        </span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Validated Images:</span>
                        <span className="font-mono text-emerald-300 font-semibold">
                          {selectedDataset.validated_image_files !== null &&
                          selectedDataset.validated_image_files !== undefined
                            ? `${selectedDataset.validated_image_files} verified`
                            : "Not Yet Validated"}
                        </span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Exact Duplicate Groups:</span>
                        <span className="font-mono text-zinc-200 font-semibold">
                          {selectedDataset.duplicate_groups_count !== null &&
                          selectedDataset.duplicate_groups_count !== undefined
                            ? `${selectedDataset.duplicate_groups_count} groups`
                            : duplicateResult
                            ? `${duplicateResult.exact_duplicate_groups} groups`
                            : "Pending Analysis"}
                        </span>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Classification Tags:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {selectedDataset.tags.map((tag) => (
                            <span
                              key={tag}
                              className="inline-flex items-center gap-1 rounded bg-zinc-800/60 px-1.5 py-0.5 text-[10px] text-zinc-300 border border-zinc-700/50"
                            >
                              <Tag className="h-2.5 w-2.5 text-emerald-400" />
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <span className="text-zinc-400 block mb-0.5">Storage Reference:</span>
                        <span className="font-mono text-zinc-400 text-[11px]">
                          {selectedDataset.storage_relative_path || "curated/" + selectedDataset.slug}
                        </span>
                      </div>
                    </div>
                  </div>
                </DashboardCard>

                {/* Validation Real Results Panel */}
                {validationResult ? (
                  <DashboardCard
                    title="Image Integrity & Validation Report"
                    badge={{
                      text:
                        validationResult.total_corrupted_images === 0
                          ? "100% Valid & Intact"
                          : `${validationResult.total_corrupted_images} Corrupt Detected`,
                      variant:
                        validationResult.total_corrupted_images === 0 ? "emerald" : "amber",
                    }}
                    icon={<ShieldCheck className="h-5 w-5" />}
                    description={`Validated at ${formatDate(validationResult.validation_timestamp)} via Pillow byte stream decode`}
                  >
                    <div className="space-y-4 text-xs">
                      {/* Metric counts */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Validated Images</span>
                          <span className="text-lg font-bold text-emerald-300 font-mono">
                            {validationResult.total_validated_images}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Corrupted Files</span>
                          <span
                            className={`text-lg font-bold font-mono ${
                              validationResult.total_corrupted_images > 0
                                ? "text-red-400"
                                : "text-zinc-300"
                            }`}
                          >
                            {validationResult.total_corrupted_images}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Unreadable Files</span>
                          <span className="text-lg font-bold text-amber-400 font-mono">
                            {validationResult.total_unreadable_images}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Processing Errors</span>
                          <span className="text-lg font-bold text-zinc-400 font-mono">
                            {validationResult.total_processing_errors}
                          </span>
                        </div>
                      </div>

                      {/* Dimension Summary */}
                      {validationResult.dimension_summary && (
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/50 p-3.5 space-y-2">
                          <h4 className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                            <Maximize2 className="h-3.5 w-3.5 text-emerald-400" />
                            <span>Image Dimensions & Geometry:</span>
                          </h4>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                            <div>
                              <span className="text-zinc-400 block">Resolution Min:</span>
                              <span className="font-mono text-zinc-200">
                                {validationResult.dimension_summary.min_width} ×{" "}
                                {validationResult.dimension_summary.min_height} px
                              </span>
                            </div>
                            <div>
                              <span className="text-zinc-400 block">Resolution Max:</span>
                              <span className="font-mono text-zinc-200">
                                {validationResult.dimension_summary.max_width} ×{" "}
                                {validationResult.dimension_summary.max_height} px
                              </span>
                            </div>
                            <div>
                              <span className="text-zinc-400 block">Mean Resolution:</span>
                              <span className="font-mono text-emerald-300">
                                {validationResult.dimension_summary.mean_width} ×{" "}
                                {validationResult.dimension_summary.mean_height} px
                              </span>
                            </div>
                            <div>
                              <span className="text-zinc-400 block">Aspect Ratio Range:</span>
                              <span className="font-mono text-zinc-200">
                                {validationResult.dimension_summary.min_aspect_ratio} -{" "}
                                {validationResult.dimension_summary.max_aspect_ratio}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Color modes and formats */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="rounded-lg border border-croplens-border-subtle bg-zinc-950/30 p-3">
                          <span className="text-zinc-400 font-medium block mb-1.5">
                            Color Modes Encountered:
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(validationResult.color_mode_distribution).map(
                              ([mode, count]) => (
                                <span
                                  key={mode}
                                  className="rounded bg-emerald-950/60 px-2 py-0.5 font-mono text-[11px] text-emerald-300 border border-emerald-800/50"
                                >
                                  {mode}: {count}
                                </span>
                              )
                            )}
                          </div>
                        </div>

                        <div className="rounded-lg border border-croplens-border-subtle bg-zinc-950/30 p-3">
                          <span className="text-zinc-400 font-medium block mb-1.5">
                            Decoded Image Formats:
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(validationResult.format_distribution).map(
                              ([fmt, count]) => (
                                <span
                                  key={fmt}
                                  className="rounded bg-zinc-800/60 px-2 py-0.5 font-mono text-[11px] text-zinc-200 border border-zinc-700/50"
                                >
                                  {fmt}: {count}
                                </span>
                              )
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Corrupted Files List */}
                      {validationResult.corrupted_files.length > 0 && (
                        <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-3.5 space-y-2">
                          <span className="font-semibold text-red-300 block flex items-center gap-1.5">
                            <FileWarning className="h-4 w-4 text-red-400" />
                            <span>
                              Corrupted Files Identified ({validationResult.corrupted_files.length}):
                            </span>
                          </span>
                          <div className="max-h-48 overflow-y-auto divide-y divide-red-900/30 font-mono text-[11px]">
                            {validationResult.corrupted_files.map((cf) => (
                              <div key={cf.relative_path} className="py-1.5">
                                <span className="text-red-200 font-semibold block">
                                  {cf.relative_path}
                                </span>
                                <span className="text-red-400/90 text-[10px]">
                                  {cf.error_message || "Corrupt byte stream or header"}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </DashboardCard>
                ) : isDiscovered ? (
                  <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/20 p-4">
                    <div className="flex items-center gap-2 mb-1.5">
                      <FileCheck className="h-4 w-4 text-emerald-400" />
                      <h4 className="text-xs font-semibold text-emerald-200">
                        Image Decodability & Corruption Validation Ready
                      </h4>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Discovery found <strong className="text-emerald-300">{selectedDataset.total_images}</strong> candidate images across <strong className="text-emerald-300">{selectedDataset.total_classes}</strong> class directories. Click <strong className="text-emerald-300">Validate Images</strong> in the card header above to run full byte-level integrity checks with Pillow.
                    </p>
                  </div>
                ) : null}

                {/* Duplicate Detection Real Results Panel */}
                {duplicateResult ? (
                  <DashboardCard
                    title="Exact Duplicate Detection Report (SHA-256)"
                    badge={{
                      text:
                        duplicateResult.exact_duplicate_groups === 0
                          ? "0 Exact Duplicates (100% Unique)"
                          : `${duplicateResult.exact_duplicate_groups} Duplicate Groups (${duplicateResult.duplicate_instances_count} Redundant)`,
                      variant:
                        duplicateResult.exact_duplicate_groups === 0 ? "emerald" : "amber",
                    }}
                    icon={<Copy className="h-5 w-5" />}
                    description={`Analyzed at ${formatDate(duplicateResult.analysis_timestamp)} via chunked streaming SHA-256 byte hashing`}
                  >
                    <div className="space-y-4 text-xs">
                      {/* Metric counts */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Images Evaluated</span>
                          <span className="text-lg font-bold text-emerald-300 font-mono">
                            {duplicateResult.successfully_hashed_images}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Unique Hashes</span>
                          <span className="text-lg font-bold text-zinc-100 font-mono">
                            {duplicateResult.unique_content_groups}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Duplicate Groups</span>
                          <span
                            className={`text-lg font-bold font-mono ${
                              duplicateResult.exact_duplicate_groups > 0
                                ? "text-amber-400"
                                : "text-zinc-300"
                            }`}
                          >
                            {duplicateResult.exact_duplicate_groups}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Redundant Copies</span>
                          <span
                            className={`text-lg font-bold font-mono ${
                              duplicateResult.duplicate_instances_count > 0
                                ? "text-amber-400"
                                : "text-zinc-300"
                            }`}
                          >
                            {duplicateResult.duplicate_instances_count}
                          </span>
                        </div>
                      </div>

                      {/* Additional Metrics Row */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="rounded-lg border border-croplens-border-subtle bg-zinc-950/30 p-2.5 text-center">
                          <span className="text-zinc-400 block text-[11px]">Images in Groups</span>
                          <span className="text-sm font-bold text-zinc-200 font-mono">
                            {duplicateResult.images_in_duplicate_groups}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border-subtle bg-zinc-950/30 p-2.5 text-center">
                          <span className="text-zinc-400 block text-[11px]">Redundancy Percentage</span>
                          <span className="text-sm font-bold text-teal-300 font-mono">
                            {duplicateResult.duplicate_percentage}%
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border-subtle bg-zinc-950/30 p-2.5 text-center">
                          <span className="text-zinc-400 block text-[11px]">Cross-Class Groups</span>
                          <span
                            className={`text-sm font-bold font-mono ${
                              duplicateResult.cross_class_duplicate_groups > 0
                                ? "text-amber-400"
                                : "text-zinc-300"
                            }`}
                          >
                            {duplicateResult.cross_class_duplicate_groups}
                          </span>
                        </div>
                      </div>

                      {/* Informational Callout */}
                      <div className="rounded-lg border border-teal-900/40 bg-teal-950/20 p-3 text-[11px] text-teal-200/90 leading-relaxed">
                        <strong>Exact Content Matching:</strong> Exact duplicate detection identifies files whose raw byte content is 100% identical under SHA-256 hashing. Visual or near-duplicate detection using perceptual hashing will be evaluated in subsequent analysis milestones.
                      </div>

                      {/* Zero Duplicate State */}
                      {duplicateResult.exact_duplicate_groups === 0 ? (
                        <div className="rounded-lg border border-emerald-900/50 bg-emerald-950/30 p-4 text-center">
                          <CheckCircle2 className="h-6 w-6 text-emerald-400 mx-auto mb-2" />
                          <h4 className="text-xs font-semibold text-emerald-200">
                            100% Unique Content - No Exact Duplicates Found
                          </h4>
                          <p className="text-[11px] text-zinc-300 mt-1 max-w-lg mx-auto">
                            All {duplicateResult.successfully_hashed_images} evaluated image files have distinct SHA-256 byte digests. Every file in the dataset contains unique image data.
                          </p>
                        </div>
                      ) : (
                        /* Duplicate Groups View */
                        <div className="space-y-3">
                          <h4 className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                            <Files className="h-3.5 w-3.5 text-amber-400" />
                            <span>
                              Identified Exact Duplicate Groups ({duplicateResult.groups.length}):
                            </span>
                          </h4>
                          <div className="max-h-72 overflow-y-auto space-y-2.5 pr-1">
                            {duplicateResult.groups.map((group) => (
                              <div
                                key={group.group_id}
                                className="rounded-lg border border-croplens-border bg-zinc-950/60 p-3 space-y-2"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-croplens-border-subtle pb-2">
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono font-bold text-amber-300 text-xs">
                                      {group.group_id}
                                    </span>
                                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                                      {group.image_count} files ({(group.file_size_bytes / 1024).toFixed(1)} KB)
                                    </span>
                                  </div>
                                  {group.is_cross_class && (
                                    <span className="rounded bg-amber-950/80 px-2 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-700/60 flex items-center gap-1">
                                      <GitCompare className="h-3 w-3" />
                                      Cross-Class Duplicate
                                    </span>
                                  )}
                                </div>

                                <div className="text-[11px] font-mono text-zinc-400 truncate">
                                  <span className="text-zinc-500">SHA-256: </span>
                                  <span className="text-zinc-300">{group.sha256_hash}</span>
                                </div>

                                {/* Representative Member */}
                                <div className="bg-emerald-950/30 border border-emerald-900/40 rounded p-2 text-[11px]">
                                  <span className="text-emerald-400 font-semibold block mb-0.5">
                                    Canonical Representative (Preserved):
                                  </span>
                                  <div className="flex items-center justify-between gap-2 font-mono">
                                    <span className="text-emerald-200 truncate">
                                      {group.representative.relative_path}
                                    </span>
                                    <span className="rounded bg-emerald-900/60 px-1.5 py-0.2 text-[10px] text-emerald-300 shrink-0">
                                      {group.representative.class_name}
                                    </span>
                                  </div>
                                </div>

                                {/* Duplicate Instances */}
                                <div className="space-y-1">
                                  <span className="text-zinc-400 font-medium text-[11px] block">
                                    Redundant Duplicate Copies ({group.duplicates.length}):
                                  </span>
                                  <div className="space-y-1 font-mono text-[11px]">
                                    {group.duplicates.map((dup) => (
                                      <div
                                        key={dup.relative_path}
                                        className="flex items-center justify-between gap-2 rounded bg-zinc-900/50 px-2 py-1 border border-zinc-800/40"
                                      >
                                        <span className="text-zinc-300 truncate">
                                          {dup.relative_path}
                                        </span>
                                        <span className="rounded bg-zinc-800 px-1.5 py-0.2 text-[10px] text-zinc-400 shrink-0">
                                          {dup.class_name}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Per-Class Breakdown Table */}
                      {Object.keys(duplicateResult.class_metrics).length > 0 && (
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/50 p-3 space-y-2">
                          <h4 className="text-xs font-semibold text-zinc-200">
                            Class-Level Duplicate Metrics Breakdown:
                          </h4>
                          <div className="max-h-48 overflow-y-auto rounded border border-croplens-border-subtle bg-zinc-950/40 divide-y divide-croplens-border-subtle text-[11px]">
                            {Object.values(duplicateResult.class_metrics).map((cm) => (
                              <div
                                key={cm.class_name}
                                className="flex items-center justify-between px-3 py-1.5 hover:bg-zinc-900/40"
                              >
                                <span className="font-mono text-zinc-300">{cm.class_name}</span>
                                <div className="flex items-center gap-3 font-mono">
                                  <span className="text-zinc-400">
                                    {cm.total_images} images
                                  </span>
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                      cm.duplicate_instances > 0
                                        ? "bg-amber-950/70 text-amber-300 border border-amber-800/50"
                                        : "bg-zinc-800/50 text-zinc-400"
                                    }`}
                                  >
                                    {cm.duplicate_instances} dups ({cm.duplicate_percentage}%)
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </DashboardCard>
                ) : isValidated ? (
                  <div className="rounded-lg border border-teal-900/40 bg-teal-950/20 p-4">
                    <div className="flex items-center gap-2 mb-1.5">
                      <Copy className="h-4 w-4 text-teal-400" />
                      <h4 className="text-xs font-semibold text-teal-200">
                        Exact Duplicate Detection Ready
                      </h4>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Image integrity has been verified for <strong className="text-emerald-300">{selectedDataset.validated_image_files ?? validationResult?.total_validated_images}</strong> readable images. Click <strong className="text-teal-300">Detect Duplicates</strong> in the card header above to scan for byte-identical files using chunked streaming SHA-256.
                    </p>
                  </div>
                ) : null}

                {/* Discovery Real Results Panel */}
                {discoveryResult && (
                  <DashboardCard
                    title="Ingestion Discovery Metadata"
                    badge={{
                      text:
                        discoveryResult.discovery_status === "discovered"
                          ? "Real Filesystem Metrics"
                          : discoveryResult.discovery_status,
                      variant:
                        discoveryResult.discovery_status === "discovered"
                          ? "emerald"
                          : "amber",
                    }}
                    icon={<FolderOpen className="h-5 w-5" />}
                    description={`Discovered at ${formatDate(discoveryResult.ingestion_timestamp)}`}
                  >
                    <div className="space-y-4 text-xs">
                      {/* Metric counts */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Discovered Images</span>
                          <span className="text-lg font-bold text-emerald-300 font-mono">
                            {discoveryResult.discovered_image_files ?? "null"}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Class Directories</span>
                          <span className="text-lg font-bold text-zinc-100 font-mono">
                            {discoveryResult.discovered_class_directories ?? "null"}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Validated Images</span>
                          <span className="text-lg font-bold text-emerald-300 font-mono">
                            {selectedDataset.validated_image_files ?? "Not Run"}
                          </span>
                        </div>
                        <div className="rounded-lg border border-croplens-border bg-zinc-950/40 p-3 text-center">
                          <span className="text-zinc-400 block text-[11px]">Inaccessible / Errors</span>
                          <span className="text-lg font-bold text-amber-400 font-mono">
                            {discoveryResult.unreadable_or_inaccessible_count}
                          </span>
                        </div>
                      </div>

                      {/* Extensions encountered */}
                      <div className="flex items-center gap-2 py-2 border-y border-croplens-border-subtle">
                        <span className="text-zinc-400 font-medium">Image Formats Encountered:</span>
                        <div className="flex gap-1.5">
                          {discoveryResult.supported_extensions_encountered.length > 0 ? (
                            discoveryResult.supported_extensions_encountered.map((ext) => (
                              <span
                                key={ext}
                                className="rounded bg-emerald-950/60 px-2 py-0.5 font-mono text-[11px] text-emerald-300 border border-emerald-800/50"
                              >
                                {ext}
                              </span>
                            ))
                          ) : (
                            <span className="text-zinc-400 italic">None found</span>
                          )}
                        </div>
                      </div>

                      {/* Classes breakdown */}
                      {discoveryResult.classes.length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-zinc-200 mb-2 flex items-center gap-1.5">
                            <Layers className="h-3.5 w-3.5 text-emerald-400" />
                            <span>Discovered Class Hierarchy ({discoveryResult.classes.length} classes):</span>
                          </h4>
                          <div className="max-h-60 overflow-y-auto rounded-lg border border-croplens-border bg-zinc-950/60 divide-y divide-croplens-border-subtle">
                            {discoveryResult.classes.map((c) => (
                              <div
                                key={c.class_name}
                                className="flex items-center justify-between px-3.5 py-2 text-xs hover:bg-zinc-900/50"
                              >
                                <span className="font-mono text-zinc-200">{c.class_name}</span>
                                <span className="rounded bg-zinc-800/60 px-2 py-0.5 font-mono text-[11px] text-emerald-300 border border-zinc-700/50">
                                  {c.image_count} images
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </DashboardCard>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}
    </PageContainer>
  );
}
