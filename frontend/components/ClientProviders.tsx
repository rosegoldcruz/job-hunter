"use client";
import { useState } from "react";
import { MobileNavContext } from "./MobileSidebarContext";
import Sidebar from "./Sidebar";

/**
 * Renders as a React Context.Provider — no DOM wrapper element — so Sidebar
 * and the page children are direct children of .app-shell and land correctly
 * in their CSS grid areas.
 */
export default function ClientProviders({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const toggle = () => setIsOpen((v) => !v);
  const close = () => setIsOpen(false);

  return (
    <MobileNavContext.Provider value={{ isOpen, toggle, close }}>
      <Sidebar isOpen={isOpen} onClose={close} />
      {/* Fixed backdrop — out of grid flow, overlays everything */}
      {isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={close}
          aria-hidden="true"
        />
      )}
      {children}
    </MobileNavContext.Provider>
  );
}
