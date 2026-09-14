import Link from "next/link";
import { getPages, plateUrl } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Screens() {
  const pages = await getPages();
  return (
    <>
      <div className="section" style={{ paddingTop: 40 }}>
        <div className="section-head">
          <h2>Captured screens</h2>
          <span className="count mono">{pages.length} pages</span>
        </div>
        <div className="pagelist">
          {pages.map((p) => (
            <Link key={p.id} href={`/screens/${p.id}`} className="pcard">
              <div className="thumb">
                {p.shot ? (
                  <img
                    src={plateUrl(p.shot) ?? ""}
                    alt={p.title ?? p.url}
                    loading="lazy"
                  />
                ) : (
                  <div className="empty" style={{ fontSize: ".8rem" }}>
                    not annotated
                  </div>
                )}
              </div>
              <div className="body">
                <b>{p.title?.trim() || p.url}</b>
                <div className="mono">
                  {p.domain} · {p.page_type} · {p.feature_count} features ·{" "}
                  {p.word_count ?? 0} words
                </div>
              </div>
            </Link>
          ))}
        </div>
        {pages.length === 0 ? <div className="empty">No pages captured.</div> : null}
      </div>
    </>
  );
}
