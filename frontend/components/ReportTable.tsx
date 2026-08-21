"use client";

import { useTranslation } from "@/lib/i18n";
import type { Flag } from "@/lib/flags";
import type { Design } from "@/lib/types";

export type SortKey = "name" | "verdict" | "niche" | "findings" | "conf";

const VERDICT_ICON: Record<string, string> = { SAFE: "✓", RISKY: "!", BLOCKED: "✕", PENDING: "·" };

export default function ReportTable({
  designs,
  selected,
  sortKey,
  sortDir,
  flags,
  onSort,
  onSelect,
  onClearFilters,
}: {
  designs: Design[];
  selected: string | null;
  sortKey: SortKey;
  sortDir: number;
  flags: Record<string, Exclude<Flag, null>>;
  onSort: (key: SortKey) => void;
  onSelect: (id: string) => void;
  onClearFilters: () => void;
}) {
  const { t } = useTranslation();

  const headers: { key: SortKey; label: string; align?: "right"; title?: string }[] = [
    { key: "name", label: t("report.design") },
    { key: "verdict", label: t("job.verdict") },
    { key: "niche", label: t("detail.niche") },
    { key: "findings", label: t("detail.findings") },
    {
      key: "conf",
      label: t("messages.confidence"),
      align: "right",
      title: t("report.confidenceHint"),
    },
  ];

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(designs[index].id);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = index + (e.key === "ArrowDown" ? 1 : -1);
      if (next >= 0 && next < designs.length) {
        document.getElementById(`row-${designs[next].id}`)?.focus();
      }
    }
  }

  return (
    <div className="report-scroll">
      <div className="report" role="grid" aria-label={t("report.title")}>
        <div className="r head" role="row">
          {headers.map((h) => {
            const active = sortKey === h.key;
            return (
              <div
                key={h.key}
                role="columnheader"
                aria-sort={active ? (sortDir === 1 ? "ascending" : "descending") : "none"}
                title={h.title}
                style={{ textAlign: h.align }}
              >
                <button type="button" onClick={() => onSort(h.key)}>
                  {h.label}
                  <span aria-hidden="true" style={{ fontSize: 10 }}>
                    {active ? (sortDir === 1 ? "▲" : "▼") : ""}
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        {designs.map((d, i) => {
          const verdict = d.verdict ?? "PENDING";
          const findings = d.report?.findings ?? [];
          const extra = findings.length - 1;
          const flag = flags[d.id];
          return (
            <div
              key={d.id}
              id={`row-${d.id}`}
              className="r body-row"
              role="row"
              tabIndex={i === 0 ? 0 : -1}
              data-selected={selected === d.id}
              onClick={() => onSelect(d.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
            >
              <div
                role="gridcell"
                className="row"
                style={{ gap: 12, flexWrap: "nowrap", minWidth: 0 }}
              >
                <span className={`tile ${verdict}`} aria-hidden="true">
                  {VERDICT_ICON[verdict]}
                </span>
                <span className="name" title={d.filename}>
                  {d.filename}
                </span>
              </div>
              <div role="gridcell" className="row" style={{ gap: 6 }}>
                <span className={`badge ${verdict}`}>
                  {d.verdict ? t(`verdict.${d.verdict}`) : t(`status.${d.status}`)}
                </span>
                {flag && <span className="flag">{t(`flag.${flag}`)}</span>}
              </div>
              <div role="gridcell" className="cell">
                {d.niche ?? "—"}
              </div>
              <div role="gridcell" className="cell row" style={{ gap: 8, flexWrap: "nowrap" }}>
                <span className="clip">{findings.length ? findings[0].title : "—"}</span>
                {extra > 0 && (
                  <span
                    className={`badge ${verdict}`}
                    style={{ flex: "none", fontSize: 12, padding: "1px 8px" }}
                  >
                    +{extra}
                  </span>
                )}
              </div>
              <div role="gridcell" className="conf">
                {d.confidence != null ? `${d.confidence}%` : "—"}
              </div>
            </div>
          );
        })}

        {designs.length === 0 && (
          <div className="empty">
            <div className="muted">{t("report.noMatch")}</div>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ marginTop: 12 }}
              onClick={onClearFilters}
            >
              {t("report.clearFilters")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** Shared ordering so the dashboard and the export view agree on row order. */
export function sortDesigns(
  designs: Design[],
  sortKey: SortKey,
  sortDir: number,
  flags: Record<string, Exclude<Flag, null>>,
): Design[] {
  const order: Record<string, number> = { BLOCKED: 0, RISKY: 1, SAFE: 2, PENDING: 3 };
  const value = (d: Design): string | number => {
    switch (sortKey) {
      case "name":
        return d.filename.toLowerCase();
      case "niche":
        return (d.niche ?? "").toLowerCase();
      case "findings":
        return d.report?.findings.length ?? 0;
      case "conf":
        return d.confidence ?? -1;
      default:
        // Dealt-with rows sink just below their untouched peers rather than out
        // of the verdict group — the reviewer still needs to see them.
        return order[d.verdict ?? "PENDING"] + (flags[d.id] ? 0.5 : 0);
    }
  };
  return [...designs].sort((a, b) => {
    const va = value(a);
    const vb = value(b);
    const c = va < vb ? -1 : va > vb ? 1 : 0;
    return c * sortDir || (b.confidence ?? 0) - (a.confidence ?? 0);
  });
}
