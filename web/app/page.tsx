import Link from "next/link";
import { getCategories, getPages, getSites, getStats, plateUrl } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [stats, sites, cats, pages] = await Promise.all([
    getStats(),
    getSites(),
    getCategories(),
    getPages(),
  ]);

  return (
    <>
      <section className="hero">
        <div className="eyebrow">Competitive feature intelligence</div>
        <h1 className="display">
          What other <em>products</em> actually ship.
        </h1>
        <p className="lede">
          Pages are crawled with self-hosted Firecrawl and crawl4ai, reduced to
          clean markdown, and read into a structured catalog. Every feature keeps
          a verbatim quote, and most are pinned to the exact pixels they came
          from.
        </p>

        <div className="statrow">
          <div className="stat">
            <b className="mono">{stats.sites}</b>
            <span>Sites</span>
          </div>
          <div className="stat accent">
            <b className="mono">{stats.features}</b>
            <span>Features</span>
          </div>
          <div className="stat">
            <b className="mono">{stats.pages}</b>
            <span>Pages</span>
          </div>
          <div className="stat">
            <b className="mono">{stats.annotated}</b>
            <span>Pinned to pixels</span>
          </div>
          <div className="stat">
            <b className="mono">{stats.categories}</b>
            <span>Categories</span>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Sites</h2>
          <span className="count mono">{sites.length} tracked</span>
        </div>
        <div className="sites">
          {sites.map((s) => (
            <Link key={s.id} href={`/sites/${s.domain}`} className="sitecard">
              <h3>{s.name ?? s.domain}</h3>
              <div className="dom mono">{s.domain}</div>
              <div className="vert">{s.vertical ?? s.tagline ?? ""}</div>
              <div className="figs mono">
                <div>
                  <b>{s.feature_count}</b>
                  <span>Features</span>
                </div>
                <div>
                  <b>{s.page_count}</b>
                  <span>Pages</span>
                </div>
                <div>
                  <b>{s.annotated}</b>
                  <span>Pinned</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Categories</h2>
          <span className="count mono">across all sites</span>
        </div>
        <div className="chips">
          {cats.map((c) => (
            <Link
              key={c.category}
              href={`/features?cat=${encodeURIComponent(c.category)}`}
              className="chip"
            >
              {c.category}
              <span className="n mono">{c.n}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Annotated screens</h2>
          <span className="count mono">{pages.length} captured</span>
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
                ) : null}
              </div>
              <div className="body">
                <b>{p.title?.trim() || p.url}</b>
                <div className="mono">
                  {p.page_type} · {p.feature_count} features
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
