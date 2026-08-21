"use client";

import type { Metadata } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";

/** Keys must match `MARKETS` in backend/app/pipeline/rules.py. */
const MARKETS = ["US", "EU", "UK", "JP"];

/** Keys must match `PLATFORMS` in backend/app/pipeline/rules.py. */
const PLATFORMS = [
  { key: "etsy", label: "Etsy" },
  { key: "amazon_merch", label: "Amazon Merch" },
  { key: "tiktok_shop", label: "TikTok Shop" },
  { key: "shopify", label: "Shopify" },
  { key: "redbubble", label: "Redbubble" },
];

function toggle(list: string[], key: string) {
  return list.includes(key) ? list.filter((k) => k !== key) : [...list, key];
}

/**
 * One question — "where will this be listed?" — answered on two labelled rows.
 * Colour still separates the axes, but the row labels mean a reader does not
 * have to already know that sage means market to parse the control.
 */
export default function MetadataPicker({
  value,
  onChange,
}: {
  value: Metadata;
  onChange: (m: Metadata) => void;
}) {
  const { t } = useTranslation();

  return (
    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
      <div className="muted">{t("meta.prompt")}</div>

      <div className="chips">
        <span className="axis-label">{t("meta.markets")}</span>
        {MARKETS.map((k) => (
          <button
            key={k}
            type="button"
            className="chip"
            data-kind="market"
            data-on={value.markets.includes(k)}
            aria-pressed={value.markets.includes(k)}
            onClick={() => onChange({ ...value, markets: toggle(value.markets, k) })}
          >
            {k}
          </button>
        ))}
      </div>

      <div className="chips">
        <span className="axis-label">{t("meta.platforms")}</span>
        {PLATFORMS.map((p) => (
          <button
            key={p.key}
            type="button"
            className="chip"
            data-kind="platform"
            data-on={value.platforms.includes(p.key)}
            aria-pressed={value.platforms.includes(p.key)}
            onClick={() => onChange({ ...value, platforms: toggle(value.platforms, p.key) })}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
