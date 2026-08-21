"use client";

import { useTranslation } from "@/lib/i18n";
import type { Design } from "@/lib/types";

/**
 * Counts are derived from the rows on screen, not from the job's stored stats —
 * the date filter and the category filter both narrow the grid, and a headline
 * number that disagrees with the list under it is worse than no headline.
 */
export default function StatCards({ designs }: { designs: Design[] }) {
  const { t } = useTranslation();

  const counts = { BLOCKED: 0, RISKY: 0, SAFE: 0, FAILED: 0 };
  for (const d of designs) {
    if (d.verdict && d.verdict in counts) counts[d.verdict as keyof typeof counts]++;
    else if (d.status === "failed") counts.FAILED++;
  }

  return (
    <section style={{ marginBottom: 12 }}>
      <div className="stats">
        {(["BLOCKED", "RISKY", "SAFE"] as const).map((k) => (
          <div key={k} className={`stat ${k}`}>
            <div className="n">{counts[k]}</div>
            <div className="k">{t(`verdict.${k}`)}</div>
            <div className="h">{t(`stat.${k}`)}</div>
          </div>
        ))}
        {counts.FAILED > 0 && (
          <div className="stat NEUTRAL">
            <div className="n">{counts.FAILED}</div>
            <div className="k">{t("status.failed")}</div>
            <div className="h">{t("stat.FAILED")}</div>
          </div>
        )}
      </div>
      <div className="note">{t("stat.caveat")}</div>
    </section>
  );
}
