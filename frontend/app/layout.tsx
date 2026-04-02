import type { Metadata } from "next";
import "./globals.css";
import BackgroundCanvas from "@/components/BackgroundCanvas";
import CustomCursor from "@/components/CustomCursor";
import Sidebar from "@/components/Sidebar";
import StatusBar from "@/components/StatusBar";

export const metadata: Metadata = {
  title: "RESUMEBOT — Mission Control",
  description: "Personal job hunting dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="scanline" />
        <BackgroundCanvas />
        <CustomCursor />

        <div className="app-shell">
          <Sidebar />

          {/* Topbar + Main are injected by child pages via a shell wrapper */}
          {children}

          <StatusBar />
        </div>
      </body>
    </html>
  );
}
