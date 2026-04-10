"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, Lead, ParsedLead, EnrichmentStatus } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ViewFilter = "ALL" | "FOUND" | "NO_EMAIL" | "PENDING";

// ---------------------------------------------------------------------------
// Client-side TSV parser  (mirrors Python logic for instant preview)
// ---------------------------------------------------------------------------

const PHONE_RE = /(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/g;
const STATE_HEADER_RE = /^[A-Z][A-Z\s\-]{2,}$/;
const COL_HEADERS = new Set(["company", "business", "name", "company name", "company/city", "company + city"]);

function splitCompanyCity(raw: string): { company: string; city: string; ambiguous: boolean } {
  const s = raw.trim();
  const idx = s.lastIndexOf(",");
  if (idx !== -1) {
    return { company: s.slice(0, idx).trim(), city: s.slice(idx + 1).trim(), ambiguous: false };
  }
  return { company: s, city: "", ambiguous: true };
}

function isStateHeader(text: string): boolean {
  return STATE_HEADER_RE.test(text) && !/\d/.test(text);
}

function parseTsv(text: string): ParsedLead[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed.includes("\t") ? parseTabFormat(trimmed) : parseSmashed(trimmed);
}

function parseTabFormat(text: string): ParsedLead[] {
  const leads: ParsedLead[] = [];
  let state = "";
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\r$/, "");
    const cols = line.split("\t");
    if (!cols.some(c => c.trim())) continue;
    const first = cols[0].trim();
    const restEmpty = cols.slice(1).every(c => !c.trim());
    if (restEmpty && first && isStateHeader(first)) { state = toTitleCase(first); continue; }
    if (COL_HEADERS.has(first.toLowerCase())) continue;
    if (!first) continue;
    const phone = cols[1]?.trim() ?? "";
    const { company, city, ambiguous } = splitCompanyCity(first);
    leads.push({ company, city, state, phone, ambiguous });
  }
  return leads;
}

function parseSmashed(text: string): ParsedLead[] {
  const leads: ParsedLead[] = [];
  let state = "";
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\r$/, "").trim();
    if (!line) continue;
    if (isStateHeader(line) && !PHONE_RE.test(line)) { state = toTitleCase(line); PHONE_RE.lastIndex = 0; continue; }
    if (COL_HEADERS.has(line.toLowerCase())) continue;
    PHONE_RE.lastIndex = 0;
    const parts = line.split(PHONE_RE);
    let i = 0;
    while (i < parts.length) {
      const companyCity = parts[i].trim();
      const phone = i + 1 < parts.length ? parts[i + 1].trim() : "";
      i += 2;
      if (!companyCity) continue;
      const { company, city, ambiguous } = splitCompanyCity(companyCity);
      leads.push({ company, city, state, phone, ambiguous });
    }
  }
  return leads;
}

function toTitleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

// ---------------------------------------------------------------------------
// Status badge component
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "badge badge-pending",
    in_progress: "badge badge-in-progress",
    found: "badge badge-found",
    not_found: "badge badge-not-found",
  };
  const label: Record<string, string> = {
    pending: "PENDING",
    in_progress: "SCANNING...",
    found: "FOUND",
    not_found: "NOT FOUND",
  };
  return <span className={map[status] ?? "badge"}>{label[status] ?? status.toUpperCase()}</span>;
}

// ---------------------------------------------------------------------------
// Confidence bar component
// ---------------------------------------------------------------------------

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 60 ? "var(--success)" : value >= 30 ? "var(--warn)" : "var(--danger)";
  return (
    <div className="conf-bar-track">
      <div className="conf-bar-fill" style={{ width: `${value}%`, background: color }} />
      <span className="conf-bar-label">{value}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function LeadEnrichmentPage() {
  const [rawInput, setRawInput] = useState("");
  const [preview, setPreview] = useState<ParsedLead[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [enrichStatus, setEnrichStatus] = useState<EnrichmentStatus | null>(null);
  const [filter, setFilter] = useState<ViewFilter>("ALL");
  const [phase, setPhase] = useState<"input" | "running" | "done">("input");
  const [launching, setLaunching] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Live preview on input change ──────────────────────────────────────
  useEffect(() => {
    setPreview(parseTsv(rawInput));
  }, [rawInput]);

  // ── Enforce plain-text paste ──────────────────────────────────────────
  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    e.preventDefault();
    const plain = e.clipboardData.getData("text/plain");
    const ta = textareaRef.current!;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const next = rawInput.slice(0, start) + plain + rawInput.slice(end);
    setRawInput(next);
    // Restore cursor after React re-render
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = start + plain.length;
    });
  }, [rawInput]);

  // ── Poll enrichment status ────────────────────────────────────────────
  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const [status, rows] = await Promise.all([
          api.enrichmentStatus(),
          api.getLeads(),
        ]);
        setEnrichStatus(status);
        setLeads(rows);
        if (!status.enriching) {
          clearInterval(pollRef.current!);
          setPhase("done");
        }
      } catch { /* ignore poll errors */ }
    }, 2000);
  }, []);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── Launch enrichment ─────────────────────────────────────────────────
  const handleEnrich = useCallback(async () => {
    if (!preview.length) return;
    setLaunching(true);
    try {
      const res = await api.startEnrichment(rawInput);
      if (res.status === "started" || res.status === "already_running") {
        setPhase("running");
        const initial = await api.getLeads();
        setLeads(initial);
        startPolling();
      }
    } catch (err) {
      console.error("Enrichment launch failed:", err);
    } finally {
      setLaunching(false);
    }
  }, [rawInput, preview.length, startPolling]);

  // ── Clear ─────────────────────────────────────────────────────────────
  const handleClear = useCallback(async () => {
    if (pollRef.current) clearInterval(pollRef.current);
    await api.clearLeads().catch(() => {});
    setRawInput("");
    setPreview([]);
    setLeads([]);
    setEnrichStatus(null);
    setPhase("input");
  }, []);

  // ── Filtered leads ────────────────────────────────────────────────────
  const visibleLeads =
    filter === "FOUND" ? leads.filter(l => l.email)
    : filter === "NO_EMAIL" ? leads.filter(l => !l.email)
    : filter === "PENDING" ? leads.filter(l => l.status === "pending" || l.status === "in_progress")
    : leads;

  // ── Progress bar values ───────────────────────────────────────────────
  const progressPct = enrichStatus && enrichStatus.progress_total > 0
    ? Math.round((enrichStatus.progress_completed / enrichStatus.progress_total) * 100)
    : 0;

  return (
    <>
      <Topbar page="leads" search="" onSearch={() => {}} />
      <main className="main-content">

        {/* ── Page header ─────────────────────────────────────────────── */}
        <div className="page-header" style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div>
            <div className="page-tag">// ENRICHMENT ENGINE</div>
            <div className="page-title">LEAD ENRICHMENT</div>
          </div>
          {(phase !== "input" || leads.length > 0) && (
            <button className="btn btn-danger" onClick={handleClear} data-interactive>
              <span>CLEAR LEADS</span>
            </button>
          )}
        </div>

        {/* ══════════════════════════════════════════════════════════════
            INPUT SECTION
        ══════════════════════════════════════════════════════════════ */}
        <div className="lead-input-section">

          {/* Instructions box */}
          <div className="paste-instructions">
            <div className="paste-instructions-title">HOW TO PASTE YOUR LEADS</div>
            <ol className="paste-steps">
              <li>Open your Google Sheet</li>
              <li>Select your rows</li>
              <li>Press <kbd>CTRL</kbd>+<kbd>C</kbd> to copy</li>
              <li>Click inside the box below</li>
              <li>Press <kbd>CTRL</kbd>+<kbd>SHIFT</kbd>+<kbd>V</kbd> to paste as plain text</li>
            </ol>
            <div className="paste-warning">
              ⚠ Do NOT use <kbd>CTRL</kbd>+<kbd>V</kbd> — it pastes with formatting and breaks the parser.
              Use <kbd>CTRL</kbd>+<kbd>SHIFT</kbd>+<kbd>V</kbd> only.
            </div>
            <div className="paste-format-note">
              Both tab-separated (preferred) and formatting-stripped paste are handled automatically.
            </div>
          </div>

          {/* Paste textarea */}
          <textarea
            ref={textareaRef}
            className="lead-paste-area"
            rows={20}
            placeholder={"Paste your Google Sheets leads here...\n\nExpected format: Company, City [TAB] Phone Number\nState headers (e.g. ARIZONA) are auto-detected as section separators."}
            value={rawInput}
            onChange={e => setRawInput(e.target.value)}
            onPaste={handlePaste}
            spellCheck={false}
          />

          {/* Live preview */}
          {preview.length > 0 && (
            <div className="preview-section">
              <div className="preview-header">
                <span className="preview-label">
                  LIVE PREVIEW — <span style={{ color: "var(--accent)" }}>{preview.length}</span> LEADS DETECTED
                </span>
                {preview.some(l => l.ambiguous) && (
                  <span className="preview-warn-badge">
                    ⚠ {preview.filter(l => l.ambiguous).length} AMBIGUOUS
                  </span>
                )}
              </div>
              <div className="table-scroll-wrap">
                <table className="lead-table preview-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>COMPANY</th>
                      <th>CITY</th>
                      <th>STATE</th>
                      <th>PHONE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((lead, i) => (
                      <tr key={i} className={lead.ambiguous ? "row-ambiguous" : ""}>
                        <td className="td-num">{i + 1}</td>
                        <td>{lead.company || <span className="td-empty">—</span>}</td>
                        <td>{lead.city || <span className="td-empty">—</span>}</td>
                        <td>{lead.state || <span className="td-empty">—</span>}</td>
                        <td>{lead.phone || <span className="td-empty">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Launch button */}
          {preview.length > 0 && phase === "input" && (
            <div className="launch-row">
              <button
                className="btn btn-enrich"
                onClick={handleEnrich}
                disabled={launching}
                data-interactive
              >
                <span>
                  {launching ? "LAUNCHING..." : `PARSE & ENRICH  ${preview.length} LEADS  ▶`}
                </span>
              </button>
            </div>
          )}
        </div>

        {/* ══════════════════════════════════════════════════════════════
            ENRICHMENT RESULTS SECTION
        ══════════════════════════════════════════════════════════════ */}
        {(phase === "running" || phase === "done") && leads.length > 0 && (
          <div className="results-section">

            {/* Metrics row */}
            <div className="metrics-row" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
              <div className="metric-card">
                <div className="metric-label">Total Leads</div>
                <div className="metric-value">{enrichStatus?.total ?? leads.length}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Email Found</div>
                <div className="metric-value" style={{ color: "var(--success)" }}>
                  {enrichStatus?.found ?? 0}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Not Found</div>
                <div className="metric-value" style={{ color: "var(--danger)" }}>
                  {enrichStatus?.not_found ?? 0}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">In Progress</div>
                <div className="metric-value" style={{ color: "var(--warn)" }}>
                  {(enrichStatus?.pending ?? 0) + (enrichStatus?.in_progress ?? 0)}
                </div>
              </div>
            </div>

            {/* Progress bar */}
            {phase === "running" && (
              <div className="enrich-progress-wrap">
                <div className="enrich-progress-label">
                  <span className="status-running">ENRICHING</span>
                  <span style={{ color: "var(--text-dim)" }}>
                    {enrichStatus?.progress_completed ?? 0} / {enrichStatus?.progress_total ?? leads.length}
                  </span>
                </div>
                <div className="enrich-progress-track">
                  <div
                    className="enrich-progress-fill"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
            )}

            {/* Filter + export row */}
            <div className="results-toolbar">
              <div className="filter-row" style={{ marginBottom: 0 }}>
                {(["ALL", "FOUND", "NO_EMAIL", "PENDING"] as ViewFilter[]).map(f => (
                  <button
                    key={f}
                    className={`filter-chip${filter === f ? " active" : ""}`}
                    onClick={() => setFilter(f)}
                    data-interactive
                  >
                    {f === "NO_EMAIL" ? "NO EMAIL" : f === "PENDING" ? "IN PROGRESS" : f}
                  </button>
                ))}
              </div>
              <a
                href={api.exportLeadsCsv()}
                className="btn"
                download="leads_enriched.csv"
                data-interactive
              >
                <span>EXPORT CSV ↓</span>
              </a>
            </div>

            {/* Results table */}
            <div className="table-scroll-wrap">
              <table className="lead-table results-table">
                <thead>
                  <tr>
                    <th>COMPANY</th>
                    <th>CITY</th>
                    <th>STATE</th>
                    <th>PHONE</th>
                    <th>WEBSITE</th>
                    <th>EMAIL</th>
                    <th>CONTACT NAME</th>
                    <th>CONFIDENCE</th>
                    <th>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleLeads.map(lead => (
                    <tr
                      key={lead.id}
                      className={[
                        lead.ambiguous ? "row-ambiguous" : "",
                        lead.status === "found" ? "row-found" : "",
                      ].filter(Boolean).join(" ")}
                    >
                      <td className="td-company">{lead.company}</td>
                      <td>{lead.city || <span className="td-empty">—</span>}</td>
                      <td>{lead.state || <span className="td-empty">—</span>}</td>
                      <td>{lead.phone || <span className="td-empty">—</span>}</td>
                      <td>
                        {lead.website
                          ? <a href={lead.website} target="_blank" rel="noreferrer" className="td-link">{lead.website.replace(/^https?:\/\/(www\.)?/, "")}</a>
                          : <span className="td-empty">—</span>
                        }
                      </td>
                      <td>
                        {lead.email
                          ? <span className="td-email">{lead.email}</span>
                          : <span className="td-empty">—</span>
                        }
                      </td>
                      <td>
                        {lead.contact_name
                          ? <span>{lead.contact_name}</span>
                          : <span className="td-empty">—</span>
                        }
                      </td>
                      <td>
                        {lead.confidence > 0
                          ? <ConfidenceBar value={lead.confidence} />
                          : <span className="td-empty">—</span>
                        }
                      </td>
                      <td><StatusBadge status={lead.status} /></td>
                    </tr>
                  ))}
                  {visibleLeads.length === 0 && (
                    <tr>
                      <td colSpan={9} style={{ textAlign: "center", color: "var(--text-dim)", padding: "24px" }}>
                        NO LEADS MATCH THIS FILTER
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Flag notice */}
            {leads.some(l => l.ambiguous) && (
              <div className="ambiguous-notice">
                ⚠ Yellow rows had no comma in the Company+City field — city could not be auto-detected.
                Review these manually.
              </div>
            )}

          </div>
        )}

      </main>
    </>
  );
}
