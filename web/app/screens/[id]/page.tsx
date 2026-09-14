import Link from "next/link";
import { notFound } from "next/navigation";
import { cleanPlate, getAnnotations, getPage, plateUrl } from "@/lib/db";
import Viewer from "./viewer";

export const dynamic = "force-dynamic";

export default async function Screen({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const page = await getPage(Number(id));
  if (!page) notFound();

  const shotUrl = plateUrl(page.shot);
  if (!shotUrl) {
    return (
      <>
        <div className="crumb">
          <Link href="/screens">Screens</Link> <span>/</span>
          <span>{page.title ?? page.url}</span>
        </div>
        <div className="empty">
          No screenshot captured for this page yet. Run:
          <br />
          <code className="mono">
            .venv/Scripts/python scripts/annotate.py --url {page.url}
          </code>
        </div>
      </>
    );
  }

  const annotations = await getAnnotations(page.id);
  // Plates and their clean twin are always published together by
  // scripts/publish.py, so — unlike the old on-disk fs.existsSync check —
  // no existence probe is needed: the storage object key is derived directly.
  const cleanUrl = plateUrl(cleanPlate(page.shot));

  return (
    <>
      <div className="crumb">
        <Link href="/screens">Screens</Link> <span>/</span>
        <Link href={`/sites/${page.domain}`}>{page.domain}</Link> <span>/</span>
        <span className="mono">{page.page_type}</span>
      </div>

      <div className="section-head" style={{ marginTop: 18 }}>
        <h2>{page.title?.trim() || page.url}</h2>
        <span className="count mono">
          <a href={page.url} target="_blank" rel="noreferrer">
            open live ↗
          </a>
        </span>
      </div>

      <Viewer shot={shotUrl} clean={cleanUrl} annotations={annotations} />
    </>
  );
}
