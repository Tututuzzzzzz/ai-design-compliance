"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";
import type { Health } from "@/lib/types";

export default function SystemStatus() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) {
    return (
      <div className="status" data-error="true">
        {t("health.backendUnreachable")}
      </div>
    );
  }
  if (!health) return null;

  const ocrLabel =
    health.ocr.engine === "rapidocr"
      ? t("health.ocrRapid")
      : health.ocr.engine === "vision-model-fallback"
        ? t("health.ocrVisionFallback")
        : health.ocr.engine;

  // 216px of sidebar has no room for the prose hints the old health card
  // showed, nor for its long labels — hence the short keys, a value that
  // ellipsises, and the full text (plus any hint) on the row's tooltip.
  // Every register is live now, so what matters is which ones can answer — not
  // how big a local snapshot is. USPTO-public needs no credential, so it is
  // normally the one carrying the check.
  const registers = health.trademark.registers;
  const activeRegisters = [
    registers.uspto_public && "USPTO",
    registers.uspto_live && "USPTO-key",
    registers.euipo && "EUIPO",
  ].filter(Boolean) as string[];

  const items = [
    {
      k: t("health.visionShort"),
      v: health.vision.model,
      warn: !health.vision.configured,
      hint: health.vision.configured ? null : t("health.noApiKey"),
      dot: health.vision.configured,
    },
    { k: t("health.ocr"), v: ocrLabel, warn: false, hint: null, dot: false },
    {
      k: t("health.registerShort"),
      v: activeRegisters.length ? activeRegisters.join(" + ") : t("health.noRegister"),
      warn: activeRegisters.length === 0,
      hint: activeRegisters.length ? null : t("health.noRegisterHint"),
      dot: false,
    },
    {
      k: t("health.workers"),
      v: String(health.queue.workers),
      warn: false,
      hint: null,
      dot: false,
    },
  ];

  return (
    <>
      <div className="status-label">{t("health.systemStatus")}</div>
      <div className="status">
        {items.map((i) => (
          <div className="line" key={i.k} title={i.hint ? `${i.k}: ${i.v} — ${i.hint}` : `${i.k}: ${i.v}`}>
            <span className="k">{i.k}</span>
            <span className="v" data-warn={i.warn}>
              {i.dot && <span className="dot" />}
              {i.v}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
