import { Download, ExternalLink, ImageIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

interface Plot {
  url: string;
  caption: string;
}

interface Props {
  plots: Plot[];
}

function describePlot(plot: Plot) {
  const raw = `${plot.caption} ${plot.url}`.toLowerCase();

  if (raw.includes("senescence_score")) {
    return {
      title: "SenMayo Senescence Score UMAP",
      description: "Cells embedded by UMAP and colored by SenMayo signature score.",
    };
  }

  if (raw.includes("age_distribution")) {
    return {
      title: "Cell Counts by Age Group",
      description: "Number of cells represented in each age group.",
    };
  }

  if (raw.includes("senescence_violin")) {
    return {
      title: "Senescence Score Distribution by Age",
      description: "Distribution of SenMayo scores across age groups.",
    };
  }

  if (raw.includes("umap")) {
    return {
      title: "Cell Cluster UMAP",
      description: "Two-dimensional UMAP embedding colored by Leiden cluster.",
    };
  }

  const fallback = plot.caption
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

  return {
    title: fallback,
    description: "Generated analysis plot.",
  };
}

export default function Plots({ plots }: Props) {
  const normalizedPlots = useMemo(
    () =>
      plots.map((plot, index) => {
        const description = describePlot(plot);

        return {
          ...plot,
          ...description,
          id: `${plot.url}-${index}`,
          src: `http://127.0.0.1:8000${plot.url}`,
        };
      }),
    [plots]
  );

  const [selectedId, setSelectedId] = useState(normalizedPlots.at(-1)?.id);

  useEffect(() => {
    setSelectedId(normalizedPlots.at(-1)?.id);
  }, [normalizedPlots.length]);

  const selectedPlot =
    normalizedPlots.find((plot) => plot.id === selectedId) ??
    normalizedPlots.at(-1) ??
    normalizedPlots[0];

  if (plots.length === 0) return null;

  return (
    <section className="mt-6 border border-slate-200 bg-white p-4 shadow-sm sm:p-5 lg:col-span-2">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
              <ImageIcon size={16} strokeWidth={1.8} />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Generated plots</h2>
              <p className="mt-0.5 text-xs text-slate-500">{plots.length} plot{plots.length === 1 ? "" : "s"} in this session</p>
            </div>
          </div>
        </div>

        {selectedPlot && (
          <div className="flex items-center gap-2">
            <a
              href={selectedPlot.src}
              target="_blank"
              rel="noreferrer"
              title="Open plot"
              className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-emerald-200 hover:text-emerald-700"
            >
              <ExternalLink size={15} strokeWidth={1.8} />
            </a>
            <a
              href={selectedPlot.src}
              download
              title="Download plot"
              className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-emerald-200 hover:text-emerald-700"
            >
              <Download size={15} strokeWidth={1.8} />
            </a>
          </div>
        )}
      </div>

      {selectedPlot && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <figure className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
            <div className="flex min-h-[320px] items-center justify-center p-3 sm:min-h-[420px]">
              <img
                src={selectedPlot.src}
                alt={selectedPlot.title}
                className="max-h-[560px] w-full object-contain"
              />
            </div>
            <figcaption className="border-t border-slate-200 bg-white px-4 py-3">
              <p className="text-sm font-semibold text-slate-900">{selectedPlot.title}</p>
              <p className="mt-1 text-xs leading-5 text-slate-600">{selectedPlot.description}</p>
              <p className="mt-1 break-all text-xs text-slate-500">{selectedPlot.url}</p>
            </figcaption>
          </figure>

          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-100 px-3 py-2">
              <p className="text-xs font-semibold uppercase text-slate-500">Plot library</p>
            </div>
            <div className="max-h-[520px] space-y-2 overflow-y-auto p-2">
              {normalizedPlots.map((plot) => {
                const isSelected = plot.id === selectedPlot.id;

                return (
                  <button
                    key={plot.id}
                    type="button"
                    onClick={() => setSelectedId(plot.id)}
                    className={`grid w-full grid-cols-[72px_minmax(0,1fr)] gap-3 rounded-md border p-2 text-left transition ${
                      isSelected
                        ? "border-emerald-300 bg-emerald-50"
                        : "border-slate-100 bg-white hover:border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="flex h-16 items-center justify-center overflow-hidden rounded bg-slate-100">
                      <img src={plot.src} alt="" className="h-full w-full object-contain" />
                    </span>
                    <span className="min-w-0 self-center">
                      <span className="block truncate text-sm font-medium text-slate-800">
                        {plot.title}
                      </span>
                      <span className="mt-1 block truncate text-xs text-slate-500">
                        {plot.description}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
