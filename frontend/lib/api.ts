// Empty string = relative URLs — proxied to FastAPI via Next.js rewrites.
// Set NEXT_PUBLIC_API_URL only if running the frontend on a separate host.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export interface Job {
  id: number;
  source: string;
  external_id: string | null;
  title: string;
  company: string | null;
  location: string | null;
  job_url: string;
  description: string | null;
  raw_text: string | null;
  contact_email: string | null;
  search_keyword: string | null;
  discovered_at: string;
  first_seen_at: string;
  last_seen_at: string;
  status: string;
  telegram_message_id: number | null;
  applied_at: string | null;
  notes: string | null;
}

export interface Packet {
  id: number;
  job_id: number;
  resume_output_path: string | null;
  cover_letter_path: string | null;
  cover_letter_text: string | null;
  created_at: string;
  final_status: string;
}

export interface Stats {
  new: number;
  saved: number;
  approved: number;
  trash: number;
  applied: number;
  manual_followup: number;
  scraper_running: boolean;
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Lead enrichment types
// ---------------------------------------------------------------------------

export interface ParsedLead {
  company: string;
  city: string;
  state: string;
  phone: string;
  ambiguous: boolean;
}

export interface Lead {
  id: number;
  company: string;
  city: string;
  state: string;
  phone: string;
  website: string | null;
  email: string | null;
  contact_name: string | null;
  confidence: number;
  status: "pending" | "in_progress" | "found" | "not_found";
  ambiguous: number; // 0 | 1 from SQLite
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface EnrichmentStatus {
  total: number;
  pending: number;
  in_progress: number;
  found: number;
  not_found: number;
  enriching: boolean;
  progress_total: number;
  progress_completed: number;
  last_error: string | null;
}

// ---------------------------------------------------------------------------

export const api = {
  getJobs: (status?: string) =>
    req<Job[]>(`/api/jobs${status ? `?status=${status}` : ""}`),

  getStats: () => req<Stats>("/api/stats"),

  triggerScrape: () => req<{ status: string }>("/api/scrape", { method: "POST" }),

  scrapeStatus: () =>
    req<{ running: boolean; last_result: unknown; last_error: string | null }>(
      "/api/scrape/status"
    ),

  approveJob: (id: number) =>
    req<{ status: string }>(`/api/jobs/${id}/approve`, { method: "POST" }),

  trashJob: (id: number) =>
    req<{ status: string }>(`/api/jobs/${id}/trash`, { method: "POST" }),

  saveJob: (id: number) =>
    req<{ status: string }>(`/api/jobs/${id}/save`, { method: "POST" }),

  getPacket: (id: number) =>
    req<Job & { packet: Packet }>(`/api/jobs/${id}/packet`),

  sendJob: (id: number) =>
    req<{ status: string }>(`/api/jobs/${id}/send`, { method: "POST" }),

  getResume: () =>
    req<{ path: string; filename: string; exists: boolean; size_bytes: number }>(
      "/api/resume"
    ),

  uploadResume: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/api/resume`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // ── Lead enrichment ────────────────────────────────────────────────────

  parseLeads: (tsv: string) =>
    req<ParsedLead[]>("/api/leads/parse", {
      method: "POST",
      body: JSON.stringify({ tsv }),
    }),

  startEnrichment: (tsv: string) =>
    req<{ status: string; total: number }>("/api/leads/enrich", {
      method: "POST",
      body: JSON.stringify({ tsv }),
    }),

  getLeads: (status?: string) =>
    req<Lead[]>(`/api/leads${status ? `?status=${status}` : ""}`),

  enrichmentStatus: () =>
    req<EnrichmentStatus>("/api/leads/enrich/status"),

  exportLeadsCsv: () => `${BASE}/api/leads/export`,

  clearLeads: () =>
    req<{ status: string }>("/api/leads", { method: "DELETE" }),
};
