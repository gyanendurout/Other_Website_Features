"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Annotation } from "@/lib/db";

/**
 * Plates are captured at device_scale_factor = 2 but SERVED at DPR 1: WebP
 * cannot encode a dimension over 16,383 px and 28 plates were taller than that,
 * so `scripts/to_webp.py` halves every one. Annotation boxes are stored in CSS
 * pixels, so at DPR 1 the served image maps 1:1 and this divisor is 1.
 *
 * This constant and HALVE in to_webp.py are one decision in two languages.
 * Change either alone and every circle moves, with no error anywhere.
 */
const SCALE = 1; // plates are SERVED at DPR 1 — see scripts/to_webp.py

export default function Viewer({
  shot,
  clean,
  annotations,
}: {
  shot: string;
  clean: string | null;
  annotations: Annotation[];
}) {
  // default to the clean plate so overlays are ours to control
  const [useClean, setUseClean] = useState(Boolean(clean));
  const [showPins, setShowPins] = useState(true);
  // hover is transient and red; locked is a click and stays cyan until cleared
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

  // the image is often already cached and complete before hydration, so
  // onLoad never fires - measure on mount and whenever the plate swaps
  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete) measure(img);
  }, [src, measure]);

  // Escape clears the lock - the only way out that does not need a mouse
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLocked(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /** Click toggles the spotlight and scrolls the circle into view. */
  const select = (id: number) => {
    const next = locked === id ? null : id;
    setLocked(next);
    setActive(next);
    if (next != null) {
      document
        .getElementById(`hot-${next}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  const lockedRow = annotations.find((a) => a.feature_id === locked) ?? null;

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
        <span className="mono" style={{ color: "var(--text-faint)", fontSize: ".8rem" }}>
          {lockedRow
            ? lockedRow.name
            : `${annotations.length} pinned${
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
            alt="page capture"
            onLoad={(e) => measure(e.currentTarget)}
          />

          {showPins && doc
            ? annotations.map((a, i) => {
                if (a.x == null || a.y == null || a.w == null || a.h == null)
                  return null;
                // mirror the padding the Python annotator uses
                const px = Math.max(12, Math.min(46, a.w * 0.08));
                const py = Math.max(10, Math.min(34, a.h * 0.22));
                const left = ((a.x - px) / doc.w) * 100;
                const top = ((a.y - py) / doc.h) * 100;
                const width = ((a.w + px * 2) / doc.w) * 100;
                const height = ((a.h + py * 2) / doc.h) * 100;
                const isLocked = locked === a.feature_id;
                return (
                  <div
                    key={a.feature_id}
                    id={`hot-${a.feature_id}`}
                    className="hot"
                    data-method={a.match_method}
                    data-active={active === a.feature_id}
                    data-locked={isLocked}
                    style={{
                      left: `${left}%`,
                      top: `${top}%`,
                      width: `${width}%`,
                      height: `${height}%`,
                    }}
                    onMouseEnter={() => setActive(a.feature_id)}
                    onMouseLeave={() => setActive(locked)}
                    onClick={() => select(a.feature_id)}
                    title={a.name}
                  >
                    <span className="pin mono">{i + 1}</span>
                    {isLocked ? <span className="lockcap">{a.name}</span> : null}
                  </div>
                );
              })
            : null}
        </div>

        <aside className="rail">
          <div className="rail-head">
            <strong style={{ fontSize: ".85rem" }}>Features on this page</strong>
            <span
              className="mono"
              style={{ marginLeft: "auto", color: "var(--text-faint)", fontSize: ".76rem" }}
            >
              {annotations.length}
            </span>
          </div>
          {annotations.map((a, i) => (
            <div
              key={a.feature_id}
              className="railrow"
              data-active={active === a.feature_id}
              data-locked={locked === a.feature_id}
              onMouseEnter={() => setActive(a.feature_id)}
              onMouseLeave={() => setActive(locked)}
              onClick={() => select(a.feature_id)}
            >
              <span className="num mono">{i + 1}</span>
              <div>
                <strong>
                  {a.is_differentiator ? <span className="star">★ </span> : null}
                  {a.name}
                </strong>
                <p>
                  {a.category}
                  {a.tier ? ` · ${a.tier}` : ""}
                  {a.match_method ? ` · ${a.match_method}` : ""}
                </p>
                {locked === a.feature_id && a.evidence ? (
                  <p style={{ color: "var(--text-dim)", marginTop: 6 }}>
                    “{a.evidence}”
                  </p>
                ) : null}
              </div>
            </div>
          ))}
          {annotations.length === 0 ? (
            <div className="empty">Nothing pinned on this page yet.</div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
