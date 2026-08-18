"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";
import type { Health } from "@/lib/types";

export default function HealthBar() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <div className="error">{t("health.backendUnreachable")}: {error}</div>;
  if (!health) return null;

  const ocrLabel =
    health.ocr.engine === "rapidocr"
      ? t("health.ocrRapid")
      : health.ocr.engine === "vision-model-fallback"
        ? t("health.ocrVisionFallback")
        : health.ocr.engine;

  const items = [
    {
      k: t("health.visionModel"),
      v: `${health.vision.model}`,
      warn: !health.vision.configured,
      hint: health.vision.configured ? null : t("health.noApiKey"),
    },
    { k: t("health.ocr"), v: ocrLabel, warn: false, hint: null },
    {
      k: t("health.trademarkIndex"),
      v: health.trademark.available
        ? `${health.trademark.marks.toLocaleString()} ${t("health.marks")}`
        : t("health.notBuilt"),
      warn: !health.trademark.available,
      hint: health.trademark.available
        ? null
        : t("health.trademarkHint"),
    },
    { k: t("health.workers"), v: String(health.queue.workers), warn: false, hint: null },
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
