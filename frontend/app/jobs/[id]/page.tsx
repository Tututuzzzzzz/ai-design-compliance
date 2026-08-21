"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import DesignDetail from "@/components/DesignDetail";
import ExportView from "@/components/ExportView";
import ReportTable, { sortDesigns, type SortKey } from "@/components/ReportTable";
import StatCards from "@/components/StatCards";
import { api } from "@/lib/api";
import { stamp } from "@/lib/dates";
import { useFlags } from "@/lib/flags";
import { useTranslation } from "@/lib/i18n";
import type { Design, Job, VerdictValue } from "@/lib/types";

const CATEGORIES = [
  "copyrighted_character",
  "brand_logo",
  "trademarked_phrase",
  "public_figure",
  "copyrighted_artwork",
  "licensed_font",
  "prohibited_content",
];

type View = "dashboard" | "export";

/**
 * One batch. Same views as the cross-batch dashboard minus the scan-window
 * filter — every design here was scanned in the same run, so a date range would
 * be a control that never changes anything.
 */
export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, lang } = useTranslation();
  const { flags, setFlag } = useFlags();

  const [job, setJob] = useState<Job | null>(null);
  const [designs, setDesigns] = useState<Design[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [view, setView] = useState<View>("dashboard");
  const [filter, setFilter] = useState<"ALL" | VerdictValue>("ALL");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("verdict");
  const [sortDir, setSortDir] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [showProcessing, setShowProcessing] = useState(true);
  const [toast, setToast] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [j, d] = await Promise.all([api.job(id), api.designs({ job_id: id, category })]);
      setJob(j);
      setDesigns(d.designs);
      setError(null);
      return j;
    } catch (e) {
      setError(String((e as Error).message ?? e));
      return null;
    }
  }, [id, category]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stop = false;
    const tick = async () => {
      const j = await refresh();
      if (stop) return;
      // Poll while work is outstanding, then settle.
      const running = !j || j.done + j.failed < j.total || j.total === 0;
      timer = setTimeout(tick, running ? 2500 : 15000);
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [refresh]);

  const processed = job ? job.done + job.failed : 0;
  const running = !!job && (job.total === 0 || processed < job.total);
  const pct = job && job.total ? Math.round((processed / job.total) * 100) : 0;

  const avgSeconds = useMemo(() => {
    const ms = designs.map((d) => d.report?.duration_ms ?? 0).filter((v) => v > 0);
    if (!ms.length) return null;
    return (ms.reduce((a, b) => a + b, 0) / ms.length / 1000).toFixed(1);
  }, [designs]);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const matched = designs
      .filter((d) => filter === "ALL" || d.verdict === filter)
      .filter((d) => !needle || `${d.filename} ${d.niche ?? ""}`.toLowerCase().includes(needle));
    return sortDesigns(matched, sortKey, sortDir, flags);
  }, [designs, filter, q, sortKey, sortDir, flags]);

  useEffect(() => {
    if (selected && !visible.some((d) => d.id === selected)) {
      setSelected(visible.length ? visible[0].id : null);
    }
  }, [visible, selected]);

  const selIndex = visible.findIndex((d) => d.id === selected);
  const selectedDesign = selIndex >= 0 ? visible[selIndex] : null;

  const counts = { SAFE: 0, RISKY: 0, BLOCKED: 0 };
  for (const d of designs) if (d.verdict && d.verdict in counts) counts[d.verdict]++;

  const scanned = job ? stamp(job.created_at, lang) : "";
  const exportFilters = { verdict: filter === "ALL" ? "" : filter, category, lang };

  const appliedLabel = [
    filter !== "ALL" ? `${t("job.verdict")}: ${t(`verdict.${filter}`)}` : "",
    category ? `${t("job.violationType")}: ${t(`categories.${category}`)}` : "",
    q.trim() ? `${t("export.search")}: "${q.trim()}"` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  function clearFilters() {
    setQ("");
    setFilter("ALL");
    setCategory("");
  }

  const subtitle = `${scanned} · ${job?.total ?? 0} ${t("proc.designs")}${
    avgSeconds ? ` · ${t("proc.about")} ${avgSeconds}${t("messages.duration")} ${t("proc.each")}` : ""
  }`;

  return (
    <main className="shell">
      {error && <div className="error">{error}</div>}

      <div className="row" style={{ marginBottom: 28, justifyContent: "space-between" }}>
        <div className="tabs">
          {(["dashboard", "export"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-current={view === v ? "page" : undefined}
              onClick={() => setView(v)}
            >
              {t(`view.${v}`)}
            </button>
          ))}
        </div>
        <Link href="/dashboard" className="btn btn-ghost">
          {t("job.allBatches")} →
        </Link>
      </div>

      {/* ---- Processing ------------------------------------------------- */}
      {view === "dashboard" && running && showProcessing && (
        <section className="section">
          <div className="panel-head">
            <h2>{t("proc.title")}</h2>
            <div className="row">
              <span className="muted">
                {job?.total} {t("proc.designs")}
                {avgSeconds
                  ? ` · ${t("proc.about")} ${avgSeconds}${t("messages.duration")} ${t("proc.each")}`
                  : ""}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowProcessing(false)}
              >
                {t("proc.viewResults")}
              </button>
            </div>
          </div>
          <p className="muted">{t("proc.steps")}</p>

          <div className="panel" style={{ marginBottom: 14 }}>
            <div
              className="row"
              style={{ justifyContent: "space-between", fontWeight: 600, marginBottom: 8 }}
            >
              <span>
                {processed} {t("proc.of")} {job?.total} {t("proc.complete")}
              </span>
              <span className="muted">{pct}%</span>
            </div>
            <div className="progress">
              <span style={{ width: `${pct}%` }} />
            </div>
          </div>

          <div className="report-scroll">
            <div style={{ minWidth: 680 }}>
              {designs.map((d) => {
                const done = d.status === "done" || d.status === "failed";
                const verdict = d.verdict ?? "PENDING";
                return (
                  <div key={d.id} className="proc-row">
                    <div className="row" style={{ gap: 12, flexWrap: "nowrap", minWidth: 0 }}>
                      <span
                        className={`tile ${done ? verdict : "PENDING"}`}
                        style={{ width: 30, height: 30, fontSize: 14 }}
                      >
                        {d.filename.charAt(0).toUpperCase()}
                      </span>
                      <span className="name">{d.filename}</span>
                    </div>
                    <div
                      className="row"
                      style={{ gap: 8, fontSize: 13, color: "var(--color-neutral-700)" }}
                    >
                      <span
                        className="dot"
                        data-live={d.status === "running"}
                        style={{
                          background:
                            d.status === "running" ? "var(--color-accent-2-600)" : undefined,
                        }}
                      />
                      {t(`proc.note.${d.status}`)}
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <span className={`badge ${done ? verdict : "PENDING"}`}>
                        {d.verdict ? t(`verdict.${d.verdict}`) : t(`status.${d.status}`)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* ---- Dashboard -------------------------------------------------- */}
      {view === "dashboard" && !(running && showProcessing) && (
        <>
          <StatCards designs={designs} />

          <section>
            <div className="panel-head">
              <div>
                <h2>{job?.label || t("report.title")}</h2>
                <div className="sub">{subtitle}</div>
              </div>
              <div className="row">
                <input
                  type="search"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={t("report.searchPlaceholder")}
                  aria-label={t("report.searchPlaceholder")}
                  style={{ width: 190 }}
                />
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  aria-label={t("job.violationType")}
                  style={{ width: 180 }}
                >
                  <option value="">{t("report.allCategories")}</option>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {t(`categories.${c}`)}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn btn-ghost" onClick={() => setView("export")}>
                  {t("report.exportReport")}
                </button>
                <a className="btn btn-primary" href={api.exportUrl(id, "xlsx", exportFilters)}>
                  {t("job.exportExcel")}
                </a>
              </div>
            </div>

            <div className="tabs" style={{ marginBottom: 12 }}>
              {(["ALL", "BLOCKED", "RISKY", "SAFE"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={filter === k}
                  onClick={() => setFilter(k)}
                >
                  {k === "ALL" ? t("job.all") : `${t(`verdict.${k}`)} ${counts[k]}`}
                </button>
              ))}
            </div>

            <ReportTable
              designs={visible}
              selected={selected}
              sortKey={sortKey}
              sortDir={sortDir}
              flags={flags}
              onSort={(k) => {
                if (k === sortKey) setSortDir((d) => -d);
                else {
                  setSortKey(k);
                  setSortDir(1);
                }
              }}
              onSelect={setSelected}
              onClearFilters={clearFilters}
            />
            <div className="note">{t("report.confidenceNote")}</div>
          </section>
        </>
      )}

      {view === "export" && (
        <ExportView
          designs={visible}
          subtitle={`${scanned} · ${t("export.filtersApply")}`}
          appliedLabel={appliedLabel}
          urlFor={(format) => api.exportUrl(id, format, exportFilters)}
          flags={flags}
          onClearFilters={clearFilters}
        />
      )}

      {selectedDesign && (
        <DesignDetail
          design={selectedDesign}
          position={selIndex + 1}
          total={visible.length}
          flag={flags[selectedDesign.id] ?? null}
          onFlag={(f) => {
            setFlag(selectedDesign.id, f, selectedDesign.filename);
            setToast(f ? t(`flag.${f}`) : t("flag.cleared"));
            setTimeout(() => setToast(""), 2500);
          }}
          onPrev={() => selIndex > 0 && setSelected(visible[selIndex - 1].id)}
          onNext={() => selIndex < visible.length - 1 && setSelected(visible[selIndex + 1].id)}
          onClose={() => {
            const returning = selectedDesign.id;
            setSelected(null);
            setTimeout(() => document.getElementById(`row-${returning}`)?.focus(), 40);
          }}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </main>
  );
}
