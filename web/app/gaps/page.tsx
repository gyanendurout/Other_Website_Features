import Link from "next/link";
import { getGaps, getFeaturesByCanonical } from "@/lib/db";

export const dynamic = "force-dynamic";

const SUBJECT = "joola.com";
const RIVALS = [
  "selkirk.com",
  "luzzpickleball.com",
  "crbnpickleball.com",
  "us.sixzeropickleball.com",
  "paddletek.com",
  "gammasports.com",
];

const LABEL: Record<string, string> = {
  "joola.com": "JOOLA",
  "selkirk.com": "Selkirk",
  "luzzpickleball.com": "Luzz",
  "crbnpickleball.com": "CRBN",
  "us.sixzeropickleball.com": "Six Zero",
  "paddletek.com": "Paddletek",
  "gammasports.com": "GAMMA",
};

/**
 * Hand-written reading of the crawl. The DB answers "who ships what"; these
 * notes answer "so what" - severity, and what JOOLA ships instead. Kept beside
 * the query rather than in it because it is judgement, not data.
 */
const NOTES: Record<string, { sev: "high" | "med" | "low"; note: string }> = {
  "star-ratings-on-product-cards": {
    sev: "high",
    note: "The single largest fixable gap. JOOLA has 350 reviews at 4.4 stars on the flagship PDP - and shows a rating on 0 of 336 collection cards. The social proof is bought and paid for, then withheld at exactly the point where a shopper is ranking 77 near-identical paddles.",
  },
  "rating-histogram": { sev: "low", note: "Narrow gap, not a missing capability. JOOLA offers removable 5/4/3/2/1-star filter chips so you can read only the 1-stars — but no distribution bars, so the shape of the 4.4 is not visible at a glance." },
  "video-testimonials": { sev: "low", note: "JOOLA has athlete video, but no customer video." },
  "free-trial-period": {
    sev: "high",
    note: "Both rivals independently converged on a 30-day play-test guarantee. JOOLA offers a 12-month defect warranty that also requires registration - protection against breakage, not against buying the wrong paddle.",
  },
  "loyalty-rewards": { sev: "high", note: "Selkirk runs tiered Bonus Bucks cashback. JOOLA has no repeat-purchase mechanic, despite selling balls, grips, apparel and shoes as consumable follow-ons." },
  "referral-program": { sev: "med", note: "Selkirk pays customers to bring customers. JOOLA has no customer-acquisition loop." },
  "affiliate-program": { sev: "med", note: "Selkirk runs affiliates; JOOLA relies on sponsored athletes only, which is far more expensive per impression." },
  "back-in-stock-notification": { sev: "med", note: "Collection has an Out of stock facet, so stockouts happen - but no way to capture demand when they do. Pure lost revenue." },
  "multi-currency-support": { sev: "med", note: "USD only. There is an International Products collection, so international intent is known and unserved at checkout." },
  "expert-consultation": { sev: "med", note: "Selkirk books a one-to-one fit expert. JOOLA's equivalent human channel is a single physical store." },
  "spec-scorecard": {
    sev: "high",
    note: "Selkirk publishes numeric ratings (Spin 10 / Control 10 / Power 7 / Sweet Spot 8) - including the weakness. JOOLA describes KineticFrame and Propulsion Core in prose but never quantifies, so 77 SKUs cannot be ranked on the axes buyers care about.",
  },
  "product-image-gallery": { sev: "med", note: "No gallery structure surfaced in the PDP markup - a $299.95 paddle shown thinly." },
  "product-badges": { sev: "low", note: "Only Sale and In Stock. No New / Bestseller / Pro Choice signalling in the grid." },
  "policy-accordion": { sev: "low", note: "Shipping, returns and warranty live in footer pages rather than on the PDP where the objection is." },
  "email-capture-popup": { sev: "low", note: "Footer signup only. Deliberate restraint, arguably the better call." },
  "countdown-timer": { sev: "low", note: "The 35% sale has no stated end date, which weakens the urgency it is trying to create." },
  "pre-order": { sev: "low", note: "No pre-order path for launches." },
  "tiered-launch-offers": { sev: "low", note: "Luzz stacks escalating launch incentives; JOOLA runs flat percentage-off." },
  "product-customization": { sev: "low", note: "No customisation path on paddles." },
  "survey-gated-discount": { sev: "low", note: "Selkirk trades discount for research data. JOOLA collects nothing in exchange for its markdowns." },
  "membership-upsell": { sev: "low", note: "An RPO membership collection exists but is not upsold anywhere on the paths crawled." },
  "training-program": { sev: "med", note: "Selkirk Academy runs camps and coaching. JOOLA has facility partnerships but no owned instruction business." },
  "brand-ambassadors": { sev: "low", note: "Pro roster only - no tier for ordinary players." },
  "community-co-creation": { sev: "low", note: "No route for players to shape products." },
  "multi-brand-portfolio": { sev: "low", note: "Selkirk splits LABS / Sport / SLK by intent. JOOLA splits by sport instead, which is a different but defensible answer." },
  "athlete-sponsorship-program": { sev: "low", note: "JOOLA has rosters but no public application route to join them." },
  "email-support": { sev: "low", note: "Contact page exists; no support address surfaced inline." },
  "price-range-display": { sev: "low", note: "Cards show one price, not a from-price across variants." },
};

/** Where JOOLA ships the thing but the execution is weaker than a rival's. */
const IMPROVE: {
  title: string;
  sev: "high" | "med" | "low";
  joola: string;
  rival: string;
  why: string;
}[] = [
  {
    title: "A best-in-class review system, invisible on the collection grid",
    sev: "high",
    joola: "The PDP runs a full Bazaarvoice stack: 4.4 over 350 reviews, verified-purchaser badges, star filters, separate Quality and Value scores, public replies signed Team JOOLA, syndication across colourways, and a community Q&A JOOLA answers itself. Not one of 336 collection cards shows a rating.",
    rival: "Luzz puts star ratings directly on product cards, so the grid can be read by proof.",
    why: "This is the strongest social-proof system of the three brands and it is switched off exactly where 77 near-identical paddles compete. Surfacing a score JOOLA already owns is a template change, not a new capability - the cheapest high-value fix here by a wide margin.",
  },
  {
    title: "Colour and grip facets are polluted with near-duplicates",
    sev: "high",
    joola: "31 colour values including “Seaside”, “Seaside Green” and “Seaside Dark Green”; grip circumference lists “4.125”, “4.125in”, “4.125 in”, “4.1875in”, “4.250in/4.125in” as five separate options.",
    rival: "Selkirk's facets are normalised, so each filter click meaningfully cuts the result set.",
    why: "The three-axis mega-menu is JOOLA's strongest navigation idea and the facets underneath it leak. This is a data-hygiene fix in the product feed, not a redesign.",
  },
  {
    title: "Broken Thickness facet sits next to a working one",
    sev: "high",
    joola: "“Thickness” offers only 10MM, while a separate “Core Thickness (mm)” correctly offers 10/14/16. “Series/Shape” lists only “Elongated” despite six named shapes existing in the nav.",
    rival: "Selkirk exposes one shape facet that matches its shape vocabulary.",
    why: "Two facets for one attribute, one of them near-empty, teaches shoppers the filters do not work.",
  },
  {
    title: "The paddle quiz is buried",
    sev: "high",
    joola: "The selector quiz appears once, at the bottom of the Hits Different comparison page.",
    rival: "Selkirk puts Paddle Fit Assistant in the primary navigation.",
    why: "JOOLA already built the highest-value tool for a 77-SKU range and then hid it below the fold of a page most visitors never reach.",
  },
  {
    title: "Free shipping threshold is nearly 2x the rival's",
    sev: "med",
    joola: "$100, shown as a live cart progress meter.",
    rival: "Selkirk ships free at $55.",
    why: "The meter is the better UI; the number is the worse offer. A $99.95 3S paddle lands one nickel short.",
  },
  {
    title: "Warranty is the shortest of the three",
    sev: "med",
    joola: "12 months, and only if the buyer registers.",
    rival: "Selkirk offers a limited lifetime warranty, also registration-gated.",
    why: "Same friction, a twelfth of the coverage, on a paddle priced at the top of the market.",
  },
  {
    title: "Education is scattered instead of branded",
    sev: "med",
    joola: "Guides and How-Tos, product instructions, blade specs and rubber specs sit in four separate footer links.",
    rival: "Selkirk University is a single branded hub with tagged topics.",
    why: "JOOLA arguably has deeper technical material - inherited from 70 years of table tennis - and gets less credit for it.",
  },
  {
    title: "Certifications are a spec row, not a trust asset",
    sev: "low",
    joola: "“UPA-A certified: Yes / USAP certified: Yes” inside the spec table, plus a footer Patents page.",
    rival: "Luzz runs a dedicated certification hub.",
    why: "Tournament legality is a purchase blocker for competitive buyers and currently reads like a footnote.",
  },
];

const SEV_ORDER = { high: 0, med: 1, low: 2 } as const;
const SEV_LABEL = { high: "High", med: "Medium", low: "Low" } as const;

export default async function Gaps() {
  const rows = await getGaps(SUBJECT, RIVALS);
  const mine = rows.filter((r) => r.mine === 1);
  const gaps = rows.filter((r) => r.mine === 0);
  const ALL = RIVALS.length + 1;
  const shared = mine.filter((r) => r.sites.split(",").length === ALL);
  const onlyMine = mine.filter((r) => r.sites.split(",").length === 1);

  const ranked = [...gaps].sort((a, b) => {
    const sa = NOTES[a.slug]?.sev ?? "low";
    const sb = NOTES[b.slug]?.sev ?? "low";
    if (SEV_ORDER[sa] !== SEV_ORDER[sb]) return SEV_ORDER[sa] - SEV_ORDER[sb];
    // both-rivals-have-it outranks one-rival-has-it
    return b.sites.split(",").length - a.sites.split(",").length;
  });

  const high = ranked.filter((r) => (NOTES[r.slug]?.sev ?? "low") === "high");

  return (
    <div className="section" style={{ paddingTop: 40 }}>
      <div className="section-head">
        <h2>JOOLA vs the field</h2>
        <span className="count mono">{gaps.length} gaps · {IMPROVE.length} to improve</span>
      </div>

      <p className="lede" style={{ marginTop: 0, maxWidth: 760 }}>
        Every feature is compared on its <strong>canonical slug</strong>, not its
        label — so JOOLA&apos;s “paddle selector quiz” and Selkirk&apos;s “Paddle Fit
        Assistant” count as the same capability. Scored against{" "}
        {RIVALS.length} rival paddle brands — {RIVALS.map((r) => LABEL[r]).join(", ")} —
        each captured across homepage, paddle collection and flagship PDP. All
        prices are USD from US storefronts.
      </p>

      <div className="statgrid" style={{ marginTop: 24 }}>
        <div className="stat accent">
          <b>{high.length}</b>
          <span>High-severity gaps</span>
        </div>
        <div className="stat">
          <b>{gaps.length}</b>
          <span>Missing vs a rival</span>
        </div>
        <div className="stat">
          <b>{shared.length}</b>
          <span>Table stakes all {ALL} ship</span>
        </div>
        <div className="stat">
          <b>{onlyMine.length}</b>
          <span>JOOLA-only</span>
        </div>
      </div>

      {/* ---------------------------------------------------------- missing */}
      <div className="section-head" style={{ marginTop: 52 }}>
        <h2 style={{ fontSize: "1.15rem" }}>Missing</h2>
        <span className="count mono">ranked by severity</span>
      </div>

      <div className="flist">
        {ranked.map((r) => {
          const n = NOTES[r.slug];
          const sev = n?.sev ?? "low";
          const who = r.sites
            .split(",")
            .filter((d) => d !== SUBJECT)
            .map((d) => LABEL[d] ?? d);
          return (
            <div key={r.slug} className="frow" style={{ gridTemplateColumns: "1fr auto" }}>
              <div style={{ minWidth: 0 }}>
                <h4>
                  {r.name}{" "}
                  <span className="cat" style={{ marginLeft: 6 }}>{r.category}</span>
                </h4>
                {n ? <div className="desc">{n.note}</div> : null}
              </div>
              <div className="meta">
                <span className="tag" data-tier={sev === "high" ? "addon" : sev === "med" ? "enterprise" : "free"}>
                  {SEV_LABEL[sev]}
                </span>
                <span className="chip">{who.join(" + ")}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* --------------------------------------------------------- improve */}
      <div className="section-head" style={{ marginTop: 52 }}>
        <h2 style={{ fontSize: "1.15rem" }}>Shipped, but weaker</h2>
        <span className="count mono">{IMPROVE.length} findings</span>
      </div>

      <div className="flist">
        {[...IMPROVE].sort((a, b) => SEV_ORDER[a.sev] - SEV_ORDER[b.sev]).map((it) => (
          <div key={it.title} className="frow" style={{ gridTemplateColumns: "1fr auto" }}>
            <div style={{ minWidth: 0 }}>
              <h4>{it.title}</h4>
              <div className="desc" style={{ marginTop: 8 }}>
                <strong style={{ color: "var(--signal)" }}>JOOLA:</strong> {it.joola}
              </div>
              <div className="desc" style={{ marginTop: 5 }}>
                <strong style={{ color: "var(--ok)" }}>Rival:</strong> {it.rival}
              </div>
              <blockquote style={{ marginTop: 9 }}>{it.why}</blockquote>
            </div>
            <div className="meta">
              <span className="tag" data-tier={it.sev === "high" ? "addon" : it.sev === "med" ? "enterprise" : "free"}>
                {SEV_LABEL[it.sev]}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* ---------------------------------------------------------- strong */}
      <div className="section-head" style={{ marginTop: 52 }}>
        <h2 style={{ fontSize: "1.15rem" }}>Where JOOLA is ahead</h2>
      </div>
      <p className="lede" style={{ marginTop: 0, fontSize: ".88rem", maxWidth: 760 }}>
        Not everything is a gap. These are capabilities neither rival ships, or
        that JOOLA executes better — worth protecting rather than trading away.
      </p>
      <div className="flist">
        {onlyMine.map((r) => (
          <div key={r.slug} className="frow" style={{ gridTemplateColumns: "1fr auto" }}>
            <div>
              <h4>{r.name}</h4>
              <div className="desc">{r.category}</div>
            </div>
            <div className="meta">
              <span className="tag" data-tier="free">JOOLA only</span>
            </div>
          </div>
        ))}
      </div>

      <div
        className="lede"
        style={{
          fontSize: ".85rem",
          marginTop: 30,
          padding: "12px 16px",
          border: "1px solid var(--line)",
          borderRadius: "var(--r-md)",
          background: "var(--surface)",
        }}
      >
        <strong>Corrections logged.</strong> An earlier pass reported that
        JOOLA had no reviews and no Q&amp;A. Both were wrong. Bazaarvoice
        injects the entire review and Q&amp;A system client-side, so it is
        invisible to a markdown scrape — and it also failed to appear in two
        scripted browser probes. It was finally confirmed by reading the
        captured screenshot, which remains the ground truth for what a page
        actually renders. The rating-histogram finding was downgraded for the
        same reason. When a negative finding matters, check the plate.
        <br />
        <br />
        <strong>Scope.</strong> Three pages per site, so absence here means
        “not found on the crawled pages”, not “does not exist anywhere”. A
        feature buried three clicks deep is still a finding — but the fix may be
        surfacing rather than building. Add more pages via{" "}
        <Link href="/capture">Capture</Link> to tighten it.
      </div>
    </div>
  );
}
