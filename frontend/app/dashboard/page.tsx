"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import DateRangeFilter from "@/components/DateRangeFilter";
import DesignDetail from "@/components/DesignDetail";
import ExportView from "@/components/ExportView";
import HistoryLog from "@/components/HistoryLog";
import ReportTable, { sortDesigns, type SortKey } from "@/components/ReportTable";
import StatCards from "@/components/StatCards";
import { api } from "@/lib/api";
import { ALL_TIME, isActive, params, stamp, type DateWindow } from "@/lib/dates";
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

type View = "dashboard" | "export" | "history";

/**
 * Rows fetched per window. Unscoped, the report spans every batch ever run, so
 * some ceiling is unavoidable; it is stated on screen when reached rather than
 * silently truncating, because a capped report that looks complete is the kind
 * of thing someone exports and acts on.
 */
const ROW_LIMIT = 600;

export default function DashboardPage() {
  // useSearchParams needs a Suspense boundary during prerender.
  return (
    <Suspense fallback={<main className="shell" />}>
      <Dashboard />
    </Suspense>
  );
}

function Dashboard() {
  const { t, lang } = useTranslation();
  const router = useRouter();
  const search = useSearchParams();
  const { flags, records, setFlag } = useFlags();

  const initialView = (search.get("view") as View) || "dashboard";
  const [view, setView] = useState<View>(initialView);
  const [win, setWin] = useState<DateWindow>(ALL_TIME);
  const [filter, setFilter] = useState<"ALL" | VerdictValue>("ALL");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("verdict");
  const [sortDir, setSortDir] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  const [jobs, setJobs] = useState<Job[]>([]);
  const [designs, setDesigns] = useState<Design[]>([]);
  const [error, setError] = useState<string | null>(null);

  // The window is applied server-side so a narrow range does not pay for the
  // whole history; everything else narrows client-side, keeping the filter-tab
  // counts and the sort consistent with what is on screen.
  const load = useCallback(async () => {
    try {
      const [j, d] = await Promise.all([
        api.jobs(),
        api.designs({ category, limit: String(ROW_LIMIT), ...params(win) }),
      ]);
      setJobs(j.jobs);
      setDesigns(d.designs);
      setError(null);
      return j.jobs;
    } catch (e) {
      setError(String((e as Error).message ?? e));
      return null;
    }
  }, [category, win]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stop = false;
    const tick = async () => {
      const list = await load();
      if (stop) return;
      const busy = !list || list.some((j) => j.done + j.failed < j.total);
      timer = setTimeout(tick, busy ? 4000 : 20000);
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [load]);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const matched = designs
      .filter((d) => filter === "ALL" || d.verdict === filter)
      .filter(
        (d) => !needle || `${d.filename} ${d.niche ?? ""}`.toLowerCase().includes(needle),
      );
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

  // The API hands back at most ROW_LIMIT rows, newest first.
  const capped = designs.length >= ROW_LIMIT;

  const latestScan = designs.length
    ? stamp(Math.max(...designs.map((d) => d.created_at)), lang)
    : null;

  function clearFilters() {
    setQ("");
    setFilter("ALL");
    setCategory("");
    setWin(ALL_TIME);
  }

  function switchView(next: View) {
    setView(next);
    setSelected(null);
    // The view lives in the URL so the tabs are linkable and survive a reload.
    router.replace(next === "dashboard" ? "/dashboard" : `/dashboard?view=${next}`);
  }

  const appliedLabel = [
    filter !== "ALL" ? `${t("job.verdict")}: ${t(`verdict.${filter}`)}` : "",
    category ? `${t("job.violationType")}: ${t(`categories.${category}`)}` : "",
    q.trim() ? `${t("export.search")}: "${q.trim()}"` : "",
    isActive(win) ? `${t("export.scanDate")}: ${t(`date.${win.preset}`)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  const exportFilters = {
    verdict: filter === "ALL" ? "" : filter,
    category,
    lang,
    ...params(win),
  };

  const dateFilter = (
    <DateRangeFilter label={t("export.scanDate")} value={win} onChange={setWin} />
  );
  // The log covers imports and review notes too, so "Scanned" would be wrong there.
  const logDateFilter = <DateRangeFilter label={t("date.label")} value={win} onChange={setWin} />;

  return (
    <main className="shell">
      {error && <div className="error">{error}</div>}

      <div className="tabs" style={{ marginBottom: 28 }}>
        {(["dashboard", "export", "history"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-current={view === v ? "page" : undefined}
            onClick={() => switchView(v)}
          >
            {t(`view.${v}`)}
          </button>
        ))}
      </div>

      {view === "dashboard" && (
        <>
          <StatCards designs={designs} />

          <section>
            <div className="panel-head">
              <div>
                <h2>{t("report.title")}</h2>
                <div className="sub">
                  {latestScan ? `${t("report.latestScan")} ${latestScan} · ` : ""}
                  {t("report.showing")
                    .replace("{n}", String(visible.length))
                    .replace("{m}", String(designs.length))}
                  {capped && ` · ${t("report.capped").replace("{n}", String(ROW_LIMIT))}`}
                </div>
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
                <button type="button" className="btn btn-ghost" onClick={() => switchView("export")}>
                  {t("report.exportReport")}
                </button>
                <a className="btn btn-primary" href={api.exportAllUrl("xlsx", exportFilters)}>
                  {t("job.exportExcel")}
                </a>
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>{dateFilter}</div>

            <div className="tabs" style={{ marginBottom: 12 }}>
              {(["ALL", "BLOCKED", "RISKY", "SAFE"] as const).map((k) => (
                <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>
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
          subtitle={
            latestScan
              ? `${t("report.latestScan")} ${latestScan} · ${t("export.filtersApply")}`
              : t("export.filtersApply")
          }
          appliedLabel={appliedLabel}
          urlFor={(format) => api.exportAllUrl(format, exportFilters)}
          flags={flags}
          dateFilter={dateFilter}
          onClearFilters={clearFilters}
        />
      )}

      {view === "history" && (
        <HistoryLog
          jobs={jobs}
          reviews={records}
          window={win}
          dateFilter={logDateFilter}
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
