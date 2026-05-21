import { useState, type ChangeEvent, type KeyboardEvent } from "react";
import UploadPanel from "./components/UploadPanel";
import ChatPanel from "./components/ChatPanel";
import Plots from "./components/Plots";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Plot {
  url: string;
  caption: string;
}

export default function App() {
  const [fileId, setFileId] = useState("");
  const [fileName, setFileName] = useState("");
  const [species] = useState("mouse");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Message[]>([]);
  const [plots, setPlots] = useState<Plot[]>([]);
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessionId] = useState(() => crypto.randomUUID());

  async function uploadFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("species", species);

    try {
      const res = await fetch("http://127.0.0.1:8000/upload", {
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
      setError("");
    } catch (err: any) {
      setError(err?.message || "Upload failed. Is the server running?");
    }
  }

  async function sendMessage() {
    if (!message.trim() || !fileId || loading) return;

    const userMsg: Message = { role: "user", content: message };
    const updated = [...history, userMsg];

    setHistory(updated);
    setMessage("");
    setLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
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

      if (data.plots?.length) {
        setPlots((p) => [...p, ...data.plots]);
      }
    } catch (err: any) {
      setError(err.message || "Error occurred");
    } finally {
      setLoading(false);
    }
  }

  async function generateReport() {
    if (!fileId || loading || reportLoading || history.length === 0) return;

    setReportLoading(true);
    setError("");

    try {
      const res = await fetch("http://127.0.0.1:8000/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          file_id: fileId,
          species,
          session_history: history,
          plots,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Report generation failed.");
      }

      const reportLinks = [
        data.pdf_url ? `[Download PDF](http://127.0.0.1:8000${data.pdf_url})` : "",
        data.report_url ? `[Open Markdown](http://127.0.0.1:8000${data.report_url})` : "",
      ].filter(Boolean);

      const reportContent = [
        data.report || "Report generated.",
        reportLinks.length ? `\n\n---\n\n${reportLinks.join(" · ")}` : "",
      ].join("");

      setHistory((current) => [
        ...current,
        { role: "assistant", content: reportContent },
      ]);
    } catch (err: any) {
      setError(err.message || "Report generation failed");
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
    setFileId("");
    setFileName("");
    setError("");
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-100 via-slate-50 to-emerald-50 py-6 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-xl sm:p-8">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-emerald-700">Senescence Agent</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
                Single-cell analysis assistant
              </h1>
            </div>
            <p className="max-w-xl text-sm leading-6 text-slate-600">
              Upload a dataset, ask questions, and browse generated plots in a polished, responsive chat experience.
            </p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <UploadPanel
            fileId={fileId}
            fileName={fileName}
            species={species}
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
            setMessage={setMessage}
            onSend={sendMessage}
            onGenerateReport={generateReport}
            onKeyDown={handleKeyDown}
            onReset={resetSession}
          />

          <Plots plots={plots} />
        </div>
      </div>
    </div>
  );
}
