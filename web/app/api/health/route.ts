import { NextResponse } from "next/server";
import { getSql, READONLY } from "@/lib/pg";

export const dynamic = "force-dynamic";

/**
 * Configuration and connectivity probe.
 *
 * ## Why this exists
 *
 * A Vercel deployment that cannot reach Postgres renders
 * "Application error: a server-side exception has occurred" plus a digest —
 * a hash with no information in it. The real message is in the function log,
 * which you cannot see from outside the deployment. Every page that queries
 * the database returns an identical, contentless 500, so there is no way to
 * tell a missing environment variable from a wrong password from a wrong host.
 *
 * This reports the *shape* of the configuration and the actual driver error,
 * so one request identifies the cause.
 *
 * ## What it deliberately does not return
 *
 * Never the password, the host, or the connection string. This deployment is
 * public. What it does return is structural — is the variable present, is the
 * port the transaction pooler's, does the username carry the project-ref
 * suffix the pooler requires — none of which is a credential, and each of
 * which is a cause of exactly this failure.
 */

/** Structural facts about DATABASE_URL. No secret is included. */
function describeUrl(raw: string | undefined) {
  if (!raw) return { present: false as const };
  if (raw.includes("[YOUR-PASSWORD]") || raw.includes("YOUR-PASSWORD")) {
    return { present: true as const, parsed: false as const,
             problem: "still contains the dashboard's [YOUR-PASSWORD] placeholder" };
  }
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return { present: true as const, parsed: false as const,
             problem: "not a parseable URI (stray quotes or a line break?)" };
  }
  const port = u.port || "(default 5432)";
  return {
    present: true as const,
    parsed: true as const,
    scheme: u.protocol.replace(":", ""),
    port,
    // Supabase's pooler authenticates as "<role>.<project-ref>". Copying the
    // role name in without the suffix is accepted by the URI parser and
    // rejected at login, which looks like a wrong password.
    usernameHasProjectRefSuffix: u.username.includes("."),
    hostLooksLikePooler: u.hostname.includes("pooler.supabase.com"),
    // 6543 is transaction mode, which is what serverless needs; 5432 is the
    // session pooler or a direct connection, which exhausts under real traffic.
    portIsTransactionPooler: port === "6543",
  };
}

export async function GET() {
  const url = describeUrl(process.env.DATABASE_URL);

  const config = {
    DATABASE_URL: url,
    NEXT_PUBLIC_SUPABASE_URL: Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL),
    CATALOG_READONLY: READONLY,
    region: process.env.VERCEL_REGION ?? "(not on Vercel)",
  };

  if (!url.present) {
    return NextResponse.json(
      { ok: false, cause: "DATABASE_URL is not set in this environment",
        hint: "In Vercel, environment variables are scoped per environment. " +
              "Confirm it is set for Production, then redeploy - an existing " +
              "deployment does not pick up a variable added after it was built.",
        config },
      { status: 503 }
    );
  }

  const started = Date.now();
  try {
    const rows = await getSql().unsafe(
      `select current_user as role,
              (select count(*)::int from catalog.features) as catalog_features,
              (select count(*)::int from pdp.features)     as pdp_features`
    );
    return NextResponse.json({
      ok: true, ms: Date.now() - started,
      db: (rows as unknown as Record<string, unknown>[])[0], config,
    });
  } catch (e) {
    const err = e as { code?: string; message?: string };
    return NextResponse.json(
      { ok: false, ms: Date.now() - started,
        code: err.code ?? null,
        message: (err.message ?? String(e)).slice(0, 300),
        meaning: explain(err.code),
        config },
      { status: 503 }
    );
  }
}

/** Map the driver's code to the configuration mistake that produces it. */
function explain(code: string | undefined): string {
  switch (code) {
    case "28P01": return "password authentication failed - wrong password, or the username is missing the .<project-ref> suffix the pooler requires";
    case "28000": return "the role was rejected - check the username";
    case "3D000": return "that database does not exist - it should be 'postgres'";
    case "42P01": return "connected, but a table is missing - schema.sql has not been applied to this project";
    case "42501": return "connected, but permission was denied - catalog_read is missing its GRANTs";
    case "ENOTFOUND": return "the hostname does not resolve - check the host";
    case "ETIMEDOUT":
    case "ENETUNREACH": return "no route to the host - this is what a direct (IPv6-only) connection looks like from a serverless function; use the transaction pooler on 6543";
    case "ECONNREFUSED": return "the host resolved but refused the port";
    default: return "see the message above";
  }
}
