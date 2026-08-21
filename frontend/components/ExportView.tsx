"use client";

import { useState } from "react";
import { stamp } from "@/lib/dates";
import { useTranslation } from "@/lib/i18n";
import type { Flag } from "@/lib/flags";
import type { Design } from "@/lib/types";

type Sheet = "summary" | "designs" | "findings";

export default function ExportView({
  designs,
  subtitle,
  appliedLabel,
  urlFor,
  flags,
  dateFilter,
  onClearFilters,
}: {
  designs: Design[];
  subtitle: string;
  /** Human summary of every active filter, or "" when nothing is narrowing. */
  appliedLabel: string;
  urlFor: (format: "csv" | "xlsx" | "sheet.xlsx") => string;
  flags: Record<string, Exclude<Flag, null>>;
  dateFilter?: React.ReactNode;
  onClearFilters: () => void;
}) {
  const { t, lang } = useTranslation();
  const [sheet, setSheet] = useState<Sheet>("summary");

  const counts = { SAFE: 0, RISKY: 0, BLOCKED: 0 };
  for (const d of designs) if (d.verdict && d.verdict in counts) counts[d.verdict]++;

  return (
    <section>
      <div className="panel-head">
        <div>
          <h2>{t("export.title")}</h2>
          <div className="sub">{subtitle}</div>
        </div>
        <div className="row">
          <a className="btn btn-secondary" href={urlFor("csv")}>
            {t("job.exportCsv")}
          </a>
          <a
            className="btn btn-secondary"
            href={urlFor("sheet.xlsx")}
            title={t("job.exportSheetHint")}
          >
            {t("job.exportSheet")}
          </a>
          <a className="btn btn-primary" href={urlFor("xlsx")}>
            {t("job.exportExcel")}
          </a>
        </div>
      </div>

      {appliedLabel && (
        <div className="row" style={{ marginBottom: 14 }}>
          <span className="muted">{t("export.applied")}</span>
          <span className="flag">{appliedLabel}</span>
          <button type="button" className="link-btn" onClick={onClearFilters}>
            {t("export.clearAll")}
          </button>
        </div>
      )}

      {dateFilter && <div style={{ marginBottom: 14 }}>{dateFilter}</div>}

      <div className="pills" style={{ marginBottom: 14 }}>
        {(["summary", "designs", "findings"] as const).map((k) => (
          <button key={k} type="button" aria-pressed={sheet === k} onClick={() => setSheet(k)}>
            {t(`export.sheet.${k}`)}
          </button>
        ))}
      </div>

      <div className="report-scroll">
        {sheet === "summary" && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("export.metric")}</th>
                <th>{t("export.value")}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{t("export.inReport")}</td>
                <td>{designs.length}</td>
              </tr>
              {(["SAFE", "RISKY", "BLOCKED"] as const).map((k) => (
                <tr key={k}>
                  <td>{t(`verdict.${k}`)}</td>
                  <td>{counts[k]}</td>
                </tr>
              ))}
              <tr>
                <td>{t("export.window")}</td>
                <td>
                  {designs.length
                    ? `${stamp(designs[0].created_at, lang)} → ${stamp(
                        designs[designs.length - 1].created_at,
                        lang,
                      )}`
                    : "—"}
                </td>
              </tr>
            </tbody>
          </table>
        )}

        {sheet === "designs" && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("export.filename")}</th>
                <th>{t("detail.niche")}</th>
                <th>{t("job.verdict")}</th>
                <th>{t("messages.confidence")}</th>
                <th>{t("detail.findings")}</th>
                <th>{t("export.scanDate")}</th>
              </tr>
            </thead>
            <tbody>
              {designs.map((d) => (
                <tr key={d.id}>
                  <td style={{ fontWeight: 600 }}>{d.filename}</td>
                  <td>{d.niche ?? "—"}</td>
                  <td style={{ fontWeight: 600 }}>
                    {d.verdict ? t(`verdict.${d.verdict}`) : t(`status.${d.status}`)}
                  </td>
                  <td>{d.confidence != null ? `${d.confidence}%` : "—"}</td>
                  <td>
                    {d.report?.findings.length
                      ? d.report.findings.map((f) => f.title).join(" · ")
                      : "—"}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>{stamp(d.created_at, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {sheet === "findings" && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("report.design")}</th>
                <th>{t("export.category")}</th>
                <th>{t("export.severity")}</th>
                <th>{t("export.finding")}</th>
                <th>{t("detail.howWeFoundIt")}</th>
              </tr>
            </thead>
            <tbody>
              {designs.flatMap((d) =>
                (d.report?.findings ?? []).map((f, i) => (
                  <tr key={`${d.id}-${i}`}>
                    <td style={{ fontWeight: 600 }}>{d.filename}</td>
                    <td>{t(`categories.${f.category}`)}</td>
                    <td style={{ fontWeight: 600 }}>{t(`severity.${f.severity}`)}</td>
                    <td>{f.title}</td>
                    <td>{(f.evidence ?? []).map((e) => t(`evidence.${e.source}`)).join(" · ")}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </div>

      {Object.keys(flags).length > 0 && <div className="note">{t("export.localFlagNote")}</div>}
    </section>
  );
}
