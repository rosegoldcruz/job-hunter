"use client";
import { useEffect, useRef, useState } from "react";
import { api, Stats } from "@/lib/api";
import { useMobileNav } from "./MobileSidebarContext";

interface Props {
  page: string;
  search: string;
  onSearch: (v: string) => void;
}

export default function Topbar({ page, search, onSearch }: Props) {
  const [clock, setClock] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [scraping, setScraping] = useState(false);
  const [searchExpanded, setSearchExpanded] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const { toggle } = useMobileNav();

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

  const openSearch = () => {
    setSearchExpanded(true);
    setTimeout(() => searchRef.current?.focus(), 50);
  };

  const closeSearch = () => {
    setSearchExpanded(false);
    onSearch("");
  };

  return (
    <header className="topbar">
      {/* ── Hamburger — mobile only ───────────────────────────────── */}
      <button
        className="hamburger-btn"
        onClick={toggle}
        aria-label="Toggle navigation"
        data-interactive
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 5h16M2 10h16M2 15h16" />
        </svg>
      </button>

      {/* ── Breadcrumb — hidden when mobile search is expanded ───── */}
      <div className={`breadcrumb${searchExpanded ? " hide-mobile" : ""}`}>
        RESUMEBOT / <span>{page.toUpperCase()}</span>
      </div>

      {/* ── Desktop search ──────────────────────────────────────── */}
      <div className="topbar-search">
        <input
          type="text"
          className="search-input"
          placeholder="SEARCH COMPANY / TITLE..."
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>

      {/* ── Mobile search overlay ────────────────────────────────── */}
      {searchExpanded && (
        <div className="mobile-search-overlay">
          <input
            ref={searchRef}
            type="text"
            className="search-input mobile-search-input"
            placeholder="SEARCH..."
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            autoComplete="off"
          />
          <button className="mobile-search-close" onClick={closeSearch} data-interactive>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 2l12 12M14 2L2 14" />
            </svg>
          </button>
        </div>
      )}

      {/* ── Right side ───────────────────────────────────────────── */}
      <div className={`topbar-right${searchExpanded ? " hide-mobile" : ""}`}>
        {stats && (
          <div className="topbar-stats">
            {stats.new} NEW · {stats.approved} PENDING · {stats.applied} SENT
          </div>
        )}

        {/* Search icon — mobile only */}
        <button
          className="topbar-search-icon"
          onClick={openSearch}
          aria-label="Search"
          data-interactive
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="6.5" cy="6.5" r="4.5" />
            <path d="M10.5 10.5L14 14" />
          </svg>
        </button>

        <button
          className="btn btn-magenta topbar-scrape-btn"
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
