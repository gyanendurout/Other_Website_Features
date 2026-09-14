import Link from "next/link";
import FeatureRows from "@/components/feature-rows";
import { getCategories, getFeatures, getSites } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Features({
  searchParams,
}: {
  searchParams: Promise<{ cat?: string; site?: string; diff?: string }>;
}) {
  const sp = await searchParams;
  const [sites, cats, allFeatures] = await Promise.all([
    getSites(),
    getCategories(sp.site),
    getFeatures(sp.site),
  ]);

  let features = allFeatures;
  if (sp.cat) features = features.filter((f) => (f.category ?? "uncategorised") === sp.cat);
  if (sp.diff === "1") features = features.filter((f) => f.is_differentiator === 1);

  const qs = (patch: Record<string, string | undefined>) => {
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries({ ...sp, ...patch })) {
      if (v) next[k] = v;
    }
    const s = new URLSearchParams(next).toString();
    return s ? `/features?${s}` : "/features";
  };

  return (
    <div className="section" style={{ paddingTop: 40 }}>
      <div className="section-head">
        <h2>Features</h2>
        <span className="count mono">{features.length} shown</span>
      </div>

      <div style={{ display: "grid", gap: 14, marginBottom: 24 }}>
        <div className="chips">
          <Link href={qs({ site: undefined })} className="chip" data-on={!sp.site}>
            all sites
          </Link>
          {sites.map((s) => (
            <Link
              key={s.id}
              href={qs({ site: s.domain })}
              className="chip"
              data-on={sp.site === s.domain}
            >
              {s.domain}
              <span className="n mono">{s.feature_count}</span>
            </Link>
          ))}
        </div>

        <div className="chips">
          <Link href={qs({ cat: undefined })} className="chip" data-on={!sp.cat}>
            all categories
          </Link>
          {cats.map((c) => (
            <Link
              key={c.category}
              href={qs({ cat: c.category })}
              className="chip"
              data-on={sp.cat === c.category}
            >
              {c.category}
              <span className="n mono">{c.n}</span>
            </Link>
          ))}
        </div>

        <div className="chips">
          <Link
            href={qs({ diff: sp.diff === "1" ? undefined : "1" })}
            className="chip"
            data-on={sp.diff === "1"}
          >
            ★ differentiators only
          </Link>
        </div>
      </div>

      <FeatureRows features={features} showSite={!sp.site} />
    </div>
  );
}
