"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A reviewer's own note on a design, kept in this browser only.
 *
 * "Risk accepted" and "false alarm" are judgements about the *verdict*, not new
 * facts about the design, and the backend deliberately stores only what the
 * pipeline can evidence. Keeping them local means the report stays exactly what
 * the analysis produced, while the reviewer can still mark rows they have dealt
 * with. Nothing here survives a different browser — the export labels it as a
 * local note so nobody mistakes it for a pipeline output.
 */
export type Flag = "accepted" | "reported" | null;

export interface FlagRecord {
  flag: Exclude<Flag, null>;
  /** Epoch seconds the note was made — the history log orders on this. */
  at: number;
  filename: string;
}

const KEY = "design-flags";

function read(): Record<string, FlagRecord> {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, FlagRecord | string>;
    const out: Record<string, FlagRecord> = {};
    for (const [id, value] of Object.entries(parsed)) {
      // Records written before notes carried a timestamp were a bare string.
      // They keep working; they just have no date, so `at` is 0 and the history
      // log sorts them last rather than dropping them.
      if (typeof value === "string") out[id] = { flag: value as FlagRecord["flag"], at: 0, filename: "" };
      else if (value?.flag) out[id] = value;
    }
    return out;
  } catch {
    return {};
  }
}

export function useFlags() {
  const [records, setRecords] = useState<Record<string, FlagRecord>>({});

  // Read after mount: localStorage does not exist during SSR, and seeding state
  // from it directly would make the server and client renders disagree.
  useEffect(() => setRecords(read()), []);

  const setFlag = useCallback((id: string, flag: Flag, filename = "") => {
    setRecords((prev) => {
      const next = { ...prev };
      if (flag) next[id] = { flag, at: Math.floor(Date.now() / 1000), filename };
      else delete next[id];
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* private mode — the note still applies for this session */
      }
      return next;
    });
  }, []);

  // Most callers only ask "is this row flagged?", so the plain id → flag view is
  // exposed alongside the full records the history log needs.
  const flags: Record<string, Exclude<Flag, null>> = {};
  for (const [id, r] of Object.entries(records)) flags[id] = r.flag;

  return { flags, records, setFlag };
}
