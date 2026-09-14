/**
 * The pickleball paddle catalog — schema `catalog` in Supabase Postgres.
 *
 * Was `db/features.db` via `node:sqlite`. Every exported type is unchanged from
 * that version so no component's props moved; every exported function is now
 * async, because the database is across a network rather than on the disk.
 *
 * The `plain()` null-prototype re-wrap that `node:sqlite` forced is gone —
 * postgres.js returns ordinary objects that React Server Components will
 * serialise happily.
 */
import { all_, one, getSql, plateUrl, cleanPlate, READONLY } from "./pg";

export { plateUrl, cleanPlate, READONLY };

// ---------------------------------------------------------------- types

export type Site = {
  id: number;
  domain: string;
  name: string | null;
  homepage_url: string;
  vertical: string | null;
  business_model: string | null;
  tagline: string | null;
  description: string | null;
  notes: string | null;
  first_seen_at: string;
  last_scraped_at: string | null;
};

export type Feature = {
  id: number;
  site_id: number;
  page_id: number | null;
  name: string;
  category: string | null;
  description: string | null;
  evidence: string | null;
  confidence: number | null;
  tier: string | null;
  is_differentiator: number;
  page_type: string | null;
  page_url: string | null;
  domain: string;
  match_method: string | null;
  crop_path: string | null;
};

export type PageRow = {
  id: number;
  site_id: number;
  url: string;
  title: string | null;
  page_type: string | null;
  markdown_path: string | null;
  word_count: number | null;
  scrape_status: string;
  scraped_at: string;
  domain: string;
  feature_count: number;
  shot: string | null;
};

export type Annotation = {
  feature_id: number;
  name: string;
  category: string | null;
  description: string | null;
  evidence: string | null;
  tier: string | null;
  is_differentiator: number;
  x: number | null;
  y: number | null;
  w: number | null;
  h: number | null;
  match_method: string | null;
  crop_path: string | null;
};

// ---------------------------------------------------------------- queries

export async function getStats() {
  const r = await one<{
    sites: number; features: number; pages: number;
    annotated: number; categories: number;
  }>(`
    SELECT (SELECT COUNT(*) FROM catalog.sites)                         AS sites,
           (SELECT COUNT(*) FROM catalog.features)                      AS features,
           (SELECT COUNT(*) FROM catalog.pages WHERE scrape_status='ok') AS pages,
           (SELECT COUNT(*) FROM catalog.annotations
             WHERE match_method <> 'failed')                            AS annotated,
           (SELECT COUNT(DISTINCT category) FROM catalog.features
             WHERE category IS NOT NULL)                                AS categories`);
  return {
    sites: Number(r?.sites ?? 0),
    features: Number(r?.features ?? 0),
    pages: Number(r?.pages ?? 0),
    annotated: Number(r?.annotated ?? 0),
    categories: Number(r?.categories ?? 0),
  };
}

export function getSites() {
  return all_<Site & { feature_count: number; page_count: number; annotated: number }>(`
    SELECT s.*,
      (SELECT COUNT(*) FROM catalog.features f WHERE f.site_id = s.id)::int AS feature_count,
      (SELECT COUNT(*) FROM catalog.pages p
        WHERE p.site_id = s.id AND p.scrape_status='ok')::int          AS page_count,
      (SELECT COUNT(*) FROM catalog.annotations a
         JOIN catalog.features f2 ON f2.id = a.feature_id
        WHERE f2.site_id = s.id AND a.match_method <> 'failed')::int   AS annotated
    FROM catalog.sites s
    ORDER BY feature_count DESC`);
}

export function getSite(domain: string) {
  return one<Site>("SELECT * FROM catalog.sites WHERE domain = $1", domain);
}

export function getFeatures(domain?: string) {
  const where = domain ? "WHERE s.domain = $1" : "";
  const params = domain ? [domain] : [];
  return all_<Feature>(
    `SELECT f.*, s.domain, p.url AS page_url, p.page_type,
            a.match_method, a.crop_path
       FROM catalog.features f
       JOIN catalog.sites s ON s.id = f.site_id
       LEFT JOIN catalog.pages p ON p.id = f.page_id
       LEFT JOIN catalog.annotations a ON a.feature_id = f.id
       ${where}
      ORDER BY f.category, f.name`,
    ...params
  );
}

export function getPages(domain?: string) {
  const where = domain ? "WHERE s.domain = $1 AND" : "WHERE";
  const params = domain ? [domain] : [];
  return all_<PageRow>(
    `SELECT p.*, s.domain,
        (SELECT COUNT(*) FROM catalog.features f WHERE f.page_id = p.id)::int AS feature_count,
        (SELECT a.screenshot_path FROM catalog.annotations a
          WHERE a.page_id = p.id AND a.screenshot_path IS NOT NULL LIMIT 1) AS shot
      FROM catalog.pages p JOIN catalog.sites s ON s.id = p.site_id
      ${where} p.scrape_status = 'ok'
      ORDER BY p.id`,
    ...params
  );
}

export function getPage(id: number) {
  return one<PageRow>(
    `SELECT p.*, s.domain,
        (SELECT COUNT(*) FROM catalog.features f WHERE f.page_id = p.id)::int AS feature_count,
        (SELECT a.screenshot_path FROM catalog.annotations a
          WHERE a.page_id = p.id AND a.screenshot_path IS NOT NULL LIMIT 1) AS shot
      FROM catalog.pages p JOIN catalog.sites s ON s.id = p.site_id
      WHERE p.id = $1`,
    id
  );
}

export function getAnnotations(pageId: number) {
  return all_<Annotation>(
    `SELECT a.feature_id, a.x, a.y, a.w, a.h, a.match_method, a.crop_path,
            f.name, f.category, f.description, f.evidence, f.tier, f.is_differentiator
       FROM catalog.annotations a
       JOIN catalog.features f ON f.id = a.feature_id
      WHERE a.page_id = $1 AND a.match_method <> 'failed'
      ORDER BY a.y, a.x`,
    pageId
  );
}

export function getCategories(domain?: string) {
  const where = domain ? "WHERE s.domain = $1" : "";
  const params = domain ? [domain] : [];
  return all_<{ category: string; n: number }>(
    `SELECT COALESCE(f.category,'uncategorised') AS category, COUNT(*)::int AS n
       FROM catalog.features f JOIN catalog.sites s ON s.id = f.site_id
       ${where}
      GROUP BY 1 ORDER BY n DESC`,
    ...params
  );
}

export function getPrevalence() {
  return all_<{
    slug: string; name: string; category: string | null;
    site_count: number; sites: string;
  }>("SELECT * FROM catalog.v_feature_prevalence");
}

/**
 * Full-text search.
 *
 * SQLite's FTS5 `MATCH` with quoted OR-joined tokens becomes a tsquery here.
 * `websearch_to_tsquery` understands a bare `or`, and treats plain spaces as
 * AND — so the tokens are joined explicitly to keep the old OR behaviour, where
 * a two-word query still returns rows matching either word.
 */
export async function search(q: string) {
  const cleaned = q.trim().replace(/["']/g, "");
  if (!cleaned) return [];
  const query = cleaned.split(/\s+/).filter(Boolean).join(" or ");
  try {
    return await all_<Feature>(
      `SELECT f.*, s.domain, p.url AS page_url, p.page_type,
              a.match_method, a.crop_path
         FROM catalog.features f
         JOIN catalog.sites s ON s.id = f.site_id
         LEFT JOIN catalog.pages p ON p.id = f.page_id
         LEFT JOIN catalog.annotations a ON a.feature_id = f.id
        WHERE f.search_vector @@ websearch_to_tsquery('english', $1)
        ORDER BY ts_rank(f.search_vector,
                         websearch_to_tsquery('english', $1)) DESC
        LIMIT 100`,
      query
    );
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------- jobs

export type Job = {
  id: number;
  url: string;
  domain: string | null;
  site_name: string | null;
  stage: string;
  status: string;
  message: string | null;
  pages_found: number;
  pages_scraped: number;
  pages_failed: number;
  created_at: string;
  updated_at: string;
};

export function listJobs(limit = 30) {
  return all_<Job>("SELECT * FROM catalog.jobs ORDER BY id DESC LIMIT $1", limit);
}

/**
 * Queue a capture job.
 *
 * The pipeline it queues for (Python + Docker Firecrawl + Playwright) cannot run
 * on Vercel, so a hosted deployment sets CATALOG_READONLY=1 and this refuses
 * rather than writing a row nothing will ever pick up.
 */
export async function createJob(url: string, name: string | null): Promise<number> {
  if (READONLY) {
    throw new Error(
      "This deployment is read-only. Capture runs on the local machine; " +
        "publish results with scripts/publish.py."
    );
  }
  const host = new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  const rows = await getSql().unsafe(
    "INSERT INTO catalog.jobs (url, domain, site_name) VALUES ($1,$2,$3) RETURNING id",
    [url, host, name] as never[]
  );
  return Number((rows as unknown as { id: number }[])[0].id);
}

// ---------------------------------------------------------------- gap analysis

export type GapRow = {
  slug: string;
  name: string;
  category: string | null;
  sites: string;
  mine: number;
};

/**
 * Canonical-feature coverage for `domain` against `rivals`. Comparison is on the
 * canonical slug, never on raw feature names, so "Paddle Fit Assistant" and
 * "Paddle selector quiz" count as one thing.
 */
export function getGaps(domain: string, rivals: string[]) {
  const all = [domain, ...rivals];
  return all_<GapRow>(
    `SELECT cf.slug, cf.name, cf.category,
            string_agg(DISTINCT s.domain, ',') AS sites,
            MAX(CASE WHEN s.domain = $1 THEN 1 ELSE 0 END)::int AS mine
       FROM catalog.canonical_features cf
       JOIN catalog.feature_links fl ON fl.canonical_id = cf.id
       JOIN catalog.features f ON f.id = fl.feature_id
       JOIN catalog.sites s ON s.id = f.site_id
      WHERE s.domain = ANY($2)
      GROUP BY cf.id, cf.slug, cf.name, cf.category
      ORDER BY cf.category, cf.name`,
    domain,
    all
  );
}

export function getFeaturesByCanonical(domain: string) {
  return all_<{
    slug: string | null; name: string;
    evidence: string | null; page_url: string | null;
  }>(
    `SELECT cf.slug, f.name, f.evidence, p.url AS page_url
       FROM catalog.features f
       JOIN catalog.sites s ON s.id = f.site_id
       LEFT JOIN catalog.feature_links fl ON fl.feature_id = f.id
       LEFT JOIN catalog.canonical_features cf ON cf.id = fl.canonical_id
       LEFT JOIN catalog.pages p ON p.id = f.page_id
      WHERE s.domain = $1`,
    domain
  );
}
