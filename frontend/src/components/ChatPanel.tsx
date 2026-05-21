import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown"

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
  onReset,
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, loading]);

  return (
    <div className="flex h-[calc(100vh-2rem)] max-h-[900px] flex-col bg-white font-sans antialiased overflow-hidden">

      {/* ── TOP BAR ─────────────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center justify-between border-b border-slate-100 px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="h-2 w-2 rounded-full bg-violet-500" />
          <h1 className="text-sm font-semibold tracking-tight text-slate-900">
            Dataset&nbsp;Chat
          </h1>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium leading-none transition-colors ${
              fileId
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-slate-200 bg-slate-50 text-slate-400"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                fileId ? "bg-emerald-500" : "bg-slate-300"
              }`}
            />
            {fileId ? (fileName || fileId) : "No dataset"}
          </div>

          <button
            onClick={onGenerateReport}
            disabled={!fileId || loading || reportLoading || history.length === 0}
            title="Generate report"
            className="flex h-7 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-slate-500 transition hover:border-emerald-200 hover:text-emerald-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 1.5h5l3 3v10H4z" />
              <path d="M9 1.5v3h3" />
              <path d="M6 8h4" />
              <path d="M6 10.5h4" />
            </svg>
            {reportLoading ? "Writing" : "Report"}
          </button>

          <button
            onClick={onReset}
            title="New session"
            className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 transition hover:border-slate-300 hover:text-slate-600 active:scale-95"
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13.5 2.5A7 7 0 1 0 14 8" />
              <polyline points="14 2 14 6 10 6" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── MESSAGES ────────────────────────────────────────────────── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        {history.length === 0 && !loading ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-50 text-violet-500">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-700">
              {fileId ? "Ask anything about your data" : "Upload a dataset to get started"}
            </p>
            <p className="mt-1.5 max-w-xs text-xs leading-5 text-slate-400">
              {fileId
                ? "Explore genes, clusters, aging signals, or ask for a plot."
                : "Once uploaded, you can query your dataset with natural language."}
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {history.map((msg, i) => (
              <div
                key={i}
                className={`flex items-end gap-2.5 ${
                  msg.role === "user" ? "flex-row-reverse" : "flex-row"
                }`}
              >
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                    msg.role === "user"
                      ? "bg-violet-100 text-violet-700"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {msg.role === "user" ? "You" : "AI"}
                </div>

                <div
                  className={`max-w-[72%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    msg.role === "user"
                      ? "rounded-br-sm bg-violet-600 text-white"
                      : "rounded-bl-sm border border-slate-100 bg-slate-50 text-slate-800"
                  }`}
                >
                  {msg.role === "user" ? (
                    msg.content
                  ) : (
                    <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-strong:text-slate-900 prose-li:text-slate-800">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex items-end gap-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-semibold text-slate-500">
                  AI
                </div>
                <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-slate-100 bg-slate-50 px-4 py-3">
                  {[0, 1, 2].map((n) => (
                    <span
                      key={n}
                      className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce"
                      style={{ animationDelay: `${n * 120}ms`, animationDuration: "0.9s" }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── ERROR BANNER ────────────────────────────────────────────── */}
      {error && (
        <div className="mx-6 mb-2 flex items-start gap-2 rounded-xl border border-rose-100 bg-rose-50 px-4 py-2.5 text-xs text-rose-600">
          <svg className="mt-0.5 shrink-0" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="8" cy="8" r="7" />
            <line x1="8" y1="5" x2="8" y2="8.5" />
            <circle cx="8" cy="11" r="0.5" fill="currentColor" />
          </svg>
          {error}
        </div>
      )}

      {/* ── INPUT BAR ───────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-slate-100 px-4 py-4">
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 transition focus-within:border-violet-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-violet-100">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder={fileId ? "Ask about your dataset…" : "Upload a dataset first…"}
            disabled={!fileId}
            className="flex-1 resize-none bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none disabled:cursor-not-allowed disabled:opacity-50"
          />

          <button
            onClick={onSend}
            disabled={!fileId || !message.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-violet-600 text-white transition hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            title="Send"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="2" y1="14" x2="14" y2="2" />
              <polyline points="6 2 14 2 14 10" />
            </svg>
          </button>
        </div>

        <p className="mt-2 text-center text-[10px] text-slate-400">
          Press <kbd className="rounded border border-slate-200 bg-white px-1 py-px font-mono text-[10px] text-slate-500">⏎</kbd> to send
          &nbsp;·&nbsp;
          <kbd className="rounded border border-slate-200 bg-white px-1 py-px font-mono text-[10px] text-slate-500">Shift ⏎</kbd> for new line
        </p>
      </div>
    </div>
  );
}
