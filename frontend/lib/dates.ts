/** Scan-window filter shared by the dashboard, the export view and the log. */

export type DatePreset = "all" | "7d" | "30d" | "custom";

export interface DateWindow {
  preset: DatePreset;
  from: string; // yyyy-mm-dd, only meaningful when preset === "custom"
  to: string;
}

export const ALL_TIME: DateWindow = { preset: "all", from: "", to: "" };

/**
 * Epoch-second bounds for a window, or null where that end is open.
 *
 * The relative presets are anchored to *now*, not to midnight: "last 7 days"
 * asked at 09:00 should include the scan that finished at 23:00 seven days ago,
 * which a midnight anchor would drop.
 */
export function bounds(w: DateWindow): { since?: number; until?: number } {
  const now = Date.now();
  if (w.preset === "7d") return { since: (now - 7 * 86400_000) / 1000 };
  if (w.preset === "30d") return { since: (now - 30 * 86400_000) / 1000 };
  if (w.preset === "custom") {
    const out: { since?: number; until?: number } = {};
    // Local midnight either side, so a single-day range covers that whole day.
    if (w.from) out.since = new Date(`${w.from}T00:00:00`).getTime() / 1000;
    if (w.to) out.until = new Date(`${w.to}T23:59:59`).getTime() / 1000;
    return out;
  }
  return {};
}

export function isActive(w: DateWindow): boolean {
  const b = bounds(w);
  return b.since != null || b.until != null;
}

export function contains(w: DateWindow, epochSeconds: number): boolean {
  const { since, until } = bounds(w);
  return (since == null || epochSeconds >= since) && (until == null || epochSeconds <= until);
}

/** Query params for the API, dropping the open ends. */
export function params(w: DateWindow): Record<string, string> {
  const { since, until } = bounds(w);
  const out: Record<string, string> = {};
  if (since != null) out.since = String(Math.floor(since));
  if (until != null) out.until = String(Math.ceil(until));
  return out;
}

export function stamp(epochSeconds: number, lang: string): string {
  return new Date(epochSeconds * 1000).toLocaleString(lang, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
