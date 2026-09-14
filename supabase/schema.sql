-- ============================================================
-- Feature Catalog — Postgres schema for Supabase
--
-- Two schemas, not two databases and not one merged set of tables:
--
--   catalog.*   the pickleball paddle catalog   (was db/features.db)
--   pdp.*       the PDP Lab                     (was db/pdp.db)
--
-- The web app counts with `SELECT COUNT(*) FROM sites` and no site filter, so
-- merging the two would silently change every number on Overview, Features,
-- Screens, Compare, Gaps and Search. Separate schemas keep that isolation for
-- free, and let luzzpickleball.com exist independently in both — which it does.
--
-- Re-runnable: every statement is IF NOT EXISTS or OR REPLACE.
--   psql "$DATABASE_URL" -f supabase/schema.sql
--
-- Note on exposure: these schemas are deliberately NOT added to Supabase's
-- PostgREST `db-schemas` list, so nothing here is readable over the public REST
-- API. The app reaches Postgres directly with DATABASE_URL. The only public
-- surface is the `plates` Storage bucket, which is public on purpose.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS pdp;

-- ------------------------------------------------------------
-- Tables and indexes, identical in both schemas.
--
-- Built in a loop rather than written out twice: the two are the same shape by
-- definition, and a copy-paste pair drifts the first time someone edits one of
-- them. %I quotes identifiers; $q$ ... $q$ keeps the inner SQL readable.
-- ------------------------------------------------------------
DO $do$
DECLARE
  s text;
BEGIN
FOREACH s IN ARRAY ARRAY['catalog', 'pdp'] LOOP

  ---------------------------------------------------------- 1. sites
  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.sites (
      id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      domain          text NOT NULL UNIQUE,
      name            text,
      homepage_url    text NOT NULL,
      vertical        text,
      business_model  text,
      tagline         text,
      description     text,
      first_seen_at   timestamptz NOT NULL DEFAULT now(),
      last_scraped_at timestamptz,
      notes           text
    )$q$, s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_sites_vertical ON %I.sites(vertical)', s);

  ---------------------------------------------------------- 2. pages
  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.pages (
      id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      site_id       bigint NOT NULL REFERENCES %I.sites(id) ON DELETE CASCADE,
      url           text NOT NULL UNIQUE,
      title         text,
      page_type     text,
      markdown_path text,
      content_hash  text,
      word_count    integer,
      http_status   integer,
      scrape_status text NOT NULL DEFAULT 'ok',
      error         text,
      scraped_at    timestamptz NOT NULL DEFAULT now()
    )$q$, s, s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_pages_site ON %I.pages(site_id)', s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_pages_hash ON %I.pages(content_hash)', s);

  ---------------------------------------------------------- 3. features
  -- FTS5 and its three sync triggers are gone. A generated tsvector column is
  -- maintained by Postgres itself, so there is no trigger left to get wrong.
  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.features (
      id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      site_id       bigint NOT NULL REFERENCES %I.sites(id) ON DELETE CASCADE,
      page_id       bigint REFERENCES %I.pages(id) ON DELETE SET NULL,
      name          text NOT NULL,
      category      text,
      description   text,
      evidence      text,
      confidence    real DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
      tier          text,
      is_differentiator integer NOT NULL DEFAULT 0,
      extracted_at  timestamptz NOT NULL DEFAULT now(),
      search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english',
          coalesce(name,'') || ' ' ||
          coalesce(description,'') || ' ' ||
          coalesce(evidence,''))
      ) STORED,
      UNIQUE (site_id, name)
    )$q$, s, s, s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_features_site ON %I.features(site_id)', s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_features_cat ON %I.features(category)', s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_features_fts ON %I.features USING GIN (search_vector)', s);

  ---------------------------------------------------------- 4. canonical taxonomy
  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.canonical_features (
      id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      slug     text NOT NULL UNIQUE,
      name     text NOT NULL,
      category text
    )$q$, s);

  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.feature_links (
      feature_id   bigint NOT NULL REFERENCES %I.features(id) ON DELETE CASCADE,
      canonical_id bigint NOT NULL REFERENCES %I.canonical_features(id) ON DELETE CASCADE,
      PRIMARY KEY (feature_id, canonical_id)
    )$q$, s, s, s);

  ---------------------------------------------------------- 5. annotations
  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.annotations (
      id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      feature_id      bigint NOT NULL UNIQUE REFERENCES %I.features(id) ON DELETE CASCADE,
      page_id         bigint REFERENCES %I.pages(id) ON DELETE CASCADE,
      screenshot_path text,
      crop_path       text,
      x               integer,
      y               integer,
      w               integer,
      h               integer,
      matched_text    text,
      match_method    text,
      created_at      timestamptz NOT NULL DEFAULT now()
    )$q$, s, s, s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_annot_page ON %I.annotations(page_id)', s);

  ---------------------------------------------------------- 6. jobs
  EXECUTE format($q$
    CREATE TABLE IF NOT EXISTS %I.jobs (
      id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      url            text NOT NULL,
      domain         text,
      site_name      text,
      stage          text NOT NULL DEFAULT 'queued',
      status         text NOT NULL DEFAULT 'running',
      message        text,
      pages_found    integer NOT NULL DEFAULT 0,
      pages_scraped  integer NOT NULL DEFAULT 0,
      pages_failed   integer NOT NULL DEFAULT 0,
      created_at     timestamptz NOT NULL DEFAULT now(),
      updated_at     timestamptz NOT NULL DEFAULT now(),
      finished_at    timestamptz
    )$q$, s);
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_jobs_status ON %I.jobs(status, id DESC)', s);

END LOOP;
END
$do$;

-- ------------------------------------------------------------
-- Views. Written out per schema rather than looped: there are only two that
-- matter, and these are the statements a person actually reads when a number
-- on the site looks wrong.
--
-- GROUP_CONCAT(DISTINCT x) has no Postgres equivalent by that name; it is
-- string_agg(DISTINCT x, ','). The app splits on "," so the separator matters.
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW catalog.v_feature_prevalence AS
SELECT c.slug, c.name, c.category,
       COUNT(DISTINCT f.site_id)            AS site_count,
       string_agg(DISTINCT s.domain, ',')   AS sites
  FROM catalog.canonical_features c
  JOIN catalog.feature_links l ON l.canonical_id = c.id
  JOIN catalog.features f      ON f.id = l.feature_id
  JOIN catalog.sites s         ON s.id = f.site_id
 GROUP BY c.id, c.slug, c.name, c.category
 ORDER BY site_count DESC;

CREATE OR REPLACE VIEW pdp.v_feature_prevalence AS
SELECT c.slug, c.name, c.category,
       COUNT(DISTINCT f.site_id)            AS site_count,
       string_agg(DISTINCT s.domain, ',')   AS sites
  FROM pdp.canonical_features c
  JOIN pdp.feature_links l ON l.canonical_id = c.id
  JOIN pdp.features f      ON f.id = l.feature_id
  JOIN pdp.sites s         ON s.id = f.site_id
 GROUP BY c.id, c.slug, c.name, c.category
 ORDER BY site_count DESC;

CREATE OR REPLACE VIEW catalog.v_site_summary AS
SELECT s.domain, s.name, s.vertical,
       COUNT(DISTINCT f.id) AS feature_count,
       COUNT(DISTINCT p.id) AS page_count,
       s.last_scraped_at
  FROM catalog.sites s
  LEFT JOIN catalog.features f ON f.site_id = s.id
  LEFT JOIN catalog.pages    p ON p.site_id = s.id
 GROUP BY s.id, s.domain, s.name, s.vertical, s.last_scraped_at;

CREATE OR REPLACE VIEW pdp.v_site_summary AS
SELECT s.domain, s.name, s.vertical,
       COUNT(DISTINCT f.id) AS feature_count,
       COUNT(DISTINCT p.id) AS page_count,
       s.last_scraped_at
  FROM pdp.sites s
  LEFT JOIN pdp.features f ON f.site_id = s.id
  LEFT JOIN pdp.pages    p ON p.site_id = s.id
 GROUP BY s.id, s.domain, s.name, s.vertical, s.last_scraped_at;
