"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Database, FileDown, FileText, GitCompare, Lightbulb, ScanSearch, ShieldCheck, Sprout, Upload, WandSparkles, Gauge, BriefcaseBusiness, Images, Presentation } from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  ["Dashboard", "/", BarChart3], ["Datasets", "/datasets", Database], ["Data Quality", "/quality", ShieldCheck],
  ["Visual Explorer", "/explorer", Images],
  ["Phase 1 Dataset Submission", "/phase1", Presentation],
  ["EDA Studio", "/eda", ScanSearch], ["Insights", "/insights", Lightbulb], ["Preprocessing", "/preprocessing", WandSparkles],
  ["Feature Engineering", "/features", Activity], ["Comparison", "/comparison", GitCompare], ["Readiness", "/readiness", Gauge],
  ["Reports", "/reports", FileText], ["Export Center", "/exports", FileDown], ["Job Center", "/jobs", BriefcaseBusiness], ["Upload dataset", "/analyze", Upload],
] as const;

export function Sidebar() {
  const pathname = usePathname();
  return <><aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-croplens-border bg-white md:flex">
    <Link href="/" className="flex h-[72px] items-center gap-3 border-b border-croplens-border px-5" aria-label="CropLens dashboard">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"><Sprout size={22}/></span>
      <span><span className="block text-[15px] font-bold tracking-tight text-zinc-100">CropLens</span><span className="block text-[11px] text-zinc-400">Dataset intelligence</span></span>
    </Link>
    <div className="px-4 pt-6 pb-2 text-[10px] font-semibold uppercase tracking-[.12em] text-zinc-400">Workspace</div>
    <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4" aria-label="Main navigation">
      {items.map(([label, href, Icon]) => {
        const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
        return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={cn("flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-medium transition-colors", active ? "bg-emerald-50 text-emerald-800" : "text-zinc-400 hover:bg-gray-50 hover:text-zinc-100")}>
          <Icon size={17} strokeWidth={1.8}/><span>{label}</span>{href === "/jobs" && <span className="ml-auto rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">Live</span>}
        </Link>;
      })}
    </nav>
    <div className="m-3 rounded-xl border border-croplens-border bg-gray-50 p-3.5">
      <div className="flex items-center gap-2 text-xs font-semibold text-zinc-100"><Activity size={14} className="text-emerald-700"/>Analysis engine</div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-400">Results are computed by the connected CropLens API.</p>
    </div>
  </aside><nav className="fixed inset-x-0 bottom-0 z-40 flex h-14 items-center justify-start gap-1 overflow-x-auto border-t border-croplens-border bg-white px-2 md:hidden" aria-label="Mobile navigation">{items.map(([label,href,Icon])=>{const active=href==="/"?pathname==="/":pathname===href||pathname.startsWith(`${href}/`);return <Link key={href} href={href} aria-label={label} aria-current={active?"page":undefined} className={`flex h-full min-w-[68px] flex-none flex-col items-center justify-center gap-1 text-[9px] font-medium ${active?"text-emerald-800":"text-zinc-400"}`}><Icon size={17}/><span className="max-w-[66px] truncate">{label}</span></Link>})}</nav></>;
}
