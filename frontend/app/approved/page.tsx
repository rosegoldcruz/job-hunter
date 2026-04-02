"use client";
import { useCallback, useEffect, useState } from "react";
import PageShell from "@/components/PageShell";
import JobCard from "@/components/JobCard";
import { api, Job } from "@/lib/api";

export default function ApprovedPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const j = await api.getJobs("approved");
      setJobs(j);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);

  const handleStatusChange = (id: number, status: string) =>
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, status } : j)));

  return (
    <PageShell page="approved">
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
              <div className="page-tag">// CLEARED FOR SEND</div>
              <div className="page-title">APPROVED</div>
            </div>
            {loading ? (
              <div style={{ color: "var(--text-dim)", fontSize: 12 }}>LOADING...</div>
            ) : visible.length === 0 ? (
              <div style={{ color: "var(--text-dim)", fontSize: 12, letterSpacing: "0.1em" }}>
                NO APPROVED JOBS YET
              </div>
            ) : (
              <div className="job-list">
                {visible.map((job) => (
                  <JobCard key={job.id} job={job} onStatusChange={handleStatusChange} />
                ))}
              </div>
            )}
          </>
        );
      }}
    </PageShell>
  );
}
