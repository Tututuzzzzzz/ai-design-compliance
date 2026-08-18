"use client";

import type { Metadata } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";

const MARKETS = [
  { key: "US", label: "United States" },
  { key: "EU", label: "European Union" },
  { key: "UK", label: "United Kingdom" },
  { key: "JP", label: "Japan" },
];

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

export default function MetadataPicker({
  value,
  onChange,
}: {
  value: Metadata;
  onChange: (m: Metadata) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="grid two">
      <div className="field">
        <label>{t("meta.targetMarkets")}</label>
        <div className="chips">
          {MARKETS.map((m) => (
            <button
              key={m.key}
              type="button"
              className="chip"
              data-on={value.markets.includes(m.key)}
              onClick={() => onChange({ ...value, markets: toggle(value.markets, m.key) })}
            >
              {m.label}
            </button>
          ))}
        </div>
        <p className="muted" style={{ marginTop: 6 }}>
          {t("meta.marketsHelp")}
        </p>
      </div>

      <div className="field">
        <label>{t("meta.sellingPlatforms")}</label>
        <div className="chips">
          {PLATFORMS.map((p) => (
            <button
              key={p.key}
              type="button"
              className="chip"
              data-on={value.platforms.includes(p.key)}
              onClick={() => onChange({ ...value, platforms: toggle(value.platforms, p.key) })}
            >
              {p.label}
            </button>
          ))}
        </div>
        <p className="muted" style={{ marginTop: 6 }}>
          {t("meta.platformsHelp")}
        </p>
      </div>
    </div>
  );
}
