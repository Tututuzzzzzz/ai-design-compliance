import type { Accuracy, Design, Health, Job } from "./types";
import type { Language } from "./i18n";

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
  /** Language the backend writes the report in — the vision model's prose and
   *  the pipeline's own sentences. Set from the UI language at submit time. */
  language?: Language;
}

/** Fallbacks used only until /api/health answers — the server owns the real
 *  numbers, these just keep the guard from being absent on the first paint. */
export const FALLBACK_LIMITS = { max_upload_mb: 60, max_request_mb: 95 };

/** An upload that no longer makes progress must fail, not hang. A proxy that
 *  rejects an oversized body answers while the browser is still sending, and
 *  Chrome leaves that request pending forever — which is indistinguishable
 *  from a slow upload unless something eventually aborts it. Generous, so a
 *  genuinely large batch on a slow link still finishes. */
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

async function postForm<T>(path: string, fd: FormData): Promise<T> {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), UPLOAD_TIMEOUT_MS);
  try {
    return await fetch(path, { method: "POST", body: fd, signal: ac.signal }).then(json<T>);
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error(
        `Upload stopped responding after ${UPLOAD_TIMEOUT_MS / 60000} minutes. ` +
          "Try fewer files at once.",
      );
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: () => fetch("/api/health").then(json<Health>),

  accuracy: () => fetch("/api/accuracy").then(json<Accuracy>),

  uploadFiles(files: File[], metadata: Metadata, label?: string) {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("metadata", JSON.stringify(metadata));
    if (label) fd.append("label", label);
    return postForm<{ job_id: string; queued: number }>("/api/analyze/upload", fd);
  },

  uploadCsv(csv: File, attachments: File[], metadata: Metadata, label?: string) {
    const fd = new FormData();
    fd.append("file", csv);
    attachments.forEach((f) => fd.append("attachments", f));
    fd.append("metadata", JSON.stringify(metadata));
    if (label) fd.append("label", label);
    return postForm<{ job_id: string; queued: number; skipped: unknown[] }>(
      "/api/analyze/csv",
      fd,
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

  designs(params: {
    job_id?: string;
    verdict?: string;
    niche?: string;
    category?: string;
    /** Epoch seconds bounding the scan time. */
    since?: string;
    until?: string;
    limit?: string;
  }) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    );
    return fetch(`/api/designs?${qs}`).then(json<{ designs: Design[] }>);
  },

  exportUrl(
    jobId: string,
    format: "csv" | "xlsx" | "sheet.xlsx",
    // The window is passed through so the file matches the grid the button was
    // pressed from — an export that silently ignores the filters is worse than
    // no export.
    filters: {
      verdict?: string;
      category?: string;
      lang?: Language;
      since?: string;
      until?: string;
    },
  ) {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][],
    );
    return `/api/jobs/${jobId}/export.${format}?${qs}`;
  },

  /** The original artwork of every SAFE design in scope, zipped.
   *  Verdict is fixed to SAFE — that is what the button promises — but the
   *  category and window filters are passed so the file matches the count on
   *  the button. */
  safeZipUrl(filters: { job_id?: string; category?: string; since?: string; until?: string }) {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][],
    );
    return `/api/export.safe.zip?${qs}`;
  },

  /** Cross-batch export — same filters, no job scope. */
  exportAllUrl(
    format: "csv" | "xlsx" | "sheet.xlsx",
    filters: {
      verdict?: string;
      category?: string;
      lang?: Language;
      since?: string;
      until?: string;
    },
  ) {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][],
    );
    return `/api/export.${format}?${qs}`;
  },
};
