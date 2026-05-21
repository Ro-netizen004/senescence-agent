interface Plot {
  url: string;
  caption: string;
}

interface Props {
  plots: Plot[];
}

export default function Plots({ plots }: Props) {
  if (plots.length === 0) return null;

  return (
    <div className="mt-6 rounded-2xl border border-slate-100 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Generated plots</h2>
          <p className="mt-0.5 text-xs text-slate-400">Plots generated during this session.</p>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-slate-500">
          {plots.length}
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {plots.map((plot, i) => (
          <figure
            key={i}
            className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md"
          >
            <div className="overflow-hidden bg-slate-100">
              <img
                src={`http://127.0.0.1:8000${plot.url}`}
                alt={plot.caption}
                className="h-56 w-full object-contain transition duration-300 group-hover:scale-[1.02]"
              />
            </div>
            <figcaption className="border-t border-slate-100 px-4 py-2.5 text-xs font-medium text-slate-600">
              {plot.caption}
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}