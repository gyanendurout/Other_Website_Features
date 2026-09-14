"use client";

/**
 * What the reader sees when a page's queries fail.
 *
 * Next redacts server error messages in production and hands the browser a
 * digest instead — a hash with no information in it. Unhandled, that renders as
 * "Application error: a server-side exception has occurred", which is the same
 * screen for a missing environment variable, a rejected password, an unapplied
 * schema and a genuine bug. Diagnosing the first deployment of this app cost
 * several rounds precisely because every cause produced that one sentence.
 *
 * The digest stays redacted here too — that is the framework's decision and a
 * reasonable one. What this adds is the next step: /api/health runs the same
 * connection and is allowed to say what happened.
 */

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Server-side causes are already in the platform log; this surfaces the
  // client-side ones, which otherwise vanish silently.
  useEffect(() => {
    console.error("catalog page failed to render:", error);
  }, [error]);

  return (
    <div className="section" style={{ paddingTop: 40, maxWidth: "70ch" }}>
      <p className="eyebrow">Page failed to render</p>
      <h1 className="display" style={{ maxWidth: "22ch" }}>
        This page could not <em>reach its data</em>.
      </h1>

      <p className="lede">
        Every page here reads Postgres on Supabase and serves its screenshots
        from Supabase Storage. When the database is unreachable or refuses the
        connection, the page has nothing to render and Next replaces the error
        with a digest, so this screen cannot tell you which of those happened.
      </p>

      <p className="lede">
        <a href="/api/health" style={{ color: "var(--signal)" }}>
          /api/health
        </a>{" "}
        runs the same connection and reports the cause — whether{" "}
        <code className="mono">DATABASE_URL</code> is present, whether it reached
        the transaction pooler, and what Postgres said if it refused.
      </p>

      <div
        style={{
          marginTop: 28,
          padding: "18px 20px",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "var(--r-md)",
        }}
      >
        <p className="eyebrow" style={{ marginBottom: 10 }}>
          Most likely, in order
        </p>
        <ol
          className="mono"
          style={{
            margin: 0,
            paddingLeft: "1.4em",
            fontSize: "0.84rem",
            lineHeight: 1.9,
            color: "var(--text-dim)",
          }}
        >
          <li>DATABASE_URL is not set for this environment</li>
          <li>it was set after this deployment was built — redeploy</li>
          <li>the password is wrong, or is a different role&apos;s</li>
          <li>the schema was never applied to this project</li>
        </ol>
      </div>

      <p style={{ marginTop: 28, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button className="toggle" onClick={reset}>
          Try this page again
        </button>
        <a className="toggle" href="/api/health">
          Open /api/health
        </a>
      </p>

      {error.digest ? (
        <p
          className="mono"
          style={{
            marginTop: 24,
            fontSize: "0.76rem",
            color: "var(--text-faint)",
          }}
        >
          digest {error.digest} — quote this to find the matching entry in the
          platform log
        </p>
      ) : null}
    </div>
  );
}
