"use client";
import { useEffect, useRef, useState } from "react";
import PageShell from "@/components/PageShell";
import { api } from "@/lib/api";

export default function ResumePage() {
  const [info, setInfo] = useState<{
    path: string;
    filename: string;
    exists: boolean;
    size_bytes: number;
    warning?: string;
  } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const d = await api.getResume();
      setInfo(d);
    } catch {}
  };

  useEffect(() => { load(); }, []);

  const upload = async (file: File) => {
    setUploading(true);
    setMessage("");
    try {
      const res = await api.uploadResume(file);
      setMessage(`Uploaded: ${res.filename}`);
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage(`Error: ${msg}`);
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) upload(file);
  };

  return (
    <PageShell page="resume">
      {() => (
        <>
          <div className="page-header">
            <div className="page-tag">// OPERATIVE FILE</div>
            <div className="page-title">RESUME</div>
          </div>

          {info && (
            <div className="resume-card">
              <div style={{ marginBottom: 10 }}>
                <div className="metric-label">Current File</div>
                <div style={{ color: info.exists ? "var(--accent)" : "var(--danger)", fontSize: 13, marginTop: 4 }}>
                  {info.filename || "No file configured"}
                </div>
              </div>
              <div style={{ display: "flex", gap: 24 }}>
                <div>
                  <div className="metric-label">Status</div>
                  <div style={{ color: info.exists ? "var(--success)" : "var(--danger)", fontSize: 12, marginTop: 2 }}>
                    {info.exists ? "FILE FOUND" : "FILE MISSING"}
                  </div>
                </div>
                {info.size_bytes > 0 && (
                  <div>
                    <div className="metric-label">Size</div>
                    <div style={{ fontSize: 12, marginTop: 2, color: "var(--text)" }}>
                      {(info.size_bytes / 1024).toFixed(1)} KB
                    </div>
                  </div>
                )}
              </div>
              {info.path && (
                <div style={{ marginTop: 10, fontSize: 10, color: "var(--text-dim)", wordBreak: "break-all" }}>
                  PATH: {info.path}
                </div>
              )}
              {info.warning && (
                <div style={{ marginTop: 8, fontSize: 11, color: "var(--warn)" }}>{info.warning}</div>
              )}
            </div>
          )}

          <div
            className={`dropzone${dragOver ? " drag-over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            data-interactive
          >
            <div className="dropzone-text">
              {uploading ? "UPLOADING..." : "DROP RESUME FILE HERE"}
            </div>
            <div className="dropzone-subtext">TXT, PDF, DOCX accepted</div>
            <input
              ref={inputRef}
              type="file"
              accept=".txt,.pdf,.docx"
              style={{ display: "none" }}
              onChange={onFileChange}
            />
          </div>

          <div style={{ marginTop: 16 }}>
            <button
              className="btn"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              data-interactive
            >
              <span>UPLOAD FILE</span>
            </button>
          </div>

          {message && (
            <div
              style={{
                marginTop: 12,
                fontSize: 12,
                color: message.startsWith("Error") ? "var(--danger)" : "var(--success)",
                letterSpacing: "0.06em",
              }}
            >
              {message}
            </div>
          )}
        </>
      )}
    </PageShell>
  );
}
