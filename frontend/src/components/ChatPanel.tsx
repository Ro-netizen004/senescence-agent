import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import type { ToolCallLog } from "../App";

/* ── Color-coded, rich Markdown renderer ─────────────────────────────── */

const mdComponents: Components = {
  h3: ({ children }) => (
    <h3 className="flex items-center gap-2 text-[15px] font-bold text-slate-900 tracking-tight mt-4 mb-2 first:mt-0">
      <span className="inline-block h-3 w-1 rounded-full bg-violet-500" />
      {children}
    </h3>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
      <table className="w-full text-[13px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gradient-to-r from-slate-50 to-slate-100 border-b border-slate-200">
      {children}
    </thead>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wider text-slate-600">
      {children}
    </th>
  ),
  td: ({ children }) => {
    const text = String(children ?? "");
    // Color-code specific values
    let extra = "text-slate-700";
    if (/^\d+\.\d+%?$/.test(text) || /^[\d,]+$/.test(text.replace(/,/g, ""))) {
      extra = "font-semibold text-slate-900 tabular-nums";
    }
    if (/significant/i.test(text) && !/not/i.test(text)) {
      extra = "font-semibold text-emerald-700";
    }
    if (/not significant/i.test(text) || /underpowered/i.test(text)) {
      extra = "font-semibold text-amber-600";
    }
    if (/NA/i.test(text) && text.length <= 3) {
      extra = "text-slate-400 italic";
    }
    return <td className={`px-3 py-2 border-t border-slate-100 ${extra}`}>{children}</td>;
  },
  tr: ({ children }) => (
    <tr className="hover:bg-violet-50/30 transition-colors">{children}</tr>
  ),
  strong: ({ children }) => {
    const text = String(children ?? "");
    // Color-code result headlines
    if (/highest senescence/i.test(text)) {
      return <strong className="text-rose-600 font-bold">{children}</strong>;
    }
    if (/significant/i.test(text) && !/not/i.test(text)) {
      return <strong className="text-emerald-700 font-bold">{children}</strong>;
    }
    if (/not significant/i.test(text) || /underpowered/i.test(text)) {
      return <strong className="text-amber-600 font-bold">{children}</strong>;
    }
    if (/result:/i.test(text)) {
      return <strong className="text-violet-700 font-bold">{children}</strong>;
    }
    if (/detected:/i.test(text) || /coverage/i.test(text)) {
      return <strong className="text-blue-700 font-bold">{children}</strong>;
    }
    if (/error|failed|could not/i.test(text)) {
      return <strong className="text-rose-600 font-bold">{children}</strong>;
    }
    return <strong className="text-slate-900 font-semibold">{children}</strong>;
  },
  blockquote: ({ children }) => {
    const text = String(children ?? "");
    let style = "border-l-violet-300 bg-violet-50/50";
    let icon = "info";
    if (/warning|caution|note.*low/i.test(text)) {
      style = "border-l-amber-400 bg-amber-50/50";
      icon = "warn";
    }
    if (/descriptive only|no p-value/i.test(text)) {
      style = "border-l-blue-300 bg-blue-50/50";
      icon = "info";
    }
    if (/good coverage|reliable/i.test(text)) {
      style = "border-l-emerald-400 bg-emerald-50/50";
      icon = "ok";
    }
    return (
      <blockquote className={`${style} border-l-[3px] rounded-r-lg py-2 px-3 my-3 not-italic`}>
        <div className="flex gap-2 items-start">
          <span className="mt-0.5 text-[13px]">
            {icon === "warn" ? "!" : icon === "ok" ? "+" : "i"}
          </span>
          <div className="text-[12px] leading-relaxed text-slate-600">{children}</div>
        </div>
      </blockquote>
    );
  },
  p: ({ children }) => (
    <p className="my-1.5 text-[13px] leading-relaxed text-slate-700">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-1.5 space-y-1 text-[13px] text-slate-700 list-none pl-0">{children}</ul>
  ),
  li: ({ children }) => (
    <li className="flex gap-2 items-baseline">
      <span className="h-1.5 w-1.5 rounded-full bg-violet-400 mt-1.5 shrink-0" />
      <span>{children}</span>
    </li>
  ),
  em: ({ children }) => (
    <em className="text-[11px] text-slate-500 not-italic">{children}</em>
  ),
};

function AssistantReply({ content }: { content: string }) {
  const sections = content.split(/\n\n---\n\n/);
  const [auditOpen, setAuditOpen] = useState(false);

  const auditLines: string[] = [];
  const bodySections: string[] = [];

  for (const section of sections) {
    const systemIdx = section.search(/\[System\]/);
    const body = (systemIdx >= 0 ? section.slice(0, systemIdx) : section).trim();
    const meta = systemIdx >= 0 ? section.slice(systemIdx).trim() : null;
    if (body) bodySections.push(body);
    if (meta) auditLines.push(meta);
  }

  return (
    <div className="space-y-1">
      {bodySections.map((body, i) => (
        <div key={i} className={i > 0 ? "border-t border-slate-100 pt-3 mt-3" : undefined}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {body}
          </ReactMarkdown>
        </div>
      ))}

      {auditLines.length > 0 && (
        <button
          onClick={() => setAuditOpen(!auditOpen)}
          className="flex items-center gap-1.5 mt-2 text-[11px] font-medium text-slate-400 hover:text-slate-600 transition-colors"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            className={`transition-transform ${auditOpen ? "rotate-90" : ""}`}
          >
            <path d="M3 1l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          Audit trail ({auditLines.length})
        </button>
      )}
      {auditOpen && auditLines.length > 0 && (
        <div className="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 font-mono text-[10px] leading-relaxed text-slate-400 whitespace-pre-wrap mt-1">
          {auditLines.join("\n")}
        </div>
      )}
    </div>
  );
}

/* ── Chat panel ──────────────────────────────────────────────────────── */

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  history: Message[];
  message: string;
  loading: boolean;
  reportLoading: boolean;
  fileId: string;
  fileName: string;
  error: string;
  lastToolCalls: ToolCallLog[];
  sessionToolRunCount: number;
  setMessage: (v: string) => void;
  onSend: () => void;
  onGenerateReport: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onReset: () => void;
}

export default function ChatPanel({
  history,
  message,
  loading,
  reportLoading,
  fileId,
  fileName,
  error,
  setMessage,
  onSend,
  onGenerateReport,
  onKeyDown,
  lastToolCalls,
  sessionToolRunCount,
  onReset,
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, loading]);

  return (
    <div className="flex h-[calc(100vh-2rem)] max-h-[900px] flex-col bg-white font-sans antialiased overflow-hidden rounded-2xl border border-slate-100 shadow-sm">

      {/* ── TOP BAR ─────────────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center justify-between border-b border-slate-100 px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="h-2.5 w-2.5 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500" />
          <h1 className="text-[15px] font-bold tracking-tight text-slate-900">
            Senescence Agent
          </h1>
        </div>

        <div className="flex items-center gap-2.5">
          <div
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium leading-none transition-colors ${
              fileId
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-slate-200 bg-slate-50 text-slate-400"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${fileId ? "bg-emerald-500" : "bg-slate-300"}`} />
            {fileId ? (fileName || "Dataset loaded") : "No dataset"}
          </div>

          <button
            onClick={onGenerateReport}
            disabled={!fileId || loading || reportLoading || sessionToolRunCount === 0}
            title={sessionToolRunCount === 0 ? "Run an analysis first" : "Generate PDF report"}
            className="flex h-7 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-500 transition hover:border-violet-200 hover:text-violet-700 hover:bg-violet-50 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 1.5h5l3 3v10H4z" />
              <path d="M9 1.5v3h3" />
            </svg>
            {reportLoading ? "Writing..." : `Report (${sessionToolRunCount})`}
          </button>

          <button
            onClick={onReset}
            title="New session"
            className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 transition hover:border-slate-300 hover:text-slate-600 active:scale-95"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13.5 2.5A7 7 0 1 0 14 8" />
              <polyline points="14 2 14 6 10 6" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── MESSAGES ────────────────────────────────────────────────── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5">
        {history.length === 0 && !loading ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-100 to-fuchsia-50 text-violet-500">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p className="text-base font-bold text-slate-800">
              {fileId ? "Ready to analyze" : "Upload a dataset to begin"}
            </p>
            <p className="mt-2 max-w-sm text-[13px] leading-6 text-slate-500">
              {fileId
                ? 'Try: "Run the full senescence analysis" or "What is the p-value for senescence in T cells?"'
                : "Upload a .h5ad single-cell RNA-seq dataset and ask questions in plain English."}
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {history.map((msg, i) => (
              <div
                key={i}
                className={`flex items-start gap-3 ${
                  msg.role === "user" ? "flex-row-reverse" : "flex-row"
                }`}
              >
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[10px] font-bold mt-0.5 ${
                    msg.role === "user"
                      ? "bg-violet-600 text-white"
                      : "bg-gradient-to-br from-slate-100 to-slate-50 text-slate-500 border border-slate-200"
                  }`}
                >
                  {msg.role === "user" ? "You" : "SA"}
                </div>

                <div
                  className={`rounded-2xl text-sm leading-6 ${
                    msg.role === "user"
                      ? "max-w-[65%] rounded-br-md bg-violet-600 text-white px-4 py-3"
                      : "max-w-[90%] rounded-bl-md border border-slate-100 bg-white text-slate-800 px-5 py-4 shadow-sm"
                  }`}
                >
                  {msg.role === "user" ? (
                    <span className="whitespace-pre-wrap">{msg.content}</span>
                  ) : (
                    <AssistantReply content={msg.content} />
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex items-start gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-slate-100 to-slate-50 text-[10px] font-bold text-slate-500 border border-slate-200 mt-0.5">
                  SA
                </div>
                <div className="rounded-2xl rounded-bl-md border border-slate-100 bg-white px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      {[0, 1, 2].map((n) => (
                        <span
                          key={n}
                          className="h-2 w-2 rounded-full bg-violet-400 animate-bounce"
                          style={{ animationDelay: `${n * 150}ms`, animationDuration: "1s" }}
                        />
                      ))}
                    </div>
                    <span className="text-[13px] text-slate-500 font-medium">Running analysis...</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── TOOL CHIPS ──────────────────────────────────────────────── */}
      {lastToolCalls.length > 0 && !loading && (
        <div className="mx-5 mb-2 rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-2.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Tools:</span>
            {lastToolCalls.map((t, i) => {
              const toolColors: Record<string, string> = {
                find_senescence_markers: "bg-blue-50 text-blue-700 border-blue-200",
                senescence_score: "bg-rose-50 text-rose-700 border-rose-200",
                generate_umap: "bg-violet-50 text-violet-700 border-violet-200",
                get_cluster_annotations: "bg-teal-50 text-teal-700 border-teal-200",
                compare_across_age: "bg-amber-50 text-amber-700 border-amber-200",
                test_senescence_difference: "bg-emerald-50 text-emerald-700 border-emerald-200",
                run_deseq2: "bg-purple-50 text-purple-700 border-purple-200",
              };
              const color = toolColors[t.name] || "bg-slate-50 text-slate-600 border-slate-200";
              return (
                <span
                  key={`${t.name}-${i}`}
                  className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${color}`}
                >
                  {t.name.replace(/_/g, " ")}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* ── ERROR ───────────────────────────────────────────────────── */}
      {error && (
        <div className="mx-5 mb-2 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] text-rose-700 font-medium">
          <span className="mt-0.5">!</span>
          {error}
        </div>
      )}

      {/* ── INPUT ───────────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-slate-100 px-4 py-4">
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 transition focus-within:border-violet-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-violet-100">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder={fileId ? "Ask about your dataset..." : "Upload a dataset first..."}
            disabled={!fileId}
            className="flex-1 resize-none bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none disabled:cursor-not-allowed disabled:opacity-50"
          />
          <button
            onClick={onSend}
            disabled={!fileId || !message.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white transition hover:from-violet-700 hover:to-fuchsia-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 shadow-sm"
            title="Send"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="2" y1="14" x2="14" y2="2" />
              <polyline points="6 2 14 2 14 10" />
            </svg>
          </button>
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-400">
          <kbd className="rounded border border-slate-200 bg-white px-1 py-px font-mono text-[10px] text-slate-500">Enter</kbd> send
          &nbsp;&middot;&nbsp;
          <kbd className="rounded border border-slate-200 bg-white px-1 py-px font-mono text-[10px] text-slate-500">Shift+Enter</kbd> new line
        </p>
      </div>
    </div>
  );
}
