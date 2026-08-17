"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";

export default function HealthBar() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <div className="error">Backend unreachable: {error}</div>;
  if (!health) return null;

  const items = [
    {
      k: "Vision model",
      v: `${health.vision.model}`,
      warn: !health.vision.configured,
      hint: health.vision.configured ? null : "No API key set for this provider",
    },
    { k: "OCR", v: health.ocr.engine, warn: false, hint: null },
    {
      k: "Trademark index",
      v: health.trademark.available
        ? `${health.trademark.marks.toLocaleString()} marks`
        : "not built",
      warn: !health.trademark.available,
      hint: health.trademark.available
        ? null
        : "Run `python -m data.build_uspto_index --daily 10` for offline matching",
    },
    { k: "Workers", v: String(health.queue.workers), warn: false, hint: null },
  ];

  return (
    <div className="card">
      <div className="row" style={{ gap: 22 }}>
        {items.map((i) => (
          <div key={i.k}>
            <div className="muted" style={{ fontSize: 11, textTransform: "uppercase" }}>
              {i.k}
            </div>
            <div style={{ fontSize: 13, color: i.warn ? "var(--risky)" : "var(--text)" }}>
              {i.v}
            </div>
          </div>
        ))}
      </div>
      {items
        .filter((i) => i.hint)
        .map((i) => (
          <p key={i.k} className="muted" style={{ marginBottom: 0, marginTop: 10 }}>
            {i.k}: {i.hint}
          </p>
        ))}
    </div>
  );
}
