/**
 * PDP Lab — schema `pdp` in Supabase Postgres.
 *
 * A deliberately separate schema from `catalog`. The paddle catalog counts with
 * `SELECT COUNT(*) FROM sites` and no site filter, so putting these 13
 * product-detail pages in the same tables would silently change the totals on
 * Overview, Features, Screens, Compare, Gaps and Search. Two schemas, two
 * modules, nothing imported between them — and `luzzpickleball.com` exists
 * independently in both, which it does.
 *
 * Was `db/pdp.db` via `node:sqlite`. Types are unchanged; functions are async.
 */
import { all_, one, plateUrl, cleanPlate } from "./pg";

export { plateUrl, cleanPlate };

// ---------------------------------------------------------------- types

export type PdpSite = {
  id: number;
  domain: string;
  name: string | null;
  homepage_url: string;
  vertical: string | null;
  business_model: string | null;
  tagline: string | null;
  description: string | null;
  notes: string | null;
  last_scraped_at: string | null;
  feature_count: number;
  circled: number;
  /** annotation rows of any kind, including failures. 0 == the page was never
      successfully opened (a bot wall), a different story from "opened but
      nothing matched". */
  attempted: number;
  page_url: string | null;
  page_id: number | null;
  shot: string | null;
  title: string | null;
};

export type PdpFeature = {
  id: number;
  name: string;
  category: string | null;
  description: string | null;
  evidence: string | null;
  confidence: number | null;
  tier: string | null;
  is_differentiator: number;
  domain: string;
  site_name: string | null;
  page_url: string | null;
  match_method: string | null;
  matched_text: string | null;
  crop_path: string | null;
  canonical: string | null;
  canonical_slug: string | null;
  x: number | null;
  y: number | null;
  w: number | null;
  h: number | null;
};

export type MatrixRow = {
  slug: string;
  name: string;
  category: string | null;
  /** comma-separated domains shipping this canonical feature */
  sites: string;
  site_count: number;
};

// ---------------------------------------------------------------- queries

export async function pdpStats() {
  const r = await one<{
    sites: number; features: number; circled: number;
    canonical: number; categories: number;
  }>(`
    SELECT (SELECT COUNT(*) FROM pdp.sites)              AS sites,
           (SELECT COUNT(*) FROM pdp.features)           AS features,
           (SELECT COUNT(*) FROM pdp.annotations
             WHERE match_method <> 'failed')             AS circled,
           (SELECT COUNT(*) FROM pdp.canonical_features) AS canonical,
           (SELECT COUNT(DISTINCT category) FROM pdp.features
             WHERE category IS NOT NULL)                 AS categories`);
  return {
    sites: Number(r?.sites ?? 0),
    features: Number(r?.features ?? 0),
    circled: Number(r?.circled ?? 0),
    canonical: Number(r?.canonical ?? 0),
    categories: Number(r?.categories ?? 0),
  };
}

/** One row per PDP: the site, its single page, and its capture. */
const SITE_SELECT = `
  SELECT s.id, s.domain, s.name, s.homepage_url, s.vertical, s.business_model,
         s.tagline, s.description, s.notes, s.last_scraped_at,
    (SELECT COUNT(*) FROM pdp.features f WHERE f.site_id = s.id)::int AS feature_count,
    (SELECT COUNT(*) FROM pdp.annotations a
        JOIN pdp.features f2 ON f2.id = a.feature_id
       WHERE f2.site_id = s.id AND a.match_method <> 'failed')::int   AS circled,
    (SELECT COUNT(*) FROM pdp.annotations a
        JOIN pdp.features f4 ON f4.id = a.feature_id
       WHERE f4.site_id = s.id)::int                                  AS attempted,
    (SELECT p.url   FROM pdp.pages p WHERE p.site_id = s.id ORDER BY p.id LIMIT 1) AS page_url,
    (SELECT p.id    FROM pdp.pages p WHERE p.site_id = s.id ORDER BY p.id LIMIT 1) AS page_id,
    (SELECT p.title FROM pdp.pages p WHERE p.site_id = s.id ORDER BY p.id LIMIT 1) AS title,
    (SELECT a.screenshot_path FROM pdp.annotations a
        JOIN pdp.features f3 ON f3.id = a.feature_id
       WHERE f3.site_id = s.id AND a.screenshot_path IS NOT NULL LIMIT 1) AS shot
    FROM pdp.sites s`;

export function pdpSites() {
  return all_<PdpSite>(`${SITE_SELECT} ORDER BY feature_count DESC, s.domain`);
}

export function pdpSite(domain: string) {
  return one<PdpSite>(`${SITE_SELECT} WHERE s.domain = $1`, domain);
}

export function pdpFeatures(domain?: string) {
  const where = domain ? "WHERE s.domain = $1" : "";
  const params = domain ? [domain] : [];
  return all_<PdpFeature>(
    `SELECT f.id, f.name, f.category, f.description, f.evidence, f.confidence,
            f.tier, f.is_differentiator,
            s.domain, s.name AS site_name,
            p.url AS page_url,
            a.match_method, a.matched_text, a.crop_path, a.x, a.y, a.w, a.h,
            cf.name AS canonical, cf.slug AS canonical_slug
       FROM pdp.features f
       JOIN pdp.sites s ON s.id = f.site_id
       LEFT JOIN pdp.pages p ON p.id = f.page_id
       LEFT JOIN pdp.annotations a ON a.feature_id = f.id
       LEFT JOIN pdp.feature_links fl ON fl.feature_id = f.id
       LEFT JOIN pdp.canonical_features cf ON cf.id = fl.canonical_id
       ${where}
      ORDER BY (a.match_method IS NULL OR a.match_method = 'failed'),
               a.y, a.x, f.category, f.name`,
    ...params
  );
}

/** Only the features that got circled, in reading order down the page. */
export function pdpCircled(domain: string) {
  return all_<PdpFeature>(
    `SELECT f.id, f.name, f.category, f.description, f.evidence, f.confidence,
            f.tier, f.is_differentiator,
            s.domain, s.name AS site_name, p.url AS page_url,
            a.match_method, a.matched_text, a.crop_path, a.x, a.y, a.w, a.h,
            cf.name AS canonical, cf.slug AS canonical_slug
       FROM pdp.annotations a
       JOIN pdp.features f ON f.id = a.feature_id
       JOIN pdp.sites s ON s.id = f.site_id
       LEFT JOIN pdp.pages p ON p.id = f.page_id
       LEFT JOIN pdp.feature_links fl ON fl.feature_id = f.id
       LEFT JOIN pdp.canonical_features cf ON cf.id = fl.canonical_id
      WHERE s.domain = $1 AND a.match_method <> 'failed'
      ORDER BY a.y, a.x`,
    domain
  );
}

/** Features with no circle: unmatched, or honestly low-confidence. */
export function pdpUncircled(domain: string) {
  return all_<PdpFeature>(
    `SELECT f.id, f.name, f.category, f.description, f.evidence, f.confidence,
            f.tier, f.is_differentiator, s.domain, s.name AS site_name,
            p.url AS page_url, a.match_method, a.matched_text,
            NULL::text AS crop_path, NULL::int AS x, NULL::int AS y,
            NULL::int AS w, NULL::int AS h,
            cf.name AS canonical, cf.slug AS canonical_slug
       FROM pdp.features f
       JOIN pdp.sites s ON s.id = f.site_id
       LEFT JOIN pdp.pages p ON p.id = f.page_id
       LEFT JOIN pdp.annotations a ON a.feature_id = f.id
       LEFT JOIN pdp.feature_links fl ON fl.feature_id = f.id
       LEFT JOIN pdp.canonical_features cf ON cf.id = fl.canonical_id
      WHERE s.domain = $1
        AND (a.feature_id IS NULL OR a.match_method = 'failed')
      ORDER BY f.category, f.name`,
    domain
  );
}

export function pdpCategories(domain?: string) {
  const where = domain ? "WHERE s.domain = $1" : "";
  const params = domain ? [domain] : [];
  return all_<{ category: string; n: number }>(
    `SELECT COALESCE(f.category,'uncategorised') AS category, COUNT(*)::int AS n
       FROM pdp.features f JOIN pdp.sites s ON s.id = f.site_id
       ${where}
      GROUP BY 1 ORDER BY n DESC`,
    ...params
  );
}

/**
 * Which PDP features are table stakes across 13 storefronts in 9 verticals, and
 * which are rare. Keyed on the canonical slug — never on raw feature names, or
 * "Subscribe & Save" and "Sub & Save" would read as two different features and
 * invent a gap that is not there.
 */
export function pdpMatrix() {
  return all_<MatrixRow>(
    `SELECT cf.slug, cf.name, cf.category,
            string_agg(DISTINCT s.domain, ',') AS sites,
            COUNT(DISTINCT s.id)::int AS site_count
       FROM pdp.canonical_features cf
       JOIN pdp.feature_links fl ON fl.canonical_id = cf.id
       JOIN pdp.features f ON f.id = fl.feature_id
       JOIN pdp.sites s ON s.id = f.site_id
      GROUP BY cf.id, cf.slug, cf.name, cf.category
      ORDER BY site_count DESC, cf.category, cf.name`
  );
}

/** Domains in a stable column order for the matrix header. */
export function pdpDomains() {
  return all_<{ domain: string; name: string | null; feature_count: number }>(
    `SELECT s.domain, s.name,
       (SELECT COUNT(*) FROM pdp.features f WHERE f.site_id = s.id)::int AS feature_count
       FROM pdp.sites s ORDER BY feature_count DESC, s.domain`
  );
}
