import { Fragment } from "react";
import Link from "next/link";
import { pdpDomains, pdpMatrix } from "@/lib/pdp-db";

export const dynamic = "force-dynamic";

/** 4-char column label, e.g. "arrae.com" -> "arra". */
function abbrev(domain: string) {
  return domain.replace(/^www\./, "").slice(0, 4);
}

export default async function PdpMatrixPage() {
  const [rows, domains] = await Promise.all([pdpMatrix(), pdpDomains()]);
  const n = domains.length;

  // group by category, preserving the site_count DESC order inside each group
  const byCat = new Map<string, typeof rows>();
  for (const r of rows) {
    const k = r.category ?? "uncategorised";
    if (!byCat.has(k)) byCat.set(k, []);
    byCat.get(k)!.push(r);
  }
  // most-shared categories first
  const cats = [...byCat.entries()].sort(
    (a, b) =>
      Math.max(...b[1].map((r) => r.site_count)) -
      Math.max(...a[1].map((r) => r.site_count))
  );

  const universal = rows.filter((r) => r.site_count === n);
  const common = rows.filter((r) => r.site_count >= Math.ceil(n / 2) && r.site_count < n);
  const rare = rows.filter((r) => r.site_count === 1);

  return (
    <>
      <div className="crumb">
        <Link href="/pdp">PDP Lab</Link> <span>/</span>
        <span className="mono">matrix</span>
      </div>

      <section className="hero" style={{ paddingTop: 22 }}>
        <div className="eyebrow">canonical feature × storefront</div>
        <h1
          className="display"
          style={{ fontSize: "clamp(1.8rem,1rem+2.4vw,3rem)" }}
        >
          What every PDP has — and does not
        </h1>
        <p className="lede">
          {rows.length} canonical features across {n} product pages. Rows are
          ordered by how many storefronts ship each one, so table stakes float to
          the top of each category and the genuinely unusual sinks to the bottom.
        </p>
        <p className="pdp-note">
          Comparison keys on the canonical slug, never the raw feature name.
          &ldquo;Save 20% with Subscribe &amp; Save&rdquo; and &ldquo;Subscription
          discount&rdquo; collapse to one row — otherwise each would read as a
          feature only one site has, and invent a gap that is not there.
        </p>
      </section>

      <div className="statrow">
        <div className="stat">
          <b>{rows.length}</b>
          <span>canonical features</span>
        </div>
        <div className="stat">
          <b>{universal.length}</b>
          <span>on all {n}</span>
        </div>
        <div className="stat">
          <b>{common.length}</b>
          <span>on half or more</span>
        </div>
        <div className="stat">
          <b>{rare.length}</b>
          <span>on exactly one</span>
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <h2>The matrix</h2>
          <span className="count mono">
            {rows.length} rows × {n} sites
          </span>
        </div>

        {rows.length === 0 ? (
          <div className="empty">
            No canonical links yet — load the extracted JSON with add_features.py.
          </div>
        ) : (
          <div className="pdp-matrix-wrap">
            <table className="pdp-matrix">
              <thead>
                <tr>
                  <th style={{ minWidth: 210 }}>feature</th>
                  {domains.map((d) => (
                    <th key={d.domain} className="pdp-col mono" title={d.domain}>
                      {abbrev(d.domain)}
                    </th>
                  ))}
                  <th className="pdp-n-sites">n</th>
                </tr>
              </thead>
              <tbody>
                {cats.map(([cat, list]) => (
                  <Fragment key={`cat-${cat}`}>
                    <tr className="pdp-cat-row">
                      <th colSpan={n + 2}>{cat}</th>
                    </tr>
                    {list.map((r) => {
                      const has = new Set((r.sites ?? "").split(","));
                      return (
                        <tr key={r.slug}>
                          <th>{r.name}</th>
                          {domains.map((d) => (
                            <td
                              key={d.domain}
                              className="pdp-cell"
                              data-on={has.has(d.domain)}
                              title={`${r.name} — ${d.domain}`}
                            >
                              {has.has(d.domain) ? "●" : "·"}
                            </td>
                          ))}
                          <td className="pdp-n-sites mono">{r.site_count}</td>
                        </tr>
                      );
                    })}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {universal.length ? (
        <div className="section">
          <div className="section-head">
            <h2>Table stakes</h2>
            <span className="count mono">on all {n} storefronts</span>
          </div>
          <div className="chips">
            {universal.map((r) => (
              <span key={r.slug} className="chip">
                {r.name}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {rare.length ? (
        <div className="section">
          <div className="section-head">
            <h2>Only one site does this</h2>
            <span className="count mono">{rare.length}</span>
          </div>
          <div className="pdp-missed">
            <ul>
              {rare.map((r) => (
                <li key={r.slug}>
                  <strong style={{ color: "var(--text)" }}>{r.name}</strong>{" "}
                  <span className="mono" style={{ color: "var(--signal)" }}>
                    {r.sites}
                  </span>
                  {r.category ? (
                    <span style={{ color: "var(--text-faint)" }}> · {r.category}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </>
  );
}
