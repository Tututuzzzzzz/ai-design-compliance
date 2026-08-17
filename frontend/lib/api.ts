import type { Design, Health, Job } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export interface Metadata {
  markets: string[];
  platforms: string[];
  title?: string;
  notes?: string;
}

export const api = {
  health: () => fetch("/api/health").then(json<Health>),

  uploadFiles(files: File[], metadata: Metadata, label?: string) {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("metadata", JSON.stringify(metadata));
    if (label) fd.append("label", label);
    return fetch("/api/analyze/upload", { method: "POST", body: fd }).then(
      json<{ job_id: string; queued: number }>,
    );
  },

  uploadCsv(csv: File, attachments: File[], metadata: Metadata, label?: string) {
    const fd = new FormData();
    fd.append("file", csv);
    attachments.forEach((f) => fd.append("attachments", f));
    fd.append("metadata", JSON.stringify(metadata));
    if (label) fd.append("label", label);
    return fetch("/api/analyze/csv", { method: "POST", body: fd }).then(
      json<{ job_id: string; queued: number; skipped: unknown[] }>,
    );
  },

  submitLinks(urls: string[], metadata: Metadata, label?: string) {
    return fetch("/api/analyze/links", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls, metadata, label }),
    }).then(json<{ job_id: string; queued: number }>);
  },

  submitFolder(url: string, metadata: Metadata, label?: string) {
    return fetch("/api/analyze/folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, metadata, label }),
    }).then(json<{ job_id: string; queued: number }>);
  },

  jobs: () => fetch("/api/jobs").then(json<{ jobs: Job[] }>),
  job: (id: string) => fetch(`/api/jobs/${id}`).then(json<Job & { pending: number }>),

  designs(params: { job_id?: string; verdict?: string; niche?: string; category?: string }) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    );
    return fetch(`/api/designs?${qs}`).then(json<{ designs: Design[] }>);
  },

  exportUrl(jobId: string, format: "csv" | "xlsx", filters: { verdict?: string; category?: string }) {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][],
    );
    return `/api/jobs/${jobId}/export.${format}?${qs}`;
  },
};
