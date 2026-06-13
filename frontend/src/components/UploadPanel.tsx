import type { ChangeEvent } from "react";

interface Props {
  fileId: string;
  fileName: string;
  species: string;
  onSpeciesChange: (species: string) => void;
  onUpload: (e: ChangeEvent<HTMLInputElement>) => void;
}

export default function UploadPanel({
  fileId,
  fileName,
  species,
  onSpeciesChange,
  onUpload,
}: Props) {
  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">

      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Dataset</h2>
          <p className="mt-0.5 text-xs leading-5 text-slate-400">
            Upload a .h5ad file to begin analysis.
          </p>
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-medium text-slate-600">
          Species (gene symbols)
        </label>
        <select
          value={species}
          onChange={(e) => onSpeciesChange(e.target.value)}
          disabled={!!fileId}
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:opacity-70"
        >
          <option value="mouse">Mouse</option>
          <option value="human">Human</option>
        </select>
        {fileId ? (
          <p className="mt-1 text-[11px] text-slate-400">
            Species locked for this upload. Reset session to change.
          </p>
        ) : null}
      </div>

      <label
        className={`group relative flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
          fileId
            ? "border-emerald-200 bg-emerald-50/60 hover:bg-emerald-50"
            : "border-slate-200 bg-slate-50 hover:border-indigo-300 hover:bg-indigo-50/40"
        }`}
      >
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
            fileId ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-500 group-hover:bg-indigo-100 group-hover:text-indigo-600"
          }`}
        >
          {fileId ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          )}
        </div>

        {fileId ? (
          <div className="space-y-0.5">
            <p className="text-sm font-semibold text-emerald-700">Dataset loaded</p>
            <p className="max-w-[180px] truncate text-xs text-emerald-600">{fileName || fileId}</p>
            <p className="text-[11px] text-emerald-500/80">Click to replace</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            <p className="text-sm font-semibold text-slate-700 group-hover:text-indigo-700 transition-colors">
              Choose a file
            </p>
            <p className="text-xs text-slate-400">
              .h5ad format · single-cell data
            </p>
          </div>
        )}

        <input
          type="file"
          accept=".h5ad"
          onChange={onUpload}
          className="hidden"
        />
      </label>

      <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
        <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-600">
          <span className="inline-block h-2.5 w-1 rounded-full bg-gradient-to-b from-indigo-500 to-violet-500" />
          Reading results
        </h3>
        <p className="mt-1.5 text-[11px] leading-5 text-slate-500">
          Replies are governed: claims are limited to what the statistics support.
        </p>
        <dl className="mt-3 space-y-2.5">
          {[
            {
              label: "LOW POWER",
              caution: true,
              desc: "Too few replicates/cells for a reliable test. Numeric trends only.",
            },
            {
              label: "DESCRIPTIVE ONLY",
              caution: false,
              desc: "Medians and counts reported. No p-values or causal claims.",
            },
            {
              label: "NOT SIGNIFICANT",
              caution: false,
              desc: "Test ran; difference not significant at α = 0.05.",
            },
          ].map((item) => (
            <div key={item.label} className="flex flex-col gap-1">
              <span
                className={`inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${
                  item.caution
                    ? "border-amber-300 bg-amber-50 text-amber-800"
                    : "border-indigo-200 bg-white text-indigo-700"
                }`}
              >
                {item.label}
              </span>
              <span className="text-[11px] leading-4 text-slate-500">{item.desc}</span>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
