import { useState, type ChangeEvent, type KeyboardEvent } from "react";
import UploadPanel from "./components/UploadPanel";
import ColumnRoles from "./components/ColumnRoles";
import DatasetPreview from "./components/DatasetPreview";
import ChatPanel from "./components/ChatPanel";
import Plots from "./components/Plots";
import { API_BASE } from "./config";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Plot {
  url: string;
  caption: string;
}

export interface ToolCallLog {
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
}

export default function App() {
  const [fileId, setFileId] = useState("");
  const [fileName, setFileName] = useState("");
  const [species, setSpecies] = useState("mouse");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Message[]>([]);
  const [plots, setPlots] = useState<Plot[]>([]);
  const [lastToolCalls, setLastToolCalls] = useState<ToolCallLog[]>([]);
  const [lastAnalysisPlan, setLastAnalysisPlan] = useState<unknown>(null);
  const [sessionToolRuns, setSessionToolRuns] = useState<ToolCallLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());

  async function uploadFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("species", species);

    try {
      const res = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Upload failed. Please try again.");
      }

      const data = await res.json();
      setFileId(data.file_id);
      setFileName(file.name);
      setHistory([]);
      setPlots([]);
      setLastToolCalls([]);
      setLastAnalysisPlan(null);
      setSessionToolRuns([]);
      setError("");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed. Is the server running?";
      setError(msg);
    }
  }

  async function sendMessage(promptOverride?: string) {
    const outgoingMessage = promptOverride ?? message;
    if (!outgoingMessage.trim() || !fileId || loading) return;

    const userMsg: Message = { role: "user", content: outgoingMessage };
    const updated = [...history, userMsg];

    setHistory(updated);
    setMessage("");
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: userMsg.content,
          file_id: fileId,
          species,
          session_history: updated,
        }),
      });

      const data = await res.json();

      setHistory([
        ...updated,
        { role: "assistant", content: data.reply || "Done." },
      ]);

      const toolCalls: ToolCallLog[] = data.tool_calls || [];
      setLastToolCalls(toolCalls);
      setLastAnalysisPlan(data.analysis_plan ?? null);
      if (toolCalls.length) {
        setSessionToolRuns((prev) => [...prev, ...toolCalls]);
      }

      if (data.plots?.length) {
        setPlots((p) => {
          const seen = new Set(p.map((x) => x.url));
          const next = [...p];
          for (const plot of data.plots) {
            if (!seen.has(plot.url)) {
              next.push(plot);
              seen.add(plot.url);
            }
          }
          return next;
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error occurred";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function generateReport() {
    if (!fileId || loading || reportLoading || sessionToolRuns.length === 0) return;

    setReportLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          file_id: fileId,
          species,
          session_history: history,
          tool_runs: sessionToolRuns,
          plots,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Report generation failed.");
      }

      const reportLinks = [
        data.pdf_url ? `[Download PDF](${API_BASE}${data.pdf_url})` : "",
        data.report_url ? `[Open Markdown](${API_BASE}${data.report_url})` : "",
      ].filter(Boolean);

      const reportContent = [
        data.report || "Report generated.",
        reportLinks.length ? `\n\n---\n\n${reportLinks.join(" · ")}` : "",
      ].join("");

      setHistory((current) => [
        ...current,
        { role: "assistant", content: reportContent },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Report generation failed";
      setError(msg);
    } finally {
      setReportLoading(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function resetSession() {
    setHistory([]);
    setPlots([]);
    setLastToolCalls([]);
    setLastAnalysisPlan(null);
    setSessionToolRuns([]);
    setSessionId(crypto.randomUUID());
    setFileId("");
    setFileName("");
    setError("");
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-slate-100 to-violet-50 py-6 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-xl sm:p-8">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-indigo-600">Senescence Agent</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
                Single-cell analysis assistant
              </h1>
            </div>
            <p className="max-w-xl text-sm leading-6 text-slate-600">
              Upload a dataset, ask questions, and browse generated plots with explicit methods, statistical units, and reproducible outputs.
            </p>
          </div>
        </div>

        {fileId ? (
          <div className="mb-6">
            <div className="flex flex-col gap-4">
              <ColumnRoles fileId={fileId} species={species} apiBase={API_BASE} />
              <DatasetPreview fileId={fileId} fileName={fileName} species={species} apiBase={API_BASE} />
            </div>
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start">
          <UploadPanel
            fileId={fileId}
            fileName={fileName}
            species={species}
            onSpeciesChange={setSpecies}
            onUpload={uploadFile}
          />

          <ChatPanel
            history={history}
            message={message}
            loading={loading}
            reportLoading={reportLoading}
            fileId={fileId}
            fileName={fileName}
            error={error}
            lastToolCalls={lastToolCalls}
            analysisPlan={lastAnalysisPlan}
            sessionToolRunCount={sessionToolRuns.length}
            setMessage={setMessage}
            onSend={sendMessage}
            onGenerateReport={generateReport}
            onKeyDown={handleKeyDown}
            onReset={resetSession}
            onSuggestedPrompt={sendMessage}
          />

          <Plots plots={plots} apiBase={API_BASE} />
        </div>
      </div>
    </div>
  );
}
