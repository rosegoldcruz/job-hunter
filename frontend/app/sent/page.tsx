"use client";
import { useCallback, useEffect, useState } from "react";
import PageShell from "@/components/PageShell";
import { api, Job } from "@/lib/api";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function SentPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const j = await api.getJobs("applied");
      setJobs(j);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <PageShell page="sent">
      {(search) => {
        const q = search.toLowerCase();
        const visible = jobs.filter(
          (j) =>
            !q ||
            (j.company || "").toLowerCase().includes(q) ||
            j.title.toLowerCase().includes(q)
        );
        return (
          <>
            <div className="page-header">
              <div className="page-tag">// TRANSMITTED</div>
              <div className="page-title">SENT</div>
            </div>

            {loading ? (
              <div style={{ color: "var(--text-dim)", fontSize: 12 }}>LOADING...</div>
            ) : visible.length === 0 ? (
              <div style={{ color: "var(--text-dim)", fontSize: 12, letterSpacing: "0.1em" }}>
                NO APPLICATIONS SENT YET
              </div>
            ) : (
              <div className="job-list">
                {visible.map((job) => (
                  <div key={job.id} className="job-card">
                    <div className="job-card-body">
                      <div className="job-header">
                        <span className="job-company">{job.company || "Unknown Company"}</span>
                        <span className="badge badge-applied">SENT</span>
                      </div>
                      <div className="job-title">{job.title}</div>
                      <div className="job-meta">
                        {job.location && <span>📍 {job.location}</span>}
                        <span>⚡ {job.source}</span>
                        <span>📬 Sent {formatDate(job.last_seen_at)}</span>
                        {job.contact_email && (
                          <span style={{ color: "var(--accent)" }}>✉ {job.contact_email}</span>
                        )}
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <a
                          href={job.job_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn"
                          style={{ fontSize: "10px" }}
                          data-interactive
                        >
                          <span>↗ VIEW JOB</span>
                        </a>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        );
      }}
    </PageShell>
  );
}
