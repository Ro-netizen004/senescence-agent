import { useEffect, useMemo, useState } from "react";

interface ColumnInfo {
  name: string;
  role: string;
  n_levels: number;
  values: string[];
  samples_per_value?: Record<string, number>;
}

interface RolesData {
  columns: ColumnInfo[];
  cell_type_column: string | null;
  sample_column: string | null;
  primary_group_column: string | null;
  group_options: string[];
  sample_options: string[];
  n_cells: number;
  result?: { ok: boolean; errors: string[]; warnings: string[] };
}

interface Props {
  fileId: string;
  species: string;
  apiBase: string;
}

type Assign = "A" | "B" | "";

export default function ColumnRoles({ fileId, species, apiBase }: Props) {
  const [data, setData] = useState<RolesData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(true);

  const [cellTypeCol, setCellTypeCol] = useState("");
  const [sampleCol, setSampleCol] = useState("");
  const [groupCol, setGroupCol] = useState("");

  // Custom group builder (neutral defaults — the meaning depends on the dataset)
  const [aName, setAName] = useState("group_1");
  const [bName, setBName] = useState("group_2");
  const [assign, setAssign] = useState<Record<string, Assign>>({});

  const [warnings, setWarnings] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!fileId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setSaved(false);
    setWarnings([]);
    setErrors([]);
    fetch(`${apiBase}/dataset/${fileId}/columns?species=${species}`)
      .then((r) => r.json())
      .then((d: RolesData) => {
        if (cancelled) return;
        applyData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, species, apiBase]);

  function applyData(d: RolesData) {
    setData(d);
    setCellTypeCol(d.cell_type_column || "");
    setSampleCol(d.sample_column || "");
    setGroupCol(d.primary_group_column || "");
  }

  const groupInfo = useMemo(
    () => data?.columns.find((c) => c.name === groupCol),
    [data, groupCol]
  );
  const sourceValues = groupInfo?.values ?? [];
  const samplesPerValue = groupInfo?.samples_per_value ?? {};
  const needsCustom = sourceValues.length > 2;

  // Seed the A/B assignment whenever the grouping column changes.
  useEffect(() => {
    if (!groupInfo) return;
    if (needsCustom) {
      const seeded: Record<string, Assign> = {};
      sourceValues.forEach((v) => (seeded[v] = ""));
      setAssign(seeded);
    } else {
      setAssign({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupCol, data]);

  const countFor = (target: Assign) =>
    sourceValues
      .filter((v) => assign[v] === target)
      .reduce((sum, v) => sum + (samplesPerValue[v] || 0), 0);
  const aCount = countFor("A");
  const bCount = countFor("B");
  const customTestable = aCount >= 2 && bCount >= 2;

  async function post(body: Record<string, unknown>) {
    setSaving(true);
    setSaved(false);
    setErrors([]);
    setWarnings([]);
    try {
      const res = await fetch(`${apiBase}/dataset/${fileId}/columns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species, ...body }),
      });
      const d: RolesData = await res.json();
      applyData(d);
      setWarnings(d.result?.warnings || []);
      setErrors(d.result?.errors || []);
      setSaved(!!d.result?.ok);
    } catch {
      setErrors(["Could not save. Is the server running?"]);
    } finally {
      setSaving(false);
    }
  }

  function applyRoles() {
    post({
      sample_column: sampleCol || null,
      cell_type_column: cellTypeCol || null,
      primary_group_column: needsCustom ? null : groupCol || null,
    });
  }

  function applyCustomGroups() {
    const groups: Record<string, string[]> = { [aName]: [], [bName]: [] };
    sourceValues.forEach((v) => {
      if (assign[v] === "A") groups[aName].push(v);
      if (assign[v] === "B") groups[bName].push(v);
    });
    post({
      sample_column: sampleCol || null,
      cell_type_column: cellTypeCol || null,
      grouping: { column: groupCol, groups },
    });
  }

  if (!fileId) return null;

  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Dataset setup</h2>
          <p className="mt-0.5 text-xs leading-5 text-slate-400">
            Generic roles on the left, your dataset's columns on the right. Confirm or change
            them — every analysis follows this table.
          </p>
        </div>
        <button
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 rounded-md px-2 py-1 text-[11px] font-medium text-slate-400 hover:bg-slate-50 hover:text-slate-600"
        >
          {open ? "Hide" : "Show"}
        </button>
      </div>

      {loading ? (
        <p className="mt-4 text-xs text-slate-400">Analyzing columns…</p>
      ) : !data ? (
        <p className="mt-4 text-xs text-slate-400">Column roles unavailable.</p>
      ) : open ? (
        <div className="mt-4 flex flex-col gap-5">
          {/* Role mapping table */}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">What it is</th>
                  <th className="py-2 pr-4 font-medium">Column in your data</th>
                  <th className="py-2 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                <tr>
                  <td className="py-2.5 pr-4 font-medium text-slate-700">Cell type</td>
                  <td className="py-2.5 pr-4">
                    <ColSelect value={cellTypeCol} options={data.sample_options} suggested={data.cell_type_column} onChange={setCellTypeCol} />
                  </td>
                  <td className="py-2.5 text-xs text-slate-500">
                    {data.columns.find((c) => c.name === cellTypeCol)?.n_levels ?? "—"} type(s)
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 pr-4 font-medium text-slate-700">
                    Sample<span className="block text-[11px] font-normal text-slate-400">replicate unit</span>
                  </td>
                  <td className="py-2.5 pr-4">
                    <ColSelect value={sampleCol} options={data.sample_options} suggested={data.sample_column} onChange={setSampleCol} allowNone />
                  </td>
                  <td className="py-2.5 text-xs text-slate-500">
                    {data.columns.find((c) => c.name === sampleCol)?.n_levels ?? "—"} samples
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 pr-4 font-medium text-slate-700">
                    Compare by<span className="block text-[11px] font-normal text-slate-400">grouping variable</span>
                  </td>
                  <td className="py-2.5 pr-4">
                    <ColSelect value={groupCol} options={data.group_options} suggested={data.primary_group_column} onChange={setGroupCol} allowNone />
                  </td>
                  <td className="py-2.5 text-xs text-slate-500">
                    {sourceValues.length > 0
                      ? sourceValues
                          .slice(0, 6)
                          .map((v) => `${v}${samplesPerValue[v] != null ? ` (${samplesPerValue[v]})` : ""}`)
                          .join(", ") + (sourceValues.length > 6 ? " …" : "")
                      : "—"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Custom group builder — shown when the grouping has >2 values */}
          {needsCustom ? (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
              <p className="text-xs font-semibold text-slate-700">
                Define the two groups to compare
              </p>
              <p className="mt-0.5 text-[11px] leading-4 text-slate-500">
                '{groupCol}' has {sourceValues.length} values. Assign each to a group (e.g. treat
                several conditions as one control).
              </p>

              <div className="mt-3 flex items-center gap-2 text-xs">
                <span className="text-slate-500">Group names:</span>
                <input value={aName} onChange={(e) => setAName(e.target.value)} className="w-28 rounded-md border border-slate-200 px-2 py-1 text-xs" />
                <span className="text-slate-400">vs</span>
                <input value={bName} onChange={(e) => setBName(e.target.value)} className="w-28 rounded-md border border-slate-200 px-2 py-1 text-xs" />
              </div>

              <div className="mt-3 overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-400">
                      <th className="py-1.5 pr-4 font-medium">Value</th>
                      <th className="py-1.5 pr-4 font-medium">Samples</th>
                      <th className="py-1.5 font-medium">Assign to</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {sourceValues.map((v) => (
                      <tr key={v}>
                        <td className="py-1.5 pr-4 text-slate-700">{v}</td>
                        <td className="py-1.5 pr-4 text-xs text-slate-500">{samplesPerValue[v] ?? 0}</td>
                        <td className="py-1.5">
                          <select
                            value={assign[v] || ""}
                            onChange={(e) => setAssign((a) => ({ ...a, [v]: e.target.value as Assign }))}
                            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-800 outline-none focus:border-indigo-300"
                          >
                            <option value="">— exclude —</option>
                            <option value="A">{aName}</option>
                            <option value="B">{bName}</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-2 flex items-center gap-3 text-[11px]">
                <span className={aCount >= 2 ? "text-slate-500" : "text-amber-600"}>
                  {aName}: {aCount} sample{aCount === 1 ? "" : "s"}
                </span>
                <span className={bCount >= 2 ? "text-slate-500" : "text-amber-600"}>
                  {bName}: {bCount} sample{bCount === 1 ? "" : "s"}
                </span>
                <span className={customTestable ? "font-medium text-emerald-600" : "text-amber-600"}>
                  {customTestable ? "✓ testable" : "needs ≥2 samples per group"}
                </span>
              </div>

              <button
                onClick={applyCustomGroups}
                disabled={saving}
                className="mt-3 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Apply custom groups"}
              </button>
            </div>
          ) : null}

          {errors.length > 0 ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] leading-4 text-rose-800">
              {errors.map((e, i) => <p key={i}>{e}</p>)}
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-4 text-amber-800">
              {warnings.map((w, i) => <p key={i}>⚠ {w}</p>)}
            </div>
          ) : null}

          {!needsCustom ? (
            <div className="flex items-center gap-3">
              <button
                onClick={applyRoles}
                disabled={saving}
                className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Apply"}
              </button>
              {saved ? <span className="text-[11px] font-medium text-emerald-600">Saved ✓</span> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ColSelect({
  value,
  options,
  suggested,
  onChange,
  allowNone,
}: {
  value: string;
  options: string[];
  suggested: string | null;
  onChange: (v: string) => void;
  allowNone?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full max-w-[220px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
    >
      {allowNone ? <option value="">(none)</option> : null}
      {options.map((c) => (
        <option key={c} value={c}>
          {c}
          {c === suggested ? "  — suggested" : ""}
        </option>
      ))}
    </select>
  );
}
