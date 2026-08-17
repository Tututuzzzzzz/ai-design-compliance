"use client";

import { useState } from "react";
import { useTranslation } from "@/lib/i18n";
import type { Design, Finding } from "@/lib/types";

function Evidence({ f }: { f: Finding }) {
  if (!f.evidence?.length) return null;
  return (
    <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--muted)" }}>
      {f.evidence.map((e, i) => (
        <li key={i}>
          <strong>{e.source.replace(/_/g, " ")}</strong>: {e.detail}
          {e.reference_id && ` (#${e.reference_id})`}
          {e.url && (
            <>
              {" — "}
              <a href={e.url} target="_blank" rel="noreferrer">
                verify
              </a>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function DesignDetail({ design, onClose }: { design: Design; onClose: () => void }) {
  const { t } = useTranslation();
  const [annotated, setAnnotated] = useState(true);
  const r = design.report;

  const image = (annotated && r?.annotated_url) || r?.preview_url;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="panel" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <div>
            <h2 style={{ marginBottom: 4 }}>{design.filename}</h2>
            <div className="row" style={{ gap: 8 }}>
              <span className={`badge ${r?.verdict ?? "PENDING"}`}>{r?.verdict ?? design.status}</span>
              {r && <span className="muted">{t("messages.confidence")} {r.confidence}%</span>}
              {r && <span className="muted">· {r.provider}</span>}
              {r && <span className="muted">· {(r.duration_ms / 1000).toFixed(1)}{t("messages.duration")}</span>}
            </div>
          </div>
          <div className="spacer" />
          <button className="ghost" onClick={onClose}>
            {t("buttons.close")}
          </button>
        </div>

        {!r && <p className="muted">{t("messages.analysisInProgress")}</p>}

        {r && (
          <div className="grid two" style={{ marginTop: 18 }}>
            <div>
              {image ? (
                <>
                  <div
                    style={{
                      background: "#fff",
                      borderRadius: 10,
                      overflow: "hidden",
                      border: "1px solid var(--border)",
                    }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={image} alt={design.filename} style={{ width: "100%", display: "block" }} />
                  </div>
                  {r.annotated_url && (
                    <div className="row" style={{ marginTop: 8 }}>
                      <button className="ghost" onClick={() => setAnnotated((a) => !a)}>
                        {annotated ? t("buttons.showOriginal") : t("buttons.showAnnotated")}
                      </button>
                      <span className="muted">
                        {r.findings.filter((f) => f.bbox).length} {t("messages.marked")}
                      </span>
                    </div>
                  )}
                </>
              ) : (
                <p className="muted">No preview available.</p>
              )}

              <h3 style={{ marginTop: 20 }}>Niche</h3>
              <table>
                <tbody>
                  <tr>
                    <th>Primary</th>
                    <td>{r.niche.primary}</td>
                  </tr>
                  {r.niche.sub_niche && (
                    <tr>
                      <th>Sub-niche</th>
                      <td>{r.niche.sub_niche}</td>
                    </tr>
                  )}
                  {r.niche.audience && (
                    <tr>
                      <th>Audience</th>
                      <td>{r.niche.audience}</td>
                    </tr>
                  )}
                  {r.niche.style.length > 0 && (
                    <tr>
                      <th>Style</th>
                      <td>{r.niche.style.join(", ")}</td>
                    </tr>
                  )}
                  {r.niche.motifs.length > 0 && (
                    <tr>
                      <th>Motifs</th>
                      <td>{r.niche.motifs.join(", ")}</td>
                    </tr>
                  )}
                </tbody>
              </table>

              {r.ocr_text && (
                <>
                  <h3 style={{ marginTop: 20 }}>Text in design</h3>
                  <pre className="reasoning">{r.ocr_text}</pre>
                </>
              )}
            </div>

            <div>
              <h3>Findings ({r.findings.length})</h3>
              {r.findings.length === 0 && (
                <div className="ok">No IP or policy issues detected in this design.</div>
              )}
              {r.findings.map((f, i) => (
                <div key={i} className={`finding ${f.severity}`}>
                  <div className="row" style={{ gap: 8 }}>
                    <span className={`sev ${f.severity}`}>{f.severity}</span>
                    <span className="muted" style={{ fontSize: 12 }}>
                      {f.category.replace(/_/g, " ")} · {Math.round(f.confidence * 100)}%
                    </span>
                  </div>
                  <div className="t" style={{ marginTop: 6 }}>
                    {i + 1}. {f.title}
                  </div>
                  <p>{f.description}</p>
                  {f.rights_holder && (
                    <p style={{ marginTop: 0 }}>
                      <strong>Rights holder:</strong> {f.rights_holder}
                    </p>
                  )}
                  {(f.location_hint || f.bbox) && (
                    <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                      Location: {f.location_hint}
                      {f.bbox &&
                        ` — box x=${f.bbox.x.toFixed(2)} y=${f.bbox.y.toFixed(2)} w=${f.bbox.w.toFixed(2)} h=${f.bbox.h.toFixed(2)}`}
                    </p>
                  )}
                  <Evidence f={f} />
                  <div className="fix">
                    <strong>How to fix:</strong> {f.remediation}
                  </div>
                </div>
              ))}

              {r.trademark_hits.length > 0 && (
                <>
                  <h3 style={{ marginTop: 22 }}>Register matches</h3>
                  <table>
                    <thead>
                      <tr>
                        <th>Text</th>
                        <th>Registered mark</th>
                        <th>Sim.</th>
                        <th>Owner</th>
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
                </>
              )}

              <h3 style={{ marginTop: 22 }}>Reasoning</h3>
              <pre className="reasoning">{r.reasoning}</pre>

              {r.policy_notes.length > 0 && (
                <>
                  <h3 style={{ marginTop: 22 }}>Policy notes</h3>
                  <ul className="muted" style={{ paddingLeft: 18, fontSize: 12.5 }}>
                    {r.policy_notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
