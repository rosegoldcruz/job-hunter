"use client";
import { useState } from "react";
import { api, Job, Packet } from "@/lib/api";

interface Props {
  job: Job;
  onStatusChange: (id: number, status: string) => void;
}

function StatusBadge({ status }: { status: string }) {
  const cls = `badge badge-${status.replace("_", "-")}`;
  return <span className={cls}>{status.replace("_", " ").toUpperCase()}</span>;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function extractTags(job: Job): string[] {
  const text = ((job.description || "") + " " + (job.search_keyword || "")).toLowerCase();
  const keywords = [
    "python","react","next.js","typescript","crm","automation","api",
    "full stack","revops","marketing","sales","seo","voip","twilio","sql",
    "aws","docker","remote","b2b","saas",
  ];
  return keywords.filter((k) => text.includes(k)).slice(0, 6);
}

export default function JobCard({ job, onStatusChange }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [loadingPacket, setLoadingPacket] = useState(false);
  const [packetError, setPacketError] = useState("");
  const [approving, setApproving] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState("");

  const tags = extractTags(job);

  const loadPacket = async () => {
    if (packet) return;
    setLoadingPacket(true);
    setPacketError("");
    try {
      const data = await api.getPacket(job.id);
      setPacket(data.packet);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setPacketError(msg.includes("404") ? "Packet still generating…" : msg);
    } finally {
      setLoadingPacket(false);
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      await api.approveJob(job.id);
      onStatusChange(job.id, "approved");
      setExpanded(true);
      // Poll for packet
      let attempts = 0;
      const poll = async () => {
        try {
          const data = await api.getPacket(job.id);
          setPacket(data.packet);
        } catch {
          if (attempts++ < 10) setTimeout(poll, 2000);
        }
      };
      setTimeout(poll, 1500);
    } catch (e: unknown) {
      console.error(e);
    } finally {
      setApproving(false);
    }
  };

  const handleAction = async (action: "save" | "trash") => {
    try {
      if (action === "save") await api.saveJob(job.id);
      else await api.trashJob(job.id);
      onStatusChange(job.id, action === "save" ? "saved" : "trash");
    } catch (e) {
      console.error(e);
    }
  };

  const handleExpand = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !packet) await loadPacket();
  };

  const handleSend = async () => {
    setSending(true);
    setSendMsg("");
    try {
      await api.sendJob(job.id);
      setSendMsg("Application sent!");
      onStatusChange(job.id, "applied");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setSendMsg(`Error: ${msg}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="job-card">
      <div className="job-card-body">
        <div className="job-header">
          <span className="job-company">{job.company || "Unknown Company"}</span>
          <StatusBadge status={job.status} />
        </div>

        <div
          className="job-title"
          onClick={handleExpand}
          style={{ cursor: "none" }}
          data-interactive
        >
          {job.title}
        </div>

        <div className="job-meta">
          {job.location && <span className="job-meta-item">📍 {job.location}</span>}
          <span className="job-meta-item">⚡ {job.source}</span>
          <span className="job-meta-item">🕐 {formatDate(job.first_seen_at)}</span>
          {job.search_keyword && (
            <span className="job-meta-item" style={{ color: "var(--text-dim)" }}>
              🔍 {job.search_keyword}
            </span>
          )}
        </div>

        {tags.length > 0 && (
          <div className="job-tags">
            {tags.map((t) => (
              <span key={t} className="tag-chip">{t}</span>
            ))}
          </div>
        )}

        <div className="job-actions">
          <button
            className="btn"
            onClick={handleApprove}
            disabled={approving || job.status === "approved"}
            data-interactive
          >
            <span>{approving ? "BUILDING..." : "APPROVE"}</span>
          </button>
          <button
            className="btn btn-warn"
            onClick={() => handleAction("save")}
            disabled={job.status === "saved"}
            data-interactive
          >
            <span>SAVE</span>
          </button>
          <button
            className="btn btn-danger"
            onClick={() => handleAction("trash")}
            disabled={job.status === "trash"}
            data-interactive
          >
            <span>TRASH</span>
          </button>
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn"
            style={{ fontSize: "10px" }}
            data-interactive
          >
            <span>↗ VIEW</span>
          </a>
        </div>
      </div>

      {/* Packet expand panel */}
      <div className={`packet-panel${expanded ? " open" : ""}`}>
        <div className="packet-inner">
          <div className="packet-section-tag">— GENERATED PACKET —</div>

          {loadingPacket && (
            <div style={{ color: "var(--text-dim)", fontSize: 12 }}>Loading packet...</div>
          )}

          {packetError && !packet && (
            <div style={{ color: "var(--warn)", fontSize: 12 }}>{packetError}</div>
          )}

          {packet && (
            <>
              {packet.cover_letter_text ? (
                <div className="packet-cover">{packet.cover_letter_text}</div>
              ) : (
                <div style={{ color: "var(--text-dim)", fontSize: 12 }}>
                  Cover letter generating…
                </div>
              )}

              <div className="packet-email-row">
                {job.contact_email ? (
                  <>
                    <span className="packet-email-found">{job.contact_email}</span>
                    <button
                      className="btn btn-success"
                      onClick={handleSend}
                      disabled={sending}
                      data-interactive
                    >
                      <span>{sending ? "SENDING..." : "SEND APPLICATION"}</span>
                    </button>
                  </>
                ) : (
                  <span className="packet-email-missing">NO CONTACT EMAIL FOUND</span>
                )}
              </div>

              {sendMsg && (
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 11,
                    color: sendMsg.startsWith("Error") ? "var(--danger)" : "var(--success)",
                  }}
                >
                  {sendMsg}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
