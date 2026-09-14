import Link from "next/link";
import { notFound } from "next/navigation";
import FeatureRows from "@/components/feature-rows";
import { getCategories, getFeatures, getPages, getSite, plateUrl } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function SitePage({
  params,
}: {
  params: Promise<{ domain: string }>;
}) {
  const { domain } = await params;
  const site = await getSite(decodeURIComponent(domain));
  if (!site) notFound();

  const [features, pages, cats] = await Promise.all([
    getFeatures(site.domain),
    getPages(site.domain),
    getCategories(site.domain),
  ]);
  const diffs = features.filter((f) => f.is_differentiator === 1);

  return (
    <>
      <div className="crumb">
        <Link href="/">Overview</Link> <span>/</span>
        <span className="mono">{site.domain}</span>
      </div>

      <section className="hero" style={{ paddingTop: 26 }}>
        <div className="eyebrow">{site.vertical ?? "site"}</div>
        <h1 className="display" style={{ fontSize: "clamp(2rem,1rem+3vw,3.6rem)" }}>
          {site.name ?? site.domain}
        </h1>
        {site.tagline ? <p className="lede">{site.tagline}</p> : null}
        {site.description ? (
          <p className="lede" style={{ fontSize: ".92rem" }}>
            {site.description}
          </p>
        ) : null}

        <div className="statrow">
          <div className="stat accent">
            <b className="mono">{features.length}</b>
            <span>Features</span>
          </div>
          <div className="stat">
            <b className="mono">{diffs.length}</b>
            <span>Differentiators</span>
          </div>
          <div className="stat">
            <b className="mono">{pages.length}</b>
            <span>Pages</span>
          </div>
          <div className="stat">
            <b className="mono">{cats.length}</b>
            <span>Categories</span>
          </div>
        </div>

        {site.business_model ? (
          <p className="lede mono" style={{ fontSize: ".82rem", marginTop: 18 }}>
            model: {site.business_model}
          </p>
        ) : null}
        {site.notes ? (
          <p className="lede" style={{ fontSize: ".85rem", color: "var(--text-faint)" }}>
            {site.notes}
          </p>
        ) : null}
      </section>

      {pages.length ? (
        <section className="section">
          <div className="section-head">
            <h2>Pages</h2>
            <span className="count mono">{pages.length}</span>
          </div>
          <div className="pagelist">
            {pages.map((p) => (
              <Link key={p.id} href={`/screens/${p.id}`} className="pcard">
                <div className="thumb">
                  {p.shot ? (
                    <img
                      src={plateUrl(p.shot) ?? ""}
                      alt={p.title ?? p.url}
                      loading="lazy"
                    />
                  ) : (
                    <div className="empty" style={{ fontSize: ".78rem" }}>
                      not annotated
                    </div>
                  )}
                </div>
                <div className="body">
                  <b>{p.page_type}</b>
                  <div className="mono">{p.url}</div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>Features</h2>
          <span className="count mono">{features.length}</span>
        </div>
        <div className="chips" style={{ marginBottom: 20 }}>
          {cats.map((c) => (
            <Link
              key={c.category}
              href={`/features?site=${site.domain}&cat=${encodeURIComponent(c.category)}`}
              className="chip"
            >
              {c.category}
              <span className="n mono">{c.n}</span>
            </Link>
          ))}
        </div>
        <FeatureRows features={features} />
      </section>
    </>
  );
}
