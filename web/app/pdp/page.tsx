import Link from "next/link";
import { pdpCategories, pdpSites, pdpStats, plateUrl } from "@/lib/pdp-db";

export const dynamic = "force-dynamic";

export default async function PdpIndex() {
  const [sites, stats, cats] = await Promise.all([
    pdpSites(),
    pdpStats(),
    pdpCategories(),
  ]);

  return (
    <>
      <section className="hero" style={{ paddingTop: 30 }}>
        <div className="eyebrow">product detail pages · 2026</div>
        <h1
          className="display"
          style={{ fontSize: "clamp(2rem,1rem+3vw,3.6rem)" }}
        >
          PDP Lab
        </h1>
        <p className="lede">
          One product page each from {stats.sites} storefronts across supplements,
          skincare, apparel, footwear, watches, bicycles and sporting goods. Every
          feature is circled on the pixels it came from and explained — the same
          treatment the paddle catalog gets, on a deliberately unrelated set of
          verticals.
        </p>
        <p className="pdp-note">
          This section reads its own Postgres schema (<span className="mono">pdp</span>),
          separate from the paddle catalog&rsquo;s. Nothing here is counted in
          Overview, Features, Screens, Compare, Gaps or Search, and nothing there
          is counted here.
        </p>
      </section>

      <div className="statrow">
        <div className="stat">
          <b>{stats.sites}</b>
          <span>storefronts</span>
        </div>
        <div className="stat">
          <b>{stats.features}</b>
          <span>features</span>
        </div>
        <div className="stat">
          <b>{stats.circled}</b>
          <span>circled on page</span>
        </div>
        <div className="stat">
          <b>{stats.canonical}</b>
          <span>canonical concepts</span>
        </div>
        <div className="stat">
          <b>{stats.categories}</b>
          <span>categories</span>
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <h2>The pages</h2>
          <Link href="/pdp/matrix" className="pdp-pill" data-on="true">
            Cross-site feature matrix →
          </Link>
        </div>

        {sites.length === 0 ? (
          <div className="empty">
            Catalog not built yet. Run the capture + extract + annotate pipeline
            with <span className="mono">CATALOG_DB=db/pdp.db</span>.
          </div>
        ) : (
          <div className="pdp-grid">
            {sites.map((s) => (
              <Link key={s.domain} href={`/pdp/${s.domain}`} className="pdp-card">
                <div className="pdp-shot">
                  {plateUrl(s.shot) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={plateUrl(s.shot) ?? ""}
                      alt={`${s.name ?? s.domain} product page`}
                      loading="lazy"
                    />
                  ) : (
                    <div className="pdp-none">
                      {s.attempted === 0 && s.feature_count > 0
                        ? "bot challenge — catalogued, not circled"
                        : "not annotated yet"}
                    </div>
                  )}
                </div>
                <div className="pdp-card-body">
                  <h3>{s.name ?? s.domain}</h3>
                  <div className="pdp-dom mono">{s.domain}</div>
                  <div className="pdp-vert">{s.vertical ?? "—"}</div>
                  <div className="pdp-figs">
                    <div>
                      <b>{s.feature_count}</b>
                      <span>features</span>
                    </div>
                    <div>
                      <b>{s.circled}</b>
                      <span>circled</span>
                    </div>
                    <div>
                      <b>
                        {s.feature_count
                          ? Math.round((s.circled / s.feature_count) * 100)
                          : 0}
                        %
                      </b>
                      <span>hit rate</span>
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {cats.length ? (
        <div className="section">
          <div className="section-head">
            <h2>Where the features sit</h2>
            <span className="count mono">{cats.length} categories</span>
          </div>
          <div className="chips">
            {cats.map((c) => (
              <span key={c.category} className="chip">
                {c.category}
                <b className="mono" style={{ marginLeft: 6, color: "var(--signal)" }}>
                  {c.n}
                </b>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}
