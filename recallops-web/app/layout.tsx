import type { Metadata } from "next";
// Fonts are bundled from npm, so the demo works on bad venue Wi-Fi.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: { default: "RecallOps", template: "%s – RecallOps" },
  description: "On-call incident triage that remembers past outages, including the fixes that failed.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-page font-sans text-base text-ink antialiased">
        <Nav />
        <main className="mx-auto max-w-page px-4 pb-16 pt-20 sm:px-8">{children}</main>
      </body>
    </html>
  );
}
