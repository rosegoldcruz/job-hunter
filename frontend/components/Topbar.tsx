"use client";
import { useEffect, useState } from "react";
import { api, Stats } from "@/lib/api";

interface Props {
  page: string;
  search: string;
  onSearch: (v: string) => void;
}

export default function Topbar({ page, search, onSearch }: Props) {
  const [clock, setClock] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [scraping, setScraping] = useState(false);

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
    const load = async () => {
      try {
        const s = await api.getStats();
        setStats(s);
        setScraping(s.scraper_running);
      } catch {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const runScrape = async () => {
    if (scraping) return;
    setScraping(true);
    try {
      await api.triggerScrape();
    } catch {}
  };

  return (
    <header className="topbar">
      <div className="breadcrumb">
        RESUMEBOT / <span>{page.toUpperCase()}</span>
      </div>

      <div className="topbar-search">
        <input
          type="text"
          className="search-input"
          placeholder="SEARCH COMPANY / TITLE..."
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>

      <div className="topbar-right">
        {stats && (
          <div className="topbar-stats">
            {stats.new} NEW · {stats.approved} PENDING · {stats.applied} SENT
          </div>
        )}

        <button
          className="btn btn-magenta"
          onClick={runScrape}
          disabled={scraping}
          data-interactive
        >
          <span>{scraping ? "RUNNING..." : "RUN SCRAPE"}</span>
        </button>

        <div className="topbar-clock">{clock}</div>
      </div>
    </header>
  );
}
