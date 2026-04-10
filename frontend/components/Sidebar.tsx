"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const NAV = [
  {
    href: "/",
    label: "Enrich",
    icon: (
      <svg className="nav-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2">
        <circle cx="7" cy="5" r="2.5" />
        <path d="M2 12c0-2.76 2.24-5 5-5s5 2.24 5 5" />
        <path d="M10 2l1.5 1.5L10 5" />
        <path d="M10 2h2.5v2.5" />
      </svg>
    ),
  },
  {
    href: "/settings",
    label: "Settings",
    icon: (
      <svg className="nav-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2">
        <circle cx="7" cy="7" r="2" />
        <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.93 2.93l1.06 1.06M10.01 10.01l1.06 1.06M2.93 11.07l1.06-1.06M10.01 3.99l1.06-1.06" />
      </svg>
    ),
  },
];

export default function Sidebar({ isOpen, onClose }: Props) {
  const pathname = usePathname();

  return (
    <aside className={`sidebar${isOpen ? " mobile-open" : ""}`}>
      <div className="sidebar-logo">
        <svg className="sidebar-logo-icon" viewBox="0 0 28 28" fill="none">
          <polygon
            points="14,2 25,8 25,20 14,26 3,20 3,8"
            stroke="#00e5ff"
            strokeWidth="1.2"
            fill="rgba(0,229,255,0.06)"
          />
          <polygon
            points="14,7 20,10.5 20,17.5 14,21 8,17.5 8,10.5"
            stroke="#00e5ff"
            strokeWidth="0.8"
            fill="rgba(0,229,255,0.04)"
          />
        </svg>
        <span className="sidebar-wordmark">LEAD<br/>ENRICHER</span>
        <span className="sidebar-subtitle">CONTACT PIPELINE</span>
      </div>

      <nav className="sidebar-nav">
        {NAV.map(({ href, label, icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`nav-item${active ? " active" : ""}`}
              onClick={onClose}
            >
              {icon}
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="user-chip">
          <span className="pulse-dot" />
          OPERATOR
        </div>
      </div>
    </aside>
  );
}
