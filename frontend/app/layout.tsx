import type { Metadata } from "next";
import "./globals.css";
import BackgroundCanvas from "@/components/BackgroundCanvas";
import CustomCursor from "@/components/CustomCursor";
import ClientProviders from "@/components/ClientProviders";
import StatusBar from "@/components/StatusBar";

export const metadata: Metadata = {
  title: "LEAD ENRICHMENT — Mission Control",
  description: "Lead enrichment and contact data pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      </head>
      <body>
        <div className="scanline" />
        <BackgroundCanvas />
        <CustomCursor />

        <div className="app-shell">
          {/*
            ClientProviders renders as a React Context.Provider (no DOM wrapper),
            so Sidebar + page children land as direct grid children of .app-shell.
          */}
          <ClientProviders>
            {children}
          </ClientProviders>

          <StatusBar />
        </div>
      </body>
    </html>
  );
}
