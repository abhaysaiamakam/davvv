"use client";

import type { VisualizationSpecification } from "@croplens/shared-types";

export function VisualizationChart({ spec }: { spec: VisualizationSpecification }) {
  const rows = spec.chart_data;
  const series = spec.series[0];
  const values = rows.map((row) => Number(row[series?.data_key ?? "value"])).filter(Number.isFinite);
  if (!rows.length || !values.length || !["bar", "histogram", "line", "scatter"].includes(spec.chart_type)) {
    return <div className="flex min-h-44 flex-col items-center justify-center rounded-lg bg-gray-50 px-4 text-center"><p className="text-xs font-medium text-zinc-400">{rows.length ? `${spec.chart_type.replaceAll("_", " ")} preview is not supported yet` : "No chart data returned"}</p><p className="mt-1 text-[11px] text-zinc-400">The backend result and metadata are available above.</p></div>;
  }
  const max = Math.max(...values, 1);
  const color = series?.color || "#23834f";
  const labelKey = spec.x_axis?.name || "label";
  if (spec.chart_type === "line" || spec.chart_type === "scatter") {
    const yKey = series?.data_key ?? spec.y_axis?.name ?? "value";
    const rawX = spec.chart_type === "scatter" ? rows.map((row) => Number(row[spec.x_axis?.name ?? "x"])) : rows.map((_,i)=>i);
    const rawY = rows.map((row) => Number(row[yKey]));
    const validY = rawY.filter(Number.isFinite);
    const xMin=Math.min(...rawX),xMax=Math.max(...rawX),yMax=Math.max(...validY,1),yMin=Math.min(...validY,0);
    const points = rows.map((row, i) => ({ x: spec.chart_type === "scatter" ? (rawX[i]-xMin)/Math.max(xMax-xMin,1)*100 : i * 100 / Math.max(rows.length - 1, 1), y: 100 - (rawY[i]-yMin)/Math.max(yMax-yMin,1)*90, label: String(row[labelKey] ?? i + 1), actualX: rawX[i], actualY: rawY[i] })).filter((point) => Number.isFinite(point.y)&&Number.isFinite(point.x));
    if(spec.chart_type==="scatter"&&(!spec.x_axis||points.length!==rows.length))return <Fallback type={spec.chart_type}/>;
    const d = points.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");
    return <div className="pt-2"><svg viewBox="0 0 100 110" role="img" aria-label={`${spec.title} ${spec.chart_type} chart`} className="h-52 w-full overflow-visible"><path d="M0 100H100M0 50H100M0 0H100" stroke="#e8ede9" strokeWidth=".7"/>{spec.chart_type==="line"&&<path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke"/>}{points.map((p,i)=><circle key={i} cx={p.x} cy={p.y} r={spec.chart_type==="scatter"?1.8:1.3} fill={color}><title>{p.label}: ({p.actualX}, {p.actualY})</title></circle>)}</svg><div className="mt-1 flex justify-between text-[10px] text-zinc-400"><span>{spec.x_axis?.label??String(rows[0]?.[labelKey] ?? "1")}</span><span>{spec.x_axis?.scale==="linear"?`${xMin} – ${xMax}`:String(rows.at(-1)?.[labelKey] ?? rows.length)}</span></div></div>;
  }
  return <div className="space-y-2">{rows.slice(0, 12).map((row,i)=>{const val=Number(row[series?.data_key ?? "value"]); return <div key={i} className="grid grid-cols-[minmax(72px,1fr)_minmax(100px,2fr)_38px] items-center gap-2"><span className="truncate text-[10px] text-zinc-400" title={String(row[labelKey] ?? row.category ?? row.bin_label ?? i+1)}>{String(row[labelKey] ?? row.category ?? row.bin_label ?? i+1)}</span><div className="h-2 rounded-full bg-gray-100"><div className="h-full rounded-full transition-[width] duration-500" style={{width:`${Math.max(1,val/max*100)}%`,background:color}}/></div><span className="text-right font-mono text-[10px] text-zinc-400">{Number.isInteger(val)?val:val.toFixed(1)}</span></div>})}</div>;
}

function Fallback({type}:{type:string}){return <div className="flex min-h-44 flex-col items-center justify-center rounded-lg bg-gray-50 px-4 text-center"><p className="text-xs font-medium text-zinc-400">{type.replaceAll("_"," ")} preview is not supported for this specification</p><p className="mt-1 text-[11px] text-zinc-400">The backend result and metadata remain available above.</p></div>}
