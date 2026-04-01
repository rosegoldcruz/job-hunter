"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import PageShell from "@/components/PageShell";
import JobCard from "@/components/JobCard";
import { api, Job, Stats } from "@/lib/api";

const FILTERS = ["ALL", "NEW", "APPROVED", "SAVED", "TRASHED"] as const;
type Filter = (typeof FILTERS)[number];

function statusFromFilter(f: Filter): string | undefined {
  if (f === "ALL") return undefined;
  if (f === "TRASHED") return "trash";
  return f.toLowerCase();
}

export default function QueuePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(async () => {
    try {
      const [j, s] = await Promise.all([api.getJobs(), api.getStats()]);
      setJobs(j);
      setStats(s);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 15000);
    return () => clearInterval(id);
  }, [loadAll]);

  const handleStatusChange = (id: number, status: string) => {
    setJobs((prev) =>
      prev.map((j) => (j.id === id ? { ...j, status } : j))
    );
  };

  return (
    <PageShell page="queue">
      {(search) => {
        const filterStatus = statusFromFilter(filter);
        const visible = jobs.filter((j) => {
          const matchStatus = !filterStatus || j.status === filterStatus;
          const q = search.toLowerCase();
          const matchSearch =
            !q ||
            (j.company || "").toLowerCase().includes(q) ||
            j.title.toLowerCase().includes(q) ||
            (j.location || "").toLowerCase().includes(q);
          return matchStatus && matchSearch;
        });

        const today = new Date().toDateString();
        const newToday = jobs.filter(
          (j) => j.status === "new" && new Date(j.first_seen_at).toDateString() === today
        ).length;
        const approvalRate =
          jobs.length > 0
            ? Math.round(
                (jobs.filter((j) => ["approved", "applied"].includes(j.status)).length /
                  jobs.length) *
                  100
              )
            : 0;
        const sentWeek = jobs.filter((j) => {
          if (j.status !== "applied") return false;
          const d = new Date(j.last_seen_at);
          const week = Date.now() - 7 * 86400000;
          return d.getTime() > week;
        }).length;

        return (
          <>
            <div className="page-header">
              <div className="page-tag">// INCOMING</div>
              <div className="page-title">JOB QUEUE</div>
            </div>

            <div className="metrics-row">
              <div className="metric-card">
                <div className="metric-label">Total Found</div>
                <div className="metric-value">{jobs.length}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">New Today</div>
                <div className="metric-value">{newToday}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Approval Rate</div>
                <div className="metric-value">{approvalRate}%</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Sent This Week</div>
                <div className="metric-value">{sentWeek}</div>
              </div>
            </div>

            <div className="filter-row">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  className={`filter-chip${filter === f ? " active" : ""}`}
                  onClick={() => setFilter(f)}
                  data-interactive
                >
                  {f}
                </button>
              ))}
            </div>

            {loading ? (
              <div style={{ color: "var(--text-dim)", fontSize: 12, letterSpacing: "0.1em" }}>
                LOADING...
              </div>
            ) : visible.length === 0 ? (
              <div style={{ color: "var(--text-dim)", fontSize: 12, letterSpacing: "0.1em" }}>
                NO JOBS FOUND — RUN SCRAPE TO POPULATE
              </div>
            ) : (
              <div className="job-list">
                {visible.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    onStatusChange={handleStatusChange}
                  />
                ))}
              </div>
            )}
          </>
        );
      }}
    </PageShell>
  );
}
