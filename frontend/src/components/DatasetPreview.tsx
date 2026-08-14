import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Database } from "lucide-react";

interface PreviewData {
  n_cells: number;
  n_genes: number;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  genes: string[];
  row_limit: number;
}

interface Props {
  fileId: string;
  fileName: string;
  species: string;
  apiBase: string;
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function DatasetPreview({ fileId, fileName, species, apiBase }: Props) {
  const [data, setData] = useState<PreviewData | null>(null);
  const [open, setOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!fileId) {
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(`${apiBase}/dataset/${fileId}/preview?species=${species}&rows=20`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || "Preview unavailable");
        setData(body);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Preview unavailable");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [fileId, species, apiBase]);

  const visibleColumns = useMemo(() => data?.columns ?? [], [data]);

  return (
    <section className="border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50"
        aria-expanded={open}
      >
        <span className="flex min-w-0 items-center gap-3">
          <Database className="h-4 w-4 shrink-0 text-teal-600" aria-hidden="true" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-slate-900">Data preview</span>
            <span className="block truncate text-xs text-slate-500">{fileName || "Uploaded dataset"}</span>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
          {data ? `${data.n_cells.toLocaleString()} cells x ${data.n_genes.toLocaleString()} genes` : ""}
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </span>
      </button>

      {open ? (
        <div className="border-t border-slate-100">
          {loading ? <p className="px-5 py-6 text-sm text-slate-500">Loading preview...</p> : null}
          {error ? <p className="px-5 py-6 text-sm text-rose-700">{error}</p> : null}
          {data && !loading ? (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-max border-collapse text-left text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-slate-600">
                    <tr>
                      {visibleColumns.map((column) => (
                        <th key={column} className="border-b border-r border-slate-200 px-3 py-2 font-semibold last:border-r-0">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row, index) => (
                      <tr key={`${displayValue(row.cell_id)}-${index}`} className="odd:bg-white even:bg-slate-50/50 hover:bg-teal-50/40">
                        {visibleColumns.map((column) => (
                          <td key={column} className="max-w-64 truncate border-b border-r border-slate-100 px-3 py-2 text-slate-700 last:border-r-0" title={displayValue(row[column])}>
                            {displayValue(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-col gap-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                <span>Showing {data.rows.length} of {data.n_cells.toLocaleString()} observation rows</span>
                <span className="max-w-2xl truncate" title={data.genes.join(", ")}>Genes: {data.genes.join(", ")}</span>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
