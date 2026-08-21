"use client";

import { useTranslation } from "@/lib/i18n";
import type { DatePreset, DateWindow } from "@/lib/dates";

const PRESETS: DatePreset[] = ["all", "7d", "30d", "custom"];

export default function DateRangeFilter({
  label,
  value,
  onChange,
}: {
  label: string;
  value: DateWindow;
  onChange: (w: DateWindow) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="row" style={{ gap: 8 }}>
      <span className="muted">{label}</span>
      {PRESETS.map((p) => (
        <button
          key={p}
          type="button"
          className="chip"
          data-kind="market"
          data-on={value.preset === p}
          aria-pressed={value.preset === p}
          onClick={() => onChange({ ...value, preset: p })}
        >
          {t(`date.${p}`)}
        </button>
      ))}
      {value.preset === "custom" && (
        <span className="row" style={{ gap: 6 }}>
          <input
            type="date"
            value={value.from}
            aria-label={t("date.from")}
            // An open end is a valid range, so a blank input is left blank
            // rather than defaulted — clearing one side widens the window.
            onChange={(e) => onChange({ ...value, from: e.target.value })}
            style={{ width: "auto" }}
          />
          <span className="muted">→</span>
          <input
            type="date"
            value={value.to}
            aria-label={t("date.to")}
            onChange={(e) => onChange({ ...value, to: e.target.value })}
            style={{ width: "auto" }}
          />
        </span>
      )}
    </div>
  );
}
