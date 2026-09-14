"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PdpFeature } from "@/lib/pdp-db";

/**
 * Plates are captured at device_scale_factor = 2 but SERVED at DPR 1: WebP
 * cannot encode a dimension over 16,383 px and 28 plates were taller than that,
 * so `scripts/to_webp.py` halves every one. Annotation boxes are stored in CSS
 * pixels, so at DPR 1 the served image maps 1:1 and this divisor is 1.
 *
 * This constant and HALVE in to_webp.py are one decision in two languages.
 * Change either alone and every circle moves, with no error anywhere.
 */
const SCALE = 1;

export default function Plate({
  shot,
  clean,
  features,
}: {
  shot: string;
  clean: string | null;
  features: PdpFeature[];
}) {
  // Start on the clean plate: the overlays below are ours to control, and a
  // plate with circles already burned in double-draws every box.
  const [useClean, setUseClean] = useState(Boolean(clean));
  const [showPins, setShowPins] = useState(true);
  const [active, setActive] = useState<number | null>(null);
  const [locked, setLocked] = useState<number | null>(null);
  const [doc, setDoc] = useState<{ w: number; h: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  const measure = useCallback((img: HTMLImageElement | null) => {
    if (img && img.naturalWidth) {
      setDoc({ w: img.naturalWidth / SCALE, h: img.naturalHeight / SCALE });
    }
  }, []);

  const src = useClean && clean ? clean : shot;

  // A cached image is often already complete before hydration, so onLoad never
  // fires. Measure on mount and on every plate swap.
  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete) measure(img);
  }, [src, measure]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLocked(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const select = (id: number) => {
    const next = locked === id ? null : id;
    setLocked(next);
    setActive(next);
    if (next != null) {
      document
        .getElementById(`pdphot-${next}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  const lockedRow = features.find((f) => f.id === locked) ?? null;

  return (
    <>
      <div className="toolbar">
        {clean ? (
          <button
            className="toggle"
            data-on={useClean}
            onClick={() => setUseClean((v) => !v)}
          >
            {useClean ? "Clean plate" : "Burned-in circles"}
          </button>
        ) : null}
        <button
          className="toggle"
          data-on={showPins}
          onClick={() => setShowPins((v) => !v)}
        >
          {showPins ? "Overlays on" : "Overlays off"}
        </button>
        {locked != null ? (
          <button className="toggle" onClick={() => setLocked(null)}>
            Clear spotlight (Esc)
          </button>
        ) : null}
        <span
          className="mono"
          style={{ color: "var(--text-faint)", fontSize: ".78rem" }}
        >
          {lockedRow
            ? lockedRow.name
            : `${features.length} circled${
                doc ? ` · ${Math.round(doc.w)}×${Math.round(doc.h)} css px` : ""
              }`}
        </span>
      </div>

      <div className="viewer">
        <div className="plate" data-locked={locked != null}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            ref={imgRef}
            src={src}
            alt="product page capture"
            onLoad={(e) => measure(e.currentTarget)}
          />

          {showPins && doc
            ? features.map((f, i) => {
                if (f.x == null || f.y == null || f.w == null || f.h == null)
                  return null;
                // mirror the padding scripts/annotate.py draws with
                const px = Math.max(12, Math.min(46, f.w * 0.08));
                const py = Math.max(10, Math.min(34, f.h * 0.22));
                const isLocked = locked === f.id;
                return (
                  <div
                    key={f.id}
                    id={`pdphot-${f.id}`}
                    className="hot"
                    data-method={f.match_method}
                    data-active={active === f.id}
                    data-locked={isLocked}
                    style={{
                      left: `${((f.x - px) / doc.w) * 100}%`,
                      top: `${((f.y - py) / doc.h) * 100}%`,
                      width: `${((f.w + px * 2) / doc.w) * 100}%`,
                      height: `${((f.h + py * 2) / doc.h) * 100}%`,
                    }}
                    onMouseEnter={() => setActive(f.id)}
                    onMouseLeave={() => setActive(locked)}
                    onClick={() => select(f.id)}
                    title={f.name}
                  >
                    <span className="pin mono">{i + 1}</span>
                    {isLocked ? <span className="lockcap">{f.name}</span> : null}
                  </div>
                );
              })
            : null}
        </div>

        <aside className="rail">
          <div className="rail-head">
            <strong style={{ fontSize: ".85rem" }}>What each circle is</strong>
            <span
              className="mono"
              style={{
                marginLeft: "auto",
                color: "var(--text-faint)",
                fontSize: ".76rem",
              }}
            >
              {features.length}
            </span>
          </div>

          {features.map((f, i) => (
            <div
              key={f.id}
              className="pdp-expl"
              data-active={active === f.id}
              data-locked={locked === f.id}
              onMouseEnter={() => setActive(f.id)}
              onMouseLeave={() => setActive(locked)}
              onClick={() => select(f.id)}
            >
              <span className="pdp-n mono">{i + 1}</span>
              <div>
                <strong>
                  {f.is_differentiator ? <span className="star">★ </span> : null}
                  {f.name}
                </strong>
                <div className="pdp-meta mono">
                  {f.category}
                  {f.canonical && f.canonical !== f.name
                    ? ` · ${f.canonical}`
                    : ""}
                  {f.tier ? ` · ${f.tier}` : ""}
                </div>
                {f.description ? <p className="pdp-why">{f.description}</p> : null}
                {f.evidence ? <p className="pdp-quote">“{f.evidence}”</p> : null}
                {/* When the annotator located something narrower than the quoted
                    evidence, say what the circle is actually around rather than
                    letting the quote imply more than was matched. */}
                {f.matched_text &&
                f.matched_text.trim() &&
                f.matched_text.trim() !== (f.evidence ?? "").trim() ? (
                  <p className="pdp-meta mono" style={{ marginTop: 4 }}>
                    circled: “{f.matched_text}”
                  </p>
                ) : null}
              </div>
            </div>
          ))}

          {features.length === 0 ? (
            <div className="empty">
              Nothing circled on this plate yet — run the annotator.
            </div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
