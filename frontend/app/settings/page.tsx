"use client";
import PageShell from "@/components/PageShell";

const ENV_VARS = [
  { key: "TELEGRAM_BOT_TOKEN", desc: "Telegram bot token from @BotFather", required: true },
  { key: "TELEGRAM_CHAT_ID", desc: "Your Telegram numeric chat ID", required: true },
  { key: "EMAIL_USER", desc: "SMTP sender email address", required: true },
  { key: "EMAIL_PASSWORD", desc: "App password for SMTP", required: true },
  { key: "RESUME_PATH", desc: "Absolute path to your .docx or .txt resume", required: true },
  { key: "CANDIDATE_NAME", desc: "Your full name (used in cover letters)", required: false },
  { key: "CANDIDATE_EMAIL", desc: "Your contact email", required: false },
  { key: "CANDIDATE_PHONE", desc: "Your phone number", required: false },
  { key: "CANDIDATE_CITY", desc: "Your city (e.g. Phoenix, AZ)", required: false },
  { key: "DATABASE_PATH", desc: "SQLite database path (default: ./data/resumebot.sqlite3)", required: false },
  { key: "OUTPUT_DIR", desc: "Output directory for generated packets (default: ./output)", required: false },
  { key: "INDEED_LOCATION", desc: "Indeed location filter (default: Remote)", required: false },
  { key: "CRAIGSLIST_REGION", desc: "Craigslist region slug (default: phoenix)", required: false },
  { key: "MAX_RESULTS_PER_QUERY", desc: "Max results per search query (default: 5)", required: false },
  { key: "HEADLESS", desc: "Run browser headless (default: true)", required: false },
];

export default function SettingsPage() {
  return (
    <PageShell page="settings">
      {() => (
        <>
          <div className="page-header">
            <div className="page-tag">// CONFIGURATION</div>
            <div className="page-title">SETTINGS</div>
          </div>

          <div style={{ maxWidth: 640 }}>
            <div className="resume-card" style={{ marginBottom: 24 }}>
              <div className="metric-label" style={{ marginBottom: 12 }}>
                API ENDPOINT
              </div>
              <div style={{ color: "var(--accent)", fontSize: 13 }}>
                {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
              </div>
              <div style={{ color: "var(--text-dim)", fontSize: 11, marginTop: 4 }}>
                Configure via NEXT_PUBLIC_API_URL in frontend/.env.local
              </div>
            </div>

            <div className="resume-card">
              <div className="metric-label" style={{ marginBottom: 16 }}>
                REQUIRED ENV VARS — edit <span style={{ color: "var(--accent)" }}>.env</span> at project root
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {ENV_VARS.map(({ key, desc, required }) => (
                  <div key={key} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 10 }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 3 }}>
                      <span style={{ color: required ? "var(--accent)" : "var(--text)", fontSize: 12, letterSpacing: "0.05em" }}>
                        {key}
                      </span>
                      {required && (
                        <span className="badge badge-new" style={{ fontSize: 9 }}>REQUIRED</span>
                      )}
                    </div>
                    <div style={{ color: "var(--text-dim)", fontSize: 11 }}>{desc}</div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ marginTop: 20, color: "var(--text-dim)", fontSize: 11, lineHeight: 1.8 }}>
              <div>1. Copy <span style={{ color: "var(--accent)" }}>.env.example</span> → <span style={{ color: "var(--accent)" }}>.env</span></div>
              <div>2. Fill in all required values</div>
              <div>3. Restart the API server</div>
              <div>4. Upload your resume via the Resume page</div>
              <div>5. Click RUN SCRAPE to populate the job queue</div>
            </div>
          </div>
        </>
      )}
    </PageShell>
  );
}
