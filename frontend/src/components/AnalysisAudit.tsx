import {
  Database,
  GitCompareArrows,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import type { ToolCallLog } from "../App";

type Dict = Record<string, unknown>;

function asDict(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Dict
    : {};
}

function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function shown(value: unknown, fallback = "Not recorded") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function Status({ value }: { value: unknown }) {
  const text = shown(value);
  const good = ["accepted", "ok", "stable", "SIGNIFICANT_INFERENTIAL"].includes(text);
  const caution = ["corrected_to_deterministic", "deterministic_fallback"].includes(text);
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
      good
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : caution
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : "border-slate-200 bg-slate-50 text-slate-600"
    }`}>
      {text.replace(/_/g, " ")}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-semibold uppercase text-slate-400">{label}</dt>
      <dd className="mt-0.5 break-words text-xs font-medium text-slate-800">{shown(value)}</dd>
    </div>
  );
}

export default function AnalysisAudit({
  toolCalls,
  analysisPlan,
}: {
  toolCalls: ToolCallLog[];
  analysisPlan: unknown;
}) {
  const call = [...toolCalls].reverse().find((item) => item.name === "run_deseq2");
  if (!call) return null;

  const args = asDict(call.args);
  const result = asDict(call.result);
  const inference = asDict(result.inference_state);
  const stability = asDict(result.replicate_stability);
  const plausibility = asDict(result.result_plausibility);
  const countValidation = asDict(result.count_validation);
  const method = result.method;
  const governanceMode = result.governance_mode;
  const planAudit = asDict(analysisPlan);
  const plan = asDict(planAudit.validated_plan);
  const reference = result.reference_group ?? args.reference_group ?? plan.reference_group;
  const comparison = result.comparison_group ?? args.comparison_group ?? plan.comparison_group;
  const groupColumn = result.group_column ?? args.group_column ?? plan.group_column;
  const covariates = asList(result.covariates_used ?? args.covariates ?? plan.covariates);
  const dropped = asList(result.covariates_dropped);
  const stable = stability.n_stable_genes;
  const significant = stability.n_significant_genes ?? result.n_significant_fdr_0_05;
  const stableSummary = stable !== undefined && significant !== undefined
    ? `${shown(stable)} / ${shown(significant)} (${shown(stability.stable_gene_fraction)})`
    : shown(stability.verdict);

  return (
    <section className="mx-5 mb-2 border-y border-slate-200 bg-white px-1 py-3" aria-label="Executed analysis audit">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={15} className="text-emerald-600" aria-hidden="true" />
          <h2 className="text-xs font-semibold text-slate-800">Executed analysis</h2>
        </div>
        <Status value={inference.state ?? governanceMode} />
      </div>

      <dl className="grid grid-cols-2 gap-x-5 gap-y-3 md:grid-cols-4">
        <Metric label="Contrast" value={`${shown(comparison)} vs ${shown(reference)}`} />
        <Metric label="Grouping column" value={groupColumn} />
        <Metric
          label="Statistical unit"
          value={result.statistical_unit ?? args.sample_column ?? plan.unit_of_replication}
        />
        <Metric label="Covariates used" value={covariates.length ? covariates.join(", ") : "None"} />
      </dl>

      <div className="mt-3 grid gap-2 border-t border-slate-100 pt-3 sm:grid-cols-3">
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <GitCompareArrows size={14} className="text-indigo-500" aria-hidden="true" />
          <span>Method</span>
          <span className="font-medium text-slate-800">{shown(method).replace(/_/g, " ")}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span>Planner</span><Status value={planAudit.status} />
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <Database size={14} className="text-indigo-500" aria-hidden="true" />
          <span>Counts</span>
          <span className="font-medium text-slate-800">{shown(countValidation.source ?? countValidation.provenance)}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <SlidersHorizontal size={14} className="text-indigo-500" aria-hidden="true" />
          <span>Design</span>
          <span className="font-medium text-slate-800">{asList(result.design_factors).join(" + ") || shown(groupColumn)}</span>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-3 border-t border-slate-100 pt-3 md:grid-cols-4">
        <Metric label="Plausibility" value={plausibility.verdict} />
        <Metric label="Donor stability" value={stableSummary} />
        <Metric label="Samples" value={result.n_samples} />
        <Metric label="Dropped covariates" value={dropped.length ? dropped.join(", ") : "None"} />
      </dl>
    </section>
  );
}
