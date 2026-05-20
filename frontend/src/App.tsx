import { useState } from "react";

function App() {
  const [fileId, setFileId] = useState("");
  const [message, setMessage] = useState("");
  const [sessionId] = useState("test-session");
  const [response, setResponse] = useState<any>(null);

  async function uploadFile(e: any) {
    const file = e.target.files[0];

    const formData = new FormData();
    formData.append("file", file);
    formData.append("species", "mouse");

    const res = await fetch("http://127.0.0.1:8000/upload", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();
    setFileId(data.file_id);
  }

  async function sendPrompt() {
    const res = await fetch("http://127.0.0.1:8000/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
        message: message,
        file_id: fileId,
        species: "mouse",
      }),
    });

    const data = await res.json();
    setResponse(data);
  }

  return (
    <div style={{ padding: 20 }}>
      <h1>Senescence Agent</h1>

      {/* Upload */}
      <input type="file" onChange={uploadFile} />

      {fileId && <p>File uploaded ✅ {fileId}</p>}

      {/* Prompt input */}
      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Ask something..."
        style={{ width: "300px", marginTop: 10 }}
      />

      <button onClick={sendPrompt} disabled={!fileId}>
        Send
      </button>

      {/* Output */}
      {response && (
        <div style={{ marginTop: 20 }}>
          <h3>Reply:</h3>
          <p>{response.reply}</p>

          <h4>Tools:</h4>
          <pre>{JSON.stringify(response.tool_calls, null, 2)}</pre>

          <h4>Plots:</h4>
          {response.plots?.map((p: any, i: number) => (
            <img key={i} src={`http://127.0.0.1:8000${p.url}`} width="400" />
          ))}
        </div>
      )}
    </div>
  );
}

export default App;