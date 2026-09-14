import { spawn } from "node:child_process";
import path from "node:path";
import { NextRequest } from "next/server";
import { createJob, listJobs, READONLY } from "@/lib/db";

const ROOT = process.env.CATALOG_ROOT ?? path.join(process.cwd(), "..");
const PYTHON = process.env.CATALOG_PYTHON ?? "python";

/** Only public http(s) targets - never let the crawler be pointed inward. */
function validate(raw: string): { url: string } | { error: string } {
  let u: URL;
  try {
    u = new URL(raw.trim());
  } catch {
    return { error: "That is not a valid URL." };
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return { error: "Only http and https URLs are supported." };
  }
  const host = u.hostname.toLowerCase();
  const blocked =
    host === "localhost" ||
    host === "0.0.0.0" ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    /^127\./.test(host) ||
    /^10\./.test(host) ||
    /^192\.168\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
    /^169\.254\./.test(host) ||
    host === "[::1]";
  if (blocked) return { error: "Private and loopback hosts are not allowed." };
  if (!host.includes(".")) return { error: "That host does not look public." };
  return { url: u.toString() };
}

export async function GET() {
  // Reading the job list is safe even on a read-only deployment — it is what
  // lets the read-only capture page still show recent jobs.
  return Response.json({ jobs: await listJobs(30) });
}

export async function POST(req: NextRequest) {
  if (READONLY) {
    return Response.json(
      {
        error:
          "This deployment is read-only. Capture runs on the local machine; " +
          "publish results with scripts/publish.py.",
      },
      { status: 403 }
    );
  }

  let body: { url?: string; name?: string };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Expected JSON body." }, { status: 400 });
  }

  const checked = validate(body.url ?? "");
  if ("error" in checked) {
    return Response.json({ error: checked.error }, { status: 400 });
  }

  const name = (body.name ?? "").trim() || null;
  let id: number;
  try {
    id = await createJob(checked.url, name);
  } catch (e) {
    return Response.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }

  // detached so the HTTP request returns immediately; progress lands in `jobs`
  try {
    const child = spawn(
      PYTHON,
      [path.join(ROOT, "scripts", "capture.py"), "--job", String(id)],
      { cwd: ROOT, detached: true, stdio: "ignore", windowsHide: true }
    );
    child.unref();
  } catch (e) {
    return Response.json(
      { error: `Could not start capture: ${String(e)}` },
      { status: 500 }
    );
  }

  return Response.json({ id, url: checked.url });
}
