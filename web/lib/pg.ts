import postgres from "postgres";

/**
 * One Postgres client for the whole app, plus the helpers the two catalog
 * modules share.
 *
 * ## Why these connection options are not negotiable
 *
 * Vercel runs each request in its own short-lived function instance, so a
 * normal connection pool would open a socket per instance and exhaust Postgres
 * in minutes. The fix is Supabase's **transaction pooler** (port 6543), and a
 * transaction-mode pooler hands the same backend connection to different
 * clients between statements. That makes server-side prepared statements
 * unusable — they live on the backend connection, and the next client to get it
 * has never heard of them. Hence `prepare: false`. Without it this works
 * locally against a direct connection and fails in production under
 * concurrency, which is the worst way to find out.
 */
/**
 * The client is created on first query, not at import.
 *
 * `next build` imports every route module to collect them, so connecting (or
 * throwing) at module scope would make the build itself require a live
 * database — CI, a fresh clone and a preview deploy would all fail before
 * rendering anything. Deferring means a missing DATABASE_URL surfaces as a
 * clear error on the first request instead.
 */
let _sql: ReturnType<typeof postgres> | null = null;

export function getSql(): ReturnType<typeof postgres> {
  if (_sql) return _sql;
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. The web app needs the Supabase TRANSACTION " +
        "pooler URI (port 6543) — Project Settings > Database > Connection string."
    );
  }
  _sql = postgres(url, {
    prepare: false, // required: pgbouncer in transaction mode
    max: 1, // one socket per serverless invocation
    idle_timeout: 20,
    connect_timeout: 10,
  });
  return _sql;
}

/** Rows for a query written with $1, $2 … placeholders. */
export async function all_<T>(query: string, ...params: unknown[]): Promise<T[]> {
  return (await getSql().unsafe(query, params as never[])) as unknown as T[];
}

/** First row, or undefined. */
export async function one<T>(
  query: string,
  ...params: unknown[]
): Promise<T | undefined> {
  const rows = (await getSql().unsafe(query, params as never[])) as unknown as T[];
  return rows[0];
}

// ---------------------------------------------------------------- images

/**
 * Plates live in a public Supabase Storage bucket rather than the repo: 695 MB
 * of PNG would not survive a Git push or a Vercel deploy. `publish.py` stores
 * the object key (`pdp/arrae.com/foo.webp`), and this turns it into a URL.
 */
const STORAGE_BASE =
  process.env.NEXT_PUBLIC_PLATE_BASE ??
  (process.env.NEXT_PUBLIC_SUPABASE_URL
    ? `${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/public/plates`
    : "");

export function plateUrl(key: string | null | undefined): string | null {
  if (!key) return null;
  if (/^https?:\/\//i.test(key)) return key; // already absolute
  return `${STORAGE_BASE}/${key.replace(/^\/+/, "")}`;
}

/**
 * The un-circled twin of a plate. `annotate.py` writes `<page>-clean.png`
 * alongside `<page>.png`; after conversion those are `.webp`, so this swaps on
 * the WebP extension. Swapping on `.png` here silently returns null for every
 * plate and the viewer loses its clean-plate toggle with no error.
 */
export function cleanPlate(key: string | null): string | null {
  if (!key) return null;
  return key.replace(/\.webp$/i, "-clean.webp");
}

/** True when the deployment must not offer write actions (Vercel). */
export const READONLY = process.env.CATALOG_READONLY === "1";
