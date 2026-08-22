"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { stamp } from "@/lib/dates";
import { useTranslation } from "@/lib/i18n";
import type { Accuracy } from "@/lib/types";

/**
 * How the checker scores itself. The numbers come from the last
 * `python -m data.evaluate --json` run and are absent until someone has scored
 * the build — an unmeasured tool says so rather than quoting a figure.
 *
 * The two error classes are split because they are not equally bad: a MISS gets
 * a store suspended, a FALSE ALARM only wastes a designer's time.
 */
export default function AccuracyPanel({ lead }: { lead?: string }) {
  const { t, lang } = useTranslation();
  const [data, setData] = useState<Accuracy | null>(null);

  useEffect(() => {
    let stop = false;
    api
      .accuracy()
      .then((a) => !stop && setData(a))
      .catch(() => !stop && setData({ available: false }));
    return () => {
      stop = true;
    };
  }, []);

  const rows: { label: string; value: string; tone?: "miss" }[] = [];
  if (data?.available) {
    const pct = (n?: number | null) => (n == null ? "—" : `${n}%`);
    rows.push({
      label: t("accuracy.correctVerdicts"),
      value: `${data.correct ?? 0} / ${data.scored ?? 0} (${pct(data.accuracy_pct)})`,
    });
    if (data.category_total)
      rows.push({
        label: t("accuracy.correctCategory"),
        value: `${data.category_hits} / ${data.category_total} (${pct(data.category_pct)})`,
      });
    if (data.niche_total)
      rows.push({
        label: t("accuracy.correctNiche"),
        value: `${data.niche_hits} / ${data.niche_total} (${pct(data.niche_pct)})`,
      });
    rows.push({ label: t("accuracy.misses"), value: String(data.misses ?? 0), tone: "miss" });
    rows.push({ label: t("accuracy.falseAlarms"), value: String(data.false_alarms ?? 0) });
    if (data.errors) rows.push({ label: t("accuracy.errors"), value: String(data.errors) });
    if (data.median_latency_s != null)
      rows.push({
        label: t("accuracy.speed"),
        value: `${data.median_latency_s}${t("messages.duration")}`,
      });
  }

  return (
    <div className="accuracy">
      <div>
        <h3>{t("accuracy.title")}</h3>
        <p className="muted">{lead ?? t("accuracy.lede")}</p>
      </div>

      <div className="grid two">
        <div className="err-card miss">
          <div className="k">{t("accuracy.missLabel")}</div>
          <div className="d">{t("accuracy.missDetail")}</div>
        </div>
        <div className="err-card alarm">
          <div className="k">{t("accuracy.falseAlarmLabel")}</div>
          <div className="d">{t("accuracy.falseAlarmDetail")}</div>
        </div>
      </div>

      {data == null && <div className="muted">{t("accuracy.loading")}</div>}

      {data && !data.available && (
        <div className="panel">
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{t("accuracy.notRunTitle")}</div>
          <div className="muted">{t("accuracy.notRunDetail")}</div>
          <pre className="prose" style={{ marginTop: 10, marginBottom: 0 }}>
            python -m data.evaluate --json
          </pre>
        </div>
      )}

      {data?.available && (
        <div className="report-scroll">
          <div className="sub-label">
            {t("accuracy.measuredOn").replace("{n}", String(data.designs ?? 0))}
            {data.model ? ` · ${data.model}` : ""}
            {data.generated_at ? ` · ${stamp(data.generated_at, lang)}` : ""}
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>{t("export.metric")}</th>
                <th>{t("accuracy.result")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className={r.tone === "miss" ? "miss-value" : undefined}>{r.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="note">{t("accuracy.footnote")}</div>
        </div>
      )}
    </div>
  );
}
