import { getPrevalence, getSites } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Compare() {
  const [sites, rows] = await Promise.all([getSites(), getPrevalence()]);
  const domains = sites.map((s) => s.domain);

  const shared = rows.filter((r) => r.site_count > 1);

  return (
    <div className="section" style={{ paddingTop: 40 }}>
      <div className="section-head">
        <h2>Cross-site comparison</h2>
        <span className="count mono">
          {rows.length} canonical features · {shared.length} shared
        </span>
      </div>

      <p className="lede" style={{ marginTop: 0, marginBottom: 26 }}>
        Raw feature names differ between vendors, so each is mapped to a
        canonical concept. That is what makes “who else ships this?” answerable.
      </p>

      <div className="flist" style={{ overflowX: "auto" }}>
        <div
          className="frow"
          style={{
            gridTemplateColumns: `minmax(220px,1fr) repeat(${domains.length}, 130px)`,
            background: "var(--surface-2)",
            position: "sticky",
            top: 0,
            zIndex: 1,
          }}
        >
          <div className="cat">Canonical feature</div>
          {domains.map((d) => (
            <div key={d} className="cat" style={{ textAlign: "center" }}>
              {d}
            </div>
          ))}
        </div>

        {rows.map((r) => {
          const present = new Set(r.sites.split(","));
          return (
            <div
              key={r.slug}
              className="frow"
              style={{
                gridTemplateColumns: `minmax(220px,1fr) repeat(${domains.length}, 130px)`,
              }}
            >
              <div>
                <h4 style={{ fontSize: ".92rem" }}>{r.name}</h4>
                <span className="cat">{r.category ?? "—"}</span>
              </div>
              {domains.map((d) => (
                <div
                  key={d}
                  className="mono"
                  style={{
                    textAlign: "center",
                    alignSelf: "center",
                    color: present.has(d) ? "var(--signal)" : "var(--text-faint)",
                    fontWeight: present.has(d) ? 700 : 400,
                  }}
                >
                  {present.has(d) ? "●" : "·"}
                </div>
              ))}
            </div>
          );
        })}
      </div>
      {rows.length === 0 ? (
        <div className="empty">No canonical features linked yet.</div>
      ) : null}
    </div>
  );
}
