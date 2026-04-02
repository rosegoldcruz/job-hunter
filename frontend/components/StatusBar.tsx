"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const SESSION_ID = Array.from({ length: 8 }, () =>
  Math.floor(Math.random() * 16).toString(16)
).join("");

export default function StatusBar() {
  const [scraping, setScraping] = useState(false);
  const [clock, setClock] = useState("");

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      const pad = (n: number) => String(n).padStart(2, "0");
      setClock(`${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await api.scrapeStatus();
        setScraping(s.running);
      } catch {}
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <footer className="statusbar">
      <div className="statusbar-segment">
        <span className="pulse-dot" />
        <span className="status-nominal">SYSTEM: NOMINAL</span>
      </div>

      <div className="statusbar-divider" />

      <div className="statusbar-segment">
        {scraping ? (
          <span className="status-running">SCRAPER: RUNNING...</span>
        ) : (
          <span>SCRAPER: IDLE</span>
        )}
      </div>

      <div className="statusbar-divider" />

      <div className="statusbar-segment">
        SESSION: {SESSION_ID.toUpperCase()}
      </div>

      <div style={{ marginLeft: "auto" }} className="statusbar-segment">
        {clock}
      </div>
    </footer>
  );
}
