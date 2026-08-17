"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";
import type { Job } from "@/lib/types";

export default function JobsPage() {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      api
        .jobs()
        .then((r) => setJobs(r.jobs))
        .catch((e) => setError(String(e.message ?? e)));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <main className="shell">
      {error && <div className="error">{error}</div>}
      <div className="card">
        <h2>{t("labels.batches")}</h2>
        {jobs.length === 0 && <p className="muted">{t("labels.noBatches")}</p>}
        {jobs.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>{t("labels.batch")}</th>
                <th>{t("labels.input")}</th>
                <th>{t("labels.progress")}</th>
                <th>{t("labels.safe")}</th>
                <th>{t("labels.risky")}</th>
                <th>{t("labels.blocked")}</th>
                <th>{t("labels.status")}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link href={`/jobs/${j.id}`}>{j.label || j.id}</Link>
                  </td>
                  <td>{j.source}</td>
                  <td>
                    {j.done + j.failed}/{j.total}
                  </td>
                  <td style={{ color: "var(--safe)" }}>{j.stats.SAFE}</td>
                  <td style={{ color: "var(--risky)" }}>{j.stats.RISKY}</td>
                  <td style={{ color: "var(--blocked)" }}>{j.stats.BLOCKED}</td>
                  <td className="muted">{j.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
