-- ============================================================
-- Website Feature Catalog - SQLite schema
-- Grows over time: many sites -> many pages -> many features
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------- 1. SITES ----------------------------------------
CREATE TABLE IF NOT EXISTS sites (
    id              INTEGER PRIMARY KEY,
    domain          TEXT NOT NULL UNIQUE,      -- canonical key, e.g. "stripe.com"
    name            TEXT,                      -- "Stripe"
    homepage_url    TEXT NOT NULL,
    vertical        TEXT,                      -- SaaS / ecommerce / fintech / media ...
    business_model  TEXT,                      -- subscription / marketplace / freemium ...
    tagline         TEXT,
    description     TEXT,
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_scraped_at TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_sites_vertical ON sites(vertical);

-- ---------- 2. PAGES ----------------------------------------
CREATE TABLE IF NOT EXISTS pages (
    id            INTEGER PRIMARY KEY,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url           TEXT NOT NULL UNIQUE,
    title         TEXT,
    page_type     TEXT,                        -- homepage / pricing / features / docs / changelog
    markdown_path TEXT,                        -- relative path to the .md on disk
    content_hash  TEXT,                        -- sha256, lets us skip unchanged re-scrapes
    word_count    INTEGER,
    http_status   INTEGER,
    scrape_status TEXT NOT NULL DEFAULT 'ok',  -- ok / failed / blocked
    error         TEXT,
    scraped_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pages_site ON pages(site_id);
CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash);

-- ---------- 3. FEATURES -------------------------------------
CREATE TABLE IF NOT EXISTS features (
    id            INTEGER PRIMARY KEY,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    page_id       INTEGER REFERENCES pages(id) ON DELETE SET NULL,
    name          TEXT NOT NULL,               -- "Single Sign-On (SAML)"
    category      TEXT,                        -- auth / billing / analytics / ai / collab ...
    description   TEXT,
    evidence      TEXT,                        -- verbatim quote from the page
    confidence    REAL DEFAULT 1.0             -- 0..1, how sure we are it is a real feature
                  CHECK (confidence BETWEEN 0 AND 1),
    tier          TEXT,                        -- free / pro / enterprise / addon
    is_differentiator INTEGER DEFAULT 0,       -- 1 = marketed as a key selling point
    extracted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (site_id, name)                     -- no duplicate feature per site
);
CREATE INDEX IF NOT EXISTS idx_features_site ON features(site_id);
CREATE INDEX IF NOT EXISTS idx_features_cat  ON features(category);

-- ---------- 4. CANONICAL TAXONOMY ---------------------------
-- Lets "SSO", "SAML login" and "Single Sign-On" collapse into one
-- comparable concept across every site in the DB.
CREATE TABLE IF NOT EXISTS canonical_features (
    id       INTEGER PRIMARY KEY,
    slug     TEXT NOT NULL UNIQUE,             -- "sso"
    name     TEXT NOT NULL,                    -- "Single Sign-On"
    category TEXT
);

CREATE TABLE IF NOT EXISTS feature_links (
    feature_id   INTEGER NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    canonical_id INTEGER NOT NULL REFERENCES canonical_features(id) ON DELETE CASCADE,
    PRIMARY KEY (feature_id, canonical_id)
);

-- ---------- 5. FULL-TEXT SEARCH -----------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS features_fts USING fts5(
    name, description, evidence,
    content='features', content_rowid='id',
    tokenize='porter'
);

CREATE TRIGGER IF NOT EXISTS features_ai AFTER INSERT ON features BEGIN
  INSERT INTO features_fts(rowid,name,description,evidence)
  VALUES (new.id,new.name,new.description,new.evidence);
END;
CREATE TRIGGER IF NOT EXISTS features_ad AFTER DELETE ON features BEGIN
  INSERT INTO features_fts(features_fts,rowid,name,description,evidence)
  VALUES('delete',old.id,old.name,old.description,old.evidence);
END;
CREATE TRIGGER IF NOT EXISTS features_au AFTER UPDATE ON features BEGIN
  INSERT INTO features_fts(features_fts,rowid,name,description,evidence)
  VALUES('delete',old.id,old.name,old.description,old.evidence);
  INSERT INTO features_fts(rowid,name,description,evidence)
  VALUES(new.id,new.name,new.description,new.evidence);
END;

-- ---------- 6. CONVENIENCE VIEWS ----------------------------
CREATE VIEW IF NOT EXISTS v_features AS
SELECT s.domain, s.name AS site, f.name AS feature, f.category,
       f.description, f.tier, f.is_differentiator, f.confidence,
       p.url AS source_url, f.extracted_at
FROM features f
JOIN sites s ON s.id = f.site_id
LEFT JOIN pages p ON p.id = f.page_id;

-- How many features per site
CREATE VIEW IF NOT EXISTS v_site_summary AS
SELECT s.domain, s.name, s.vertical,
       COUNT(DISTINCT f.id) AS feature_count,
       COUNT(DISTINCT p.id) AS page_count,
       s.last_scraped_at
FROM sites s
LEFT JOIN features f ON f.site_id = s.id
LEFT JOIN pages    p ON p.site_id = s.id
GROUP BY s.id;

-- Which canonical features show up on the most sites (the payoff view)
CREATE VIEW IF NOT EXISTS v_feature_prevalence AS
SELECT c.slug, c.name, c.category,
       COUNT(DISTINCT f.site_id) AS site_count,
       GROUP_CONCAT(DISTINCT s.domain) AS sites
FROM canonical_features c
JOIN feature_links l ON l.canonical_id = c.id
JOIN features f      ON f.id = l.feature_id
JOIN sites s         ON s.id = f.site_id
GROUP BY c.id
ORDER BY site_count DESC;

-- ---------- 7. VISUAL ANNOTATIONS ---------------------------
-- Where each feature physically appears on the rendered page,
-- plus the screenshots proving it.
CREATE TABLE IF NOT EXISTS annotations (
    id              INTEGER PRIMARY KEY,
    feature_id      INTEGER NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    page_id         INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    screenshot_path TEXT,                    -- full page, all features circled
    crop_path       TEXT,                    -- close-up of just this feature
    x               INTEGER,
    y               INTEGER,
    w               INTEGER,
    h               INTEGER,
    matched_text    TEXT,                    -- the text we actually located
    match_method    TEXT,                    -- exact / fragment / keyword / failed
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (feature_id)
);
CREATE INDEX IF NOT EXISTS idx_annot_page ON annotations(page_id);

CREATE VIEW IF NOT EXISTS v_annotated AS
SELECT s.domain, f.name AS feature, f.category, a.match_method,
       a.x, a.y, a.w, a.h, a.crop_path, a.screenshot_path, p.url
FROM annotations a
JOIN features f ON f.id = a.feature_id
JOIN sites s    ON s.id = f.site_id
LEFT JOIN pages p ON p.id = a.page_id;

-- ---------- 8. CAPTURE JOBS ---------------------------------
-- Queued from the web UI; run by scripts/capture.py
CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY,
    url            TEXT NOT NULL,
    domain         TEXT,
    site_name      TEXT,
    stage          TEXT NOT NULL DEFAULT 'queued',
        -- queued > discovering > scraping > awaiting_extraction > extracted
        -- > annotated  (or: failed)
    status         TEXT NOT NULL DEFAULT 'running',   -- running / ok / failed
    message        TEXT,
    pages_found    INTEGER NOT NULL DEFAULT 0,
    pages_scraped  INTEGER NOT NULL DEFAULT 0,
    pages_failed   INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, id DESC);
