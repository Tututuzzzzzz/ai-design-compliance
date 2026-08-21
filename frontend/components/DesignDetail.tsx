"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n";
import type { Design, Finding, VerdictValue } from "@/lib/types";
import type { Flag } from "@/lib/flags";

function Evidence({ f, t }: { f: Finding; t: (key: string) => string }) {
  // The vision model is named on every finding by construction, so listing it
  // adds nothing; what matters is which *register* confirmed the claim.
  const rows = (f.evidence ?? []).filter((e) => e.source !== "vision_model");
  if (!rows.length) return null;
  return (
    <div className="how">
      {t("detail.howWeFoundIt")} ·{" "}
      {rows.map((e, i) => (
        <span key={i}>
          {i > 0 && " · "}
          {t(`evidence.${e.source}`)}
          {e.reference_id && ` #${e.reference_id}`}
          {e.url && (
            <>
              {" — "}
              <a href={e.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>
                {t("detail.verify")}
              </a>
            </>
          )}
        </span>
      ))}
    </div>
  );
}

export default function DesignDetail({
  design,
  position,
  total,
  flag,
  onFlag,
  onPrev,
  onNext,
  onClose,
}: {
  design: Design;
  position: number;
  total: number;
  flag: Flag;
  onFlag: (flag: Flag) => void;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [boxes, setBoxes] = useState(true);
  const panel = useRef<HTMLDivElement>(null);
  const r = design.report;

  useEffect(() => {
    panel.current?.focus();
  }, []);

  // Esc closes; ↑/↓ and J/K walk the batch without leaving the panel. Reviewing
  // a batch is a keyboard job — one hand on the arrow keys, eyes on the artwork.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing =
        el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (typing) return;
      if (e.key === "ArrowDown" || e.key === "j" || e.key === "J") {
        e.preventDefault();
        onNext();
      } else if (e.key === "ArrowUp" || e.key === "k" || e.key === "K") {
        e.preventDefault();
        onPrev();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onPrev]);

  const verdict: VerdictValue | "PENDING" = r?.verdict ?? "PENDING";
  const marked = r ? r.findings.filter((f) => f.bbox) : [];

  return (
    <div className="overlay" onClick={onClose}>
      <div
        ref={panel}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={design.filename}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{design.filename}</h2>
          {r && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onFlag(flag === "accepted" ? null : "accepted")}
              >
                {flag === "accepted" ? t("detail.riskAcceptedUndo") : t("detail.acceptRisk")}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => onFlag(flag === "reported" ? null : "reported")}
              >
                {flag === "reported" ? t("detail.reportedUndo") : t("detail.reportFalseAlarm")}
              </button>
            </>
          )}
          <button type="button" className="btn-icon" aria-label={t("buttons.close")} onClick={onClose}>
            ✕
          </button>
        </div>

        {!r && (
          <div style={{ padding: "26px" }} className="muted">
            {design.error ?? t("messages.analysisInProgress")}
          </div>
        )}

        {r && (
          <div className="modal-body">
            <div className="sticky">
              <div className="art artboard">
                {r.preview_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.preview_url} alt={design.filename} />
                ) : (
                  <div style={{ aspectRatio: "1/1" }} />
                )}
                {boxes &&
                  marked.map((f, i) => (
                    <div
                      key={i}
                      className="bbox"
                      data-verdict={verdict}
                      style={{
                        left: `${f.bbox!.x * 100}%`,
                        top: `${f.bbox!.y * 100}%`,
                        width: `${f.bbox!.w * 100}%`,
                        height: `${f.bbox!.h * 100}%`,
                      }}
                    >
                      {/* A box hugging the top edge has no room for a label
                          above it, and `.art` clips the overflow — so those
                          labels sit inside the box instead of over it. */}
                      <span data-inside={f.bbox!.y < 0.06}>
                        {t(`categories.${f.category}`)}
                      </span>
                    </div>
                  ))}
              </div>

              <div className="row" style={{ justifyContent: "center", marginTop: 14 }}>
                <button
                  type="button"
                  className="btn-icon"
                  aria-label={t("detail.previous")}
                  disabled={position <= 1}
                  onClick={onPrev}
                >
                  ‹
                </button>
                <span
                  className="muted"
                  style={{ fontSize: 13, whiteSpace: "nowrap" }}
                  title={t("detail.keyboardHint")}
                >
                  {position} {t("detail.of")} {total}
                </span>
                <button
                  type="button"
                  className="btn-icon"
                  aria-label={t("detail.next")}
                  disabled={position >= total}
                  onClick={onNext}
                >
                  ›
                </button>
              </div>

              <div className="row" style={{ justifyContent: "center", marginTop: 6 }}>
                {marked.length > 0 && (
                  <button type="button" className="btn btn-ghost" onClick={() => setBoxes((b) => !b)}>
                    {boxes ? t("buttons.showOriginal") : t("buttons.showAnnotated")}
                  </button>
                )}
                {r.original_url && (
                  <a
                    className="btn btn-ghost"
                    href={r.original_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t("detail.openOriginal")} ({r.image_width}×{r.image_height})
                  </a>
                )}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="row" style={{ gap: 14, fontSize: 13, color: "var(--color-neutral-700)" }}>
                <span>
                  <strong>{t("detail.niche")}</strong> · {r.niche.primary}
                </span>
                {r.niche.sub_niche && (
                  <span>
                    <strong>{t("detail.audience")}</strong> · {r.niche.sub_niche}
                  </span>
                )}
                {r.niche.style.length > 0 && (
                  <span>
                    <strong>{t("detail.style")}</strong> · {r.niche.style.join(", ")}
                  </span>
                )}
                {r.niche.motifs.length > 0 && (
                  <span>
                    <strong>{t("detail.motifs")}</strong> · {r.niche.motifs.join(", ")}
                  </span>
                )}
              </div>

              <div className={`verdict-card ${r.verdict}`}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div className="v">{t(`verdict.${r.verdict}`)}</div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.05em" }}>
                      {t("messages.confidence").toUpperCase()}
                    </div>
                    <div className="c">{r.confidence}%</div>
                  </div>
                </div>
                <div className="bar">
                  <span style={{ width: `${r.confidence}%` }} />
                </div>
                <p>{r.summary}</p>
                {r.verdict === "SAFE" && (
                  <p style={{ fontSize: 13, marginTop: 10 }}>{t("detail.safeCaveat")}</p>
                )}
              </div>

              {r.findings.length === 0 && <div className="ok">{t("detail.noIssues")}</div>}

              {r.findings.map((f, i) => (
                <div key={i} className="finding">
                  <div className="row" style={{ gap: 8 }}>
                    <span className={`sev ${f.severity}`}>{t(`severity.${f.severity}`)}</span>
                    <span className="cat">{t(`categories.${f.category}`)}</span>
                    <span className="cat">{Math.round(f.confidence * 100)}%</span>
                  </div>
                  <div className="t">{f.title}</div>
                  <div className="d">{f.description}</div>
                  {(f.rights_holder || f.location_hint) && (
                    <div className="how">
                      {f.rights_holder && (
                        <>
                          <strong>{t("detail.rightsHolder")}</strong> · {f.rights_holder}
                        </>
                      )}
                      {f.rights_holder && f.location_hint && " · "}
                      {f.location_hint}
                    </div>
                  )}
                  <Evidence f={f} t={t} />
                  <div className="fix">
                    <strong>{t("detail.howToFix")}</strong> — {f.remediation}
                  </div>
                </div>
              ))}

              {r.trademark_hits.length > 0 && (
                <div>
                  <h3>{t("detail.registerMatches")}</h3>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t("detail.text")}</th>
                        <th>{t("detail.registeredMark")}</th>
                        <th>{t("detail.similarity")}</th>
                        <th>{t("detail.owner")}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {r.trademark_hits.map((h, i) => (
                        <tr key={i}>
                          <td>{h.query}</td>
                          <td>{h.mark_text}</td>
                          <td>{h.similarity}%</td>
                          <td>{h.owner ?? "—"}</td>
                          <td>
                            {h.url && (
                              <a href={h.url} target="_blank" rel="noreferrer">
                                {h.serial_number ?? "TSDR"}
                              </a>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {r.ocr_text && (
                <div>
                  <h3>{t("detail.textInDesign")}</h3>
                  <pre className="prose">{r.ocr_text}</pre>
                </div>
              )}

              <div>
                <h3>{t("detail.reasoning")}</h3>
                <pre className="prose">{r.reasoning}</pre>
              </div>

              {r.policy_notes.length > 0 && (
                <div>
                  <h3>{t("detail.policyNotes")}</h3>
                  <ul className="muted" style={{ paddingLeft: 18, margin: 0 }}>
                    {r.policy_notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="muted" style={{ fontSize: 13 }}>
                {r.provider} · {(r.duration_ms / 1000).toFixed(1)}
                {t("messages.duration")}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
