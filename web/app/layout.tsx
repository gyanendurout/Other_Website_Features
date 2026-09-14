import type { Metadata } from "next";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Nav from "./nav";
import "./globals.css";

const sans = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Feature Catalog",
  description:
    "Website features captured with Firecrawl and crawl4ai, extracted to SQLite, and pinned to the pixels they came from.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${mono.variable}`}>
        <header className="topbar">
          <div className="shell topbar-in">
            <a href="/" className="brand">
              <span className="brand-dot" />
              Feature Catalog
            </a>
            <Nav />
          </div>
        </header>
        <main className="shell">{children}</main>
        <footer className="shell">
          <div>
            Captured with self-hosted Firecrawl + crawl4ai · annotated with
            Playwright · served from Postgres and Supabase Storage
          </div>
        </footer>
      </body>
    </html>
  );
}
