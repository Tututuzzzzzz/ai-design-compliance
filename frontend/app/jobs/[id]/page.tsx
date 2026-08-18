"use client";

import { use, useCallback, useEffect, useState } from "react";
import DesignDetail from "@/components/DesignDetail";
import { api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";
import type { Design, Job } from "@/lib/types";

const CATEGORIES = [
  "copyrighted_character",
  "brand_logo",
  "trademarked_phrase",
  "public_figure",
  "copyrighted_artwork",
  "licensed_font",
  "prohibited_content",
];

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, lang } = useTranslation();

  const [job, setJob] = useState<Job | null>(null);
  const [designs, setDesigns] = useState<Design[]>([]);
  const [verdict, setVerdict] = useState("");
  const [category, setCategory] = useState("");
  const [niche, setNiche] = useState("");
  const [selected, setSelected] = useState<Design | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [j, d] = await Promise.all([
        api.job(id),
        api.designs({ job_id: id, verdict, category, niche }),
      ]);
      setJob(j);
      setDesigns(d.designs);
      setError(null);
      return j;
    } catch (e) {
      setError(String((e as Error).message ?? e));
      return null;
    }
  }, [id, verdict, category, niche]);

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

  const stats = job?.stats ?? { SAFE: 0, RISKY: 0, BLOCKED: 0, FAILED: 0 };
  const processed = job ? job.done + job.failed : 0;
  const pct = job && job.total ? Math.round((processed / job.total) * 100) : 0;
  const sourceLabel = (value: string) => t(`source.${value}`) || value;
  const statusLabel = (value: string) => t(`status.${value}`) || value;
  const verdictLabel = (value: string) => t(`verdict.${value}`) || value;

  return (
    <main className="shell">
      {error && <div className="error">{error}</div>}

      <div className="card">
        <div className="row">
          <div>
            <h2 style={{ marginBottom: 2 }}>{job?.label ?? t("job.batch")}</h2>
            <p className="muted" style={{ margin: 0 }}>
              {t("job.inputMethod")}: <strong>{job?.source ? sourceLabel(job.source) : "-"}</strong> · {t("job.jobId")}{" "}
              <code>{id}</code>
            </p>
          </div>
          <div className="spacer" />
          <a className="ghost" href={api.exportUrl(id, "csv", { verdict, category, lang })}>
            {t("job.exportCsv")}
          </a>
          <a className="ghost" href={api.exportUrl(id, "xlsx", { verdict, category, lang })}>
            {t("job.exportExcel")}
          </a>
        </div>

        {job && job.total > 0 && processed < job.total && (
          <div style={{ marginTop: 14 }}>
            <div className="progress">
              <span style={{ width: `${pct}%` }} />
            </div>
            <p className="muted" style={{ marginBottom: 0 }}>
              {processed} / {job.total} {t("job.analysed")}
            </p>
          </div>
        )}
      </div>

      <div className="card">
        <div className="stats">
          <div className="stat">
            <div className="n">{job?.total ?? 0}</div>
            <div className="k">{t("job.totalDesigns")}</div>
          </div>
          <div className="stat">
            <div className="n" style={{ color: "var(--safe)" }}>
              {stats.SAFE}
            </div>
            <div className="k">{t("labels.safe")}</div>
          </div>
          <div className="stat">
            <div className="n" style={{ color: "var(--risky)" }}>
              {stats.RISKY}
            </div>
            <div className="k">{t("labels.risky")}</div>
          </div>
          <div className="stat">
            <div className="n" style={{ color: "var(--blocked)" }}>
              {stats.BLOCKED}
            </div>
            <div className="k">{t("labels.blocked")}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row">
          <div style={{ minWidth: 160 }}>
            <label>{t("job.verdict")}</label>
            <select value={verdict} onChange={(e) => setVerdict(e.target.value)}>
              <option value="">{t("job.all")}</option>
              <option value="SAFE">{verdictLabel("SAFE")}</option>
              <option value="RISKY">{verdictLabel("RISKY")}</option>
              <option value="BLOCKED">{verdictLabel("BLOCKED")}</option>
            </select>
          </div>
          <div style={{ minWidth: 220 }}>
            <label>{t("job.violationType")}</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">{t("job.all")}</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`categories.${c}`)}
                </option>
              ))}
            </select>
          </div>
          <div style={{ minWidth: 200 }}>
            <label>{t("job.nicheContains")}</label>
            <input
              type="text"
              value={niche}
              placeholder={t("job.nichePlaceholder")}
              onChange={(e) => setNiche(e.target.value)}
            />
          </div>
          <div className="spacer" />
          <span className="muted">{designs.length} {t("job.shown")}</span>
        </div>
      </div>

      <div className="grid cards" style={{ marginTop: 16 }}>
        {designs.map((d) => (
          <div key={d.id} className="design" onClick={() => setSelected(d)}>
            <div className="thumb">
              {d.report?.preview_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={d.report.annotated_url ?? d.report.preview_url} alt={d.filename} />
              ) : (
                <span className="muted">{statusLabel(d.status)}</span>
              )}
            </div>
            <div className="body">
              <div className="name" title={d.filename}>
                {d.filename}
              </div>
              <div className="row" style={{ gap: 6, marginTop: 6 }}>
                <span className={`badge ${d.verdict ?? "PENDING"}`}>
                  {d.verdict ? verdictLabel(d.verdict) : statusLabel(d.status)}
                </span>
                {d.confidence != null && <span className="muted">{d.confidence}%</span>}
              </div>
              <div className="meta">
                {d.niche ?? "—"}
                {d.report ? ` · ${d.report.findings.length} ${t("job.findings")}` : ""}
              </div>
            </div>
          </div>
        ))}
      </div>

      {designs.length === 0 && job && processed > 0 && (
        <p className="muted">{t("job.noMatch")}</p>
      )}

      {selected && (
        <DesignDetail
          design={designs.find((d) => d.id === selected.id) ?? selected}
          onClose={() => setSelected(null)}
        />
      )}
    </main>
  );
}
