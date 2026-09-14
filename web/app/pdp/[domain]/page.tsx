import Link from "next/link";
import { notFound } from "next/navigation";
import {
  cleanPlate,
  pdpCategories,
  pdpCircled,
  pdpSite,
  pdpUncircled,
  plateUrl,
} from "@/lib/pdp-db";
import Plate from "./plate";

export const dynamic = "force-dynamic";

export default async function PdpDetail({
  params,
}: {
  params: Promise<{ domain: string }>;
}) {
  const { domain } = await params;
  const site = await pdpSite(decodeURIComponent(domain));
  if (!site) notFound();

  const [circled, uncircled, cats] = await Promise.all([
    pdpCircled(site.domain),
    pdpUncircled(site.domain),
    pdpCategories(site.domain),
  ]);
  const diffs = [...circled, ...uncircled].filter(
    (f) => f.is_differentiator === 1
  );

  return (
    <>
      <div className="crumb">
        <Link href="/pdp">PDP Lab</Link> <span>/</span>
        <span className="mono">{site.domain}</span>
      </div>

      <section className="hero" style={{ paddingTop: 22 }}>
        <div className="eyebrow">{site.vertical ?? "product detail page"}</div>
        <h1
          className="display"
          style={{ fontSize: "clamp(1.8rem,1rem+2.4vw,3rem)" }}
        >
          {site.name ?? site.domain}
        </h1>
        {site.tagline ? <p className="lede">{site.tagline}</p> : null}
        {site.description ? (
          <p className="lede" style={{ fontSize: ".92rem" }}>
            {site.description}
          </p>
        ) : null}
        {site.page_url ? (
          <p style={{ marginTop: 10 }}>
            <a
              href={site.page_url}
              target="_blank"
              rel="noreferrer noopener"
              className="pdp-pill mono"
            >
              open the live page ↗
            </a>
          </p>
        ) : null}
      </section>

      <div className="statrow">
        <div className="stat">
          <b>{site.feature_count}</b>
          <span>features found</span>
        </div>
        <div className="stat">
          <b>{site.circled}</b>
          <span>circled on page</span>
        </div>
        <div className="stat">
          <b>{diffs.length}</b>
          <span>marketed as headline</span>
        </div>
        <div className="stat">
          <b>{site.business_model ?? "—"}</b>
          <span>model</span>
        </div>
      </div>

      {cats.length ? (
        <div className="chips" style={{ marginTop: 20 }}>
          {cats.map((c) => (
            <span key={c.category} className="chip">
              {c.category}
              <b className="mono" style={{ marginLeft: 6, color: "var(--signal)" }}>
                {c.n}
              </b>
            </span>
          ))}
        </div>
      ) : null}

      <div className="section">
        <div className="section-head">
          <h2>Circled and explained</h2>
          <span className="count mono">
            {circled.length} of {site.feature_count} located in the DOM
          </span>
        </div>

        {site.shot ? (
          <Plate
            shot={plateUrl(site.shot)!}
            clean={plateUrl(cleanPlate(site.shot))}
            features={circled}
          />
        ) : site.attempted === 0 ? (
          <div className="pdp-missed">
            <h4>no plate — this storefront served a bot challenge</h4>
            <p style={{ fontSize: ".84rem", color: "var(--text-dim)", lineHeight: 1.6 }}>
              The annotator opened the page and was handed a challenge instead of
              the product page, on separate attempts spaced well apart. It was not
              retried in a loop, and no attempt was made to work around the
              challenge — so the {site.feature_count} features below are
              catalogued from the markdown captures and explained, but none are
              circled. The capture itself succeeded earlier via a second engine,
              which is why the feature list exists at all. Re-running{" "}
              <span className="mono">annotate.py --site {site.domain}</span> later
              may well succeed.
            </p>
          </div>
        ) : (
          <div className="empty">
            No plate captured yet. Run{" "}
            <span className="mono">
              annotate.py --site {site.domain}
            </span>{" "}
            with <span className="mono">CATALOG_SHOTS=data/screenshots/pdp</span>.
          </div>
        )}
      </div>

      {uncircled.length ? (
        <div className="section">
          <div className="section-head">
            <h2>Found, not circled</h2>
            <span className="count mono">{uncircled.length}</span>
          </div>
          <p className="pdp-note">
            These are real features that could not be located in the passive
            capture. Overwhelmingly that is because the text only exists{" "}
            <strong>after a click</strong> — search drawers, cart drawers,
            back-in-stock modals, size-guide overlays, free-gift pickers — and the
            annotator deliberately never operates page controls on a live
            storefront. The rest mount client-side after the capture window
            (review platforms are the usual case), or are images rather than text.
            They are listed rather than deleted: an honest un-circled feature is
            worth more than a needle bent until it matches the wrong element.
          </p>
          <div className="rail" style={{ maxHeight: "none" }}>
            {uncircled.map((f) => (
              <div key={f.id} className="pdp-expl" style={{ cursor: "default" }}>
                <span className="pdp-n mono">·</span>
                <div>
                  <strong>
                    {f.is_differentiator ? <span className="star">★ </span> : null}
                    {f.name}
                  </strong>
                  <div className="pdp-meta mono">
                    {f.category}
                    {f.canonical && f.canonical !== f.name ? ` · ${f.canonical}` : ""}
                    {f.confidence != null ? ` · confidence ${f.confidence}` : ""}
                    {f.match_method ? ` · ${f.match_method}` : " · no match attempt"}
                  </div>
                  {f.description ? <p className="pdp-why">{f.description}</p> : null}
                  {f.evidence ? <p className="pdp-quote">“{f.evidence}”</p> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {site.notes ? (
        <div className="section">
          <div className="section-head">
            <h2>Capture notes</h2>
          </div>
          <div className="pdp-missed">
            <h4>platform, third-party apps, and what the capture did not show</h4>
            <p style={{ fontSize: ".84rem", color: "var(--text-dim)", lineHeight: 1.6 }}>
              {site.notes}
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}
