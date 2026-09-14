import Link from "next/link";
import type { Feature } from "@/lib/db";

export default function FeatureRows({
  features,
  showSite = false,
}: {
  features: Feature[];
  showSite?: boolean;
}) {
  if (features.length === 0) {
    return <div className="empty">No features match.</div>;
  }
  return (
    <div className="flist">
      {features.map((f) => (
        <div key={f.id} className="frow">
          <div>
            <h4>
              {f.is_differentiator ? <span className="star">★ </span> : null}
              {f.name}
            </h4>
            {f.description ? <div className="desc">{f.description}</div> : null}
            {f.evidence ? (
              <div className="ev mono">“{f.evidence}”</div>
            ) : null}
            <div
              style={{
                display: "flex",
                gap: 10,
                marginTop: 10,
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              {showSite ? (
                <Link href={`/sites/${f.domain}`} className="chip">
                  {f.domain}
                </Link>
              ) : null}
              {f.page_url ? (
                <a
                  href={f.page_url}
                  target="_blank"
                  rel="noreferrer"
                  className="chip"
                >
                  {f.page_type ?? "page"} ↗
                </a>
              ) : null}
              {f.crop_path ? (
                <a
                  href={`/api/shot?p=${encodeURIComponent(f.crop_path)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="chip"
                  data-on="true"
                >
                  view proof
                </a>
              ) : null}
            </div>
          </div>

          <div className="meta">
            <span className="cat">{f.category ?? "—"}</span>
            {f.tier ? (
              <span className="tag" data-tier={f.tier}>
                {f.tier}
              </span>
            ) : null}
            {f.confidence != null ? (
              <span
                className="mono"
                style={{ fontSize: ".7rem", color: "var(--text-faint)" }}
              >
                conf {f.confidence.toFixed(2)}
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
