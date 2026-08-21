"use client";

import Link from "next/link";
import { contains, stamp, type DateWindow } from "@/lib/dates";
import { useTranslation } from "@/lib/i18n";
import type { FlagRecord } from "@/lib/flags";
import type { Job } from "@/lib/types";

type Kind = "scan" | "import" | "review";

interface Entry {
  id: string;
  at: number;
  kind: Kind;
  title: string;
  detail: string;
  href?: string;
}

/**
 * Activity, reconstructed from what the system actually records: one entry per
 * batch scan, one per non-upload import, and one per local review note. The
 * design also shows "register snapshot updated" and "selling context changed"
 * rows — neither is journalled anywhere, so inventing them here would mean
 * printing timestamps nobody wrote.
 */
export default function HistoryLog({
  jobs,
  reviews,
  window: win,
  dateFilter,
  onClearFilters,
}: {
  jobs: Job[];
  reviews: Record<string, FlagRecord>;
  window: DateWindow;
  dateFilter: React.ReactNode;
  onClearFilters: () => void;
}) {
  const { t, lang } = useTranslation();

  const entries: Entry[] = [];

  for (const j of jobs) {
    const processed = j.done + j.failed;
    const parts = [
      j.stats.BLOCKED ? `${j.stats.BLOCKED} ${t("verdict.BLOCKED")}` : "",
      j.stats.RISKY ? `${j.stats.RISKY} ${t("verdict.RISKY")}` : "",
      j.stats.SAFE ? `${j.stats.SAFE} ${t("verdict.SAFE")}` : "",
      j.stats.FAILED ? `${j.stats.FAILED} ${t("status.failed")}` : "",
    ].filter(Boolean);

    entries.push({
      id: `scan-${j.id}`,
      at: j.created_at,
      kind: "scan",
      title:
        processed >= j.total && j.total > 0
          ? t(j.total === 1 ? "log.scanDoneOne" : "log.scanDone").replace(
              "{n}",
              String(j.total),
            )
          : t("log.scanRunning").replace("{n}", String(processed)).replace("{m}", String(j.total)),
      detail: parts.join(" · ") || t("log.noVerdictsYet"),
      href: `/jobs/${j.id}`,
    });

    if (j.source !== "upload") {
      entries.push({
        id: `import-${j.id}`,
        at: j.created_at,
        kind: "import",
        title: t(`log.import.${j.source}`),
        detail: j.label || j.id,
        href: `/jobs/${j.id}`,
      });
    }
  }

  for (const [id, r] of Object.entries(reviews)) {
    entries.push({
      id: `review-${id}`,
      at: r.at,
      kind: "review",
      title: t(`log.review.${r.flag}`).replace("{name}", r.filename || id),
      detail: t("log.reviewLocal"),
    });
  }

  const rows = entries
    .filter((e) => contains(win, e.at))
    .sort((a, b) => b.at - a.at);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="panel-head" style={{ marginBottom: 0 }}>
        <div>
          <h2>{t("log.title")}</h2>
          <div className="sub">
            {t("log.subtitle")} · {rows.length} {t("log.entries")}
          </div>
        </div>
      </div>

      {dateFilter}

      <div>
        <div className="log-row head">
          <div>{t("log.when")}</div>
          <div>{t("log.activity")}</div>
          <div>{t("log.details")}</div>
        </div>
        {rows.map((e) => (
          <div key={e.id} className="log-row">
            <div className="when">{e.at ? stamp(e.at, lang) : "—"}</div>
            <div>
              <span className={`log-kind ${e.kind}`}>{t(`log.kind.${e.kind}`)}</span>
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 15 }}>
                {e.href ? <Link href={e.href}>{e.title}</Link> : e.title}
              </div>
              <div className="muted" style={{ marginTop: 2, textWrap: "pretty" }}>
                {e.detail}
              </div>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <div className="empty">
            <div className="muted">{t("log.noActivity")}</div>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ marginTop: 12 }}
              onClick={onClearFilters}
            >
              {t("log.showAll")}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
