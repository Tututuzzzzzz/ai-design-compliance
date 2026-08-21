export type VerdictValue = "SAFE" | "RISKY" | "BLOCKED";
export type Severity = "low" | "medium" | "high" | "critical";

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Evidence {
  source: string;
  detail: string;
  url?: string | null;
  reference_id?: string | null;
}

export interface Finding {
  category: string;
  title: string;
  description: string;
  severity: Severity;
  confidence: number;
  rights_holder?: string | null;
  matched_text?: string | null;
  bbox?: BBox | null;
  location_hint?: string | null;
  evidence: Evidence[];
  remediation: string;
}

export interface Niche {
  primary: string;
  sub_niche?: string | null;
  audience?: string | null;
  style: string[];
  motifs: string[];
  confidence: number;
}

export interface TrademarkHit {
  query: string;
  mark_text: string;
  similarity: number;
  source: string;
  serial_number?: string | null;
  registration_number?: string | null;
  owner?: string | null;
  status?: string | null;
  classes?: string | null;
  url?: string | null;
}

export interface ComplianceReport {
  design_id: string;
  filename: string;
  source: string;
  source_ref?: string | null;
  metadata: { markets: string[]; platforms: string[]; title?: string | null };
  verdict: VerdictValue;
  confidence: number;
  reasoning: string;
  summary: string;
  niche: Niche;
  findings: Finding[];
  ocr_text: string;
  trademark_hits: TrademarkHit[];
  policy_notes: string[];
  image_width: number;
  image_height: number;
  preview_url?: string | null;
  annotated_url?: string | null;
  /** Full-resolution file the user supplied. Linked, never embedded — originals
   *  run to tens of MB and the grid would choke on them. */
  original_url?: string | null;
  duration_ms: number;
  provider: string;
  error?: string | null;
}

export interface Design {
  id: string;
  job_id: string;
  /** Epoch seconds the row was created — the scan time the date filter works on. */
  created_at: number;
  status: string;
  filename: string;
  source: string;
  source_ref?: string | null;
  verdict?: VerdictValue | null;
  confidence?: number | null;
  niche?: string | null;
  error?: string | null;
  report?: ComplianceReport | null;
}

export interface JobStats {
  SAFE: number;
  RISKY: number;
  BLOCKED: number;
  FAILED: number;
}

export interface Job {
  id: string;
  status: string;
  source: string;
  label: string;
  total: number;
  done: number;
  failed: number;
  created_at: number;
  stats: JobStats;
}

export interface Health {
  status: string;
  vision: { provider: string; model: string; configured: boolean };
  ocr: { engine: string };
  trademark: { available: boolean; marks: number; live_lookup: boolean };
  queue: { pending: number; workers: number };
  formats: string[];
  platforms: string[];
  markets: string[];
}
