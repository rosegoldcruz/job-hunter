"use client";
import { useEffect, useState } from "react";
import PageShell from "@/components/PageShell";
import { api, Job } from "@/lib/api";

const COLUMNS: { key: string; label: string; color: string }[] = [
  { key: "new",             label: "NEW",         color: "var(--accent)" },
  { key: "approved",        label: "APPROVED",    color: "var(--success)" },
  { key: "saved",           label: "SAVED",       color: "var(--warn)" },
  { key: "applied",         label: "APPLIED",     color: "var(--accent2)" },
  { key: "manual_followup", label: "FOLLOWUP",    color: "var(--warn)" },
  { key: "trash",           label: "TRASHED",     color: "var(--danger)" },
];

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function PipelinePage() {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const j = await api.getJobs();
        setJobs(j);
      } catch {}
    };
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const byStatus = (status: string) =>
    jobs.filter((j) => j.status === status);

  return (
    <PageShell page="pipeline">
      {(search) => {
        const q = search.toLowerCase();
        const filtered = (status: string) =>
          byStatus(status).filter(
            (j) =>
              !q ||
              (j.company || "").toLowerCase().includes(q) ||
              j.title.toLowerCase().includes(q)
          );

        return (
          <>
            <div className="page-header">
              <div className="page-tag">// FLOW STATE</div>
              <div className="page-title">PIPELINE</div>
            </div>

            <div className="pipeline-grid">
              {COLUMNS.map(({ key, label, color }) => {
                const col = filtered(key);
                return (
                  <div key={key} className="pipeline-col">
                    <div className="pipeline-col-header" style={{ color }}>
                      {label}
                      <span style={{ marginLeft: 6, opacity: 0.5, color: "var(--text-dim)" }}>
                        ({col.length})
                      </span>
                    </div>
                    <div className="pipeline-col-body">
                      {col.map((job) => (
                        <div key={job.id} className="pipeline-card">
                          <div className="pipeline-card-company">
                            {job.company || "Unknown"}
                          </div>
                          <div className="pipeline-card-title">{job.title}</div>
                          <div className="pipeline-card-date">
                            {formatDate(job.first_seen_at)}
                          </div>
                        </div>
                      ))}
                      {col.length === 0 && (
                        <div style={{ color: "var(--text-dim)", fontSize: 10, padding: "4px 2px", letterSpacing: "0.08em" }}>
                          EMPTY
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        );
      }}
    </PageShell>
  );
}
