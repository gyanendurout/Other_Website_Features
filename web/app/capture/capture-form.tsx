"use client";

import { useCallback, useEffect, useState } from "react";

type Job = {
  id: number;
  url: string;
  domain: string | null;
  site_name: string | null;
  stage: string;
  status: string;
  message: string | null;
  pages_found: number;
  pages_scraped: number;
  pages_failed: number;
  created_at: string;
  updated_at: string;
};

const STAGES = [
  "queued",
  "discovering",
  "scraping",
  "awaiting_extraction",
  "extracted",
  "annotated",
];

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued",
  discovering: "Finding key pages",
  scraping: "Scraping",
  awaiting_extraction: "Ready for extraction",
  extracted: "Features extracted",
  annotated: "Screenshots annotated",
  failed: "Failed",
};

/**
 * Client-side capture form and job list.
 *
 * This must stay free of any `@/lib/db` import: that module pulls in the
 * `postgres` package, which is Node-only and cannot be bundled for the
 * browser. `readOnly` is therefore read from `@/lib/db` in the parent server
 * component (page.tsx) and passed down as a plain prop.
 */
export default function CaptureForm({ readOnly }: { readOnly: boolean }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/capture", { cache: "no-store" });
      const j = await r.json();
      setJobs(j.jobs ?? []);
    } catch {
      /* transient - the next poll will pick it up */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, name }),
      });
      const j = await r.json();
      if (!r.ok) setError(j.error ?? "Could not start capture.");
      else {
        setUrl("");
        setName("");
        load();
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const active = jobs.filter((j) => j.status === "running").length;

  return (
    <>
      <div className="section-head">
        <h2>Capture a site</h2>
        <span className="count mono">
          {active ? `${active} running` : `${jobs.length} jobs`}
        </span>
      </div>

      {readOnly ? (
        <div
          className="lede"
          style={{
            fontSize: ".85rem",
            marginTop: 0,
            padding: "12px 16px",
            border: "1px solid var(--line)",
            borderRadius: "var(--r-md)",
            background: "var(--surface)",
          }}
        >
          <strong>This deployment is read-only.</strong> Capture runs the
          Firecrawl + crawl4ai + Playwright pipeline locally (Python and
          Docker), which cannot run on Vercel. Run{" "}
          <span className="mono">scripts/capture.py</span> on the local
          machine, then publish the results here with{" "}
          <span className="mono">scripts/publish.py</span>.
        </div>
      ) : (
        <>
          <p className="lede" style={{ marginTop: 0 }}>
            Paste a URL. Firecrawl maps the site, picks a representative
            homepage, collection/pricing and product/feature page, and
            scrapes each to clean markdown.
          </p>

          <form
            onSubmit={submit}
            style={{ display: "grid", gap: 12, maxWidth: 780 }}
          >
            <input
              className="input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              required
            />
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <input
                className="input"
                style={{ flex: "1 1 240px" }}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Display name (optional)"
              />
              <button
                className="toggle"
                data-on="true"
                disabled={busy}
                type="submit"
              >
                {busy ? "Starting…" : "Start capture"}
              </button>
            </div>
            {error ? (
              <div
                style={{
                  color: "var(--signal)",
                  fontSize: ".85rem",
                  border: "1px solid var(--signal-line)",
                  background: "var(--signal-soft)",
                  padding: "10px 14px",
                  borderRadius: "var(--r-md)",
                }}
              >
                {error}
              </div>
            ) : null}
          </form>

          <div
            className="lede"
            style={{
              fontSize: ".85rem",
              marginTop: 18,
              padding: "12px 16px",
              border: "1px solid var(--line)",
              borderRadius: "var(--r-md)",
              background: "var(--surface)",
            }}
          >
            <strong>What this does and does not do.</strong> Capture runs
            crawl and scrape end to end. Turning markdown into structured
            features is a reading step, and this stack has no LLM key wired
            in — so jobs stop at{" "}
            <span className="mono">awaiting_extraction</span> with the
            markdown saved. Ask Claude to extract that site, and the features
            plus annotated screenshots land in the catalog.
          </div>
        </>
      )}

      <div className="section-head" style={{ marginTop: 44 }}>
        <h2 style={{ fontSize: "1.15rem" }}>Jobs</h2>
      </div>

      {jobs.length === 0 ? (
        <div className="empty">No capture jobs yet.</div>
      ) : (
        <div className="flist">
          {jobs.map((j) => {
            const idx = STAGES.indexOf(j.stage);
            const pct =
              j.status === "failed"
                ? 100
                : Math.max(6, ((idx + 1) / STAGES.length) * 100);
            return (
              <div key={j.id} className="frow" style={{ gridTemplateColumns: "1fr auto" }}>
                <div style={{ minWidth: 0 }}>
                  <h4>
                    {j.site_name || j.domain || j.url}{" "}
                    <span className="mono" style={{ color: "var(--text-faint)", fontSize: ".78rem" }}>
                      #{j.id}
                    </span>
                  </h4>
                  <div className="desc mono" style={{ wordBreak: "break-all" }}>
                    {j.url}
                  </div>

                  <div
                    style={{
                      height: 5,
                      borderRadius: 3,
                      background: "var(--surface-3)",
                      marginTop: 12,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${pct}%`,
                        background:
                          j.status === "failed" ? "var(--warn)" : "var(--signal)",
                        transition: "width .4s var(--ease)",
                      }}
                    />
                  </div>

                  <div style={{ marginTop: 9, fontSize: ".8rem", color: "var(--text-dim)" }}>
                    {j.message ?? STAGE_LABEL[j.stage] ?? j.stage}
                    {j.pages_found ? (
                      <span className="mono" style={{ color: "var(--text-faint)" }}>
                        {" "}· {j.pages_scraped}/{j.pages_found} pages
                        {j.pages_failed ? ` · ${j.pages_failed} failed` : ""}
                      </span>
                    ) : null}
                  </div>
                </div>

                <div className="meta">
                  <span
                    className="tag"
                    data-tier={
                      j.status === "failed"
                        ? "addon"
                        : j.stage === "annotated"
                        ? "free"
                        : j.status === "running"
                        ? "business"
                        : "enterprise"
                    }
                  >
                    {STAGE_LABEL[j.stage] ?? j.stage}
                  </span>
                  {j.domain ? (
                    <a href={`/sites/${j.domain}`} className="chip">
                      open site
                    </a>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
