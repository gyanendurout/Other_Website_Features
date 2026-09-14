import FeatureRows from "@/components/feature-rows";
import { search } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Search({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const results = q ? await search(q) : [];

  return (
    <div className="section" style={{ paddingTop: 40 }}>
      <div className="section-head">
        <h2>Search</h2>
        <span className="count mono">
          {q ? `${results.length} hits` : "SQLite FTS5"}
        </span>
      </div>

      <form action="/search" method="get" style={{ marginBottom: 26 }}>
        <input
          className="input"
          name="q"
          defaultValue={q ?? ""}
          placeholder="try: sso, countdown, warranty, carbon, reviews…"
          autoFocus
        />
      </form>

      {q ? (
        <FeatureRows features={results} showSite />
      ) : (
        <div className="empty">
          Full-text search across every feature name, description and evidence
          quote.
        </div>
      )}
    </div>
  );
}
