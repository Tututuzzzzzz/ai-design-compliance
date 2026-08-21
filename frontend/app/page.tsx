"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import MetadataPicker from "@/components/MetadataPicker";
import { api, type Metadata } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";

type Tab = "upload" | "csv" | "link" | "folder";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif,.heic,.psd,.pdf,.ai,.eps";

/** Identity for de-duplicating a re-picked or re-dropped file. */
const keyOf = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;

export default function Home() {
  const { t, lang } = useTranslation();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("upload");
  const [metaState, setMeta] = useState<Metadata>({ markets: ["US"], platforms: ["etsy"] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const [files, setFiles] = useState<File[]>([]);
  const [csv, setCsv] = useState<File | null>(null);
  const [csvAttachments, setCsvAttachments] = useState<File[]>([]);
  const [links, setLinks] = useState("");
  const [folder, setFolder] = useState("");

  // The hero only earns its space before the first batch exists. `null` means
  // "not known yet" so neither state flashes while the request is in flight.
  const [firstRun, setFirstRun] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .jobs()
      .then((r) => setFirstRun(r.jobs.length === 0))
      .catch(() => setFirstRun(false));
  }, []);

  const TABS: { key: Tab; label: string }[] = [
    { key: "upload", label: t("tabs.upload") },
    { key: "csv", label: t("tabs.csv") },
    { key: "link", label: t("tabs.link") },
    { key: "folder", label: t("tabs.folder") },
  ];

  /** Add to the selection rather than replace it — picking twice should mean
   *  "and also these", which is what dropping twice already means. */
  function addFiles(incoming: FileList | File[] | null) {
    const list = Array.from(incoming ?? []);
    if (!list.length) return;
    setFiles((prev) => {
      const seen = new Set(prev.map(keyOf));
      return [...prev, ...list.filter((f) => !seen.has(keyOf(f)))];
    });
  }

  const dragProps = {
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      if (!dragging) setDragging(true);
    },
    onDragLeave: (e: React.DragEvent) => {
      e.preventDefault();
      // Ignore the leave events fired when the pointer crosses a child element.
      if (e.currentTarget.contains(e.relatedTarget as Node)) return;
      setDragging(false);
    },
  };

  function dropFiles(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  function dropCsv(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setCsv(f);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      // The report is written once, in the language selected now — switching the
      // UI later re-labels the chrome but never rewrites an analysed report.
      const meta = { ...metaState, language: lang };
      let res: { job_id: string };
      if (tab === "upload") {
        if (!files.length) throw new Error(t("messages.chooseDesignFile"));
        res = await api.uploadFiles(files, meta);
      } else if (tab === "csv") {
        if (!csv) throw new Error(t("messages.chooseCsvFile"));
        res = await api.uploadCsv(csv, csvAttachments, meta);
      } else if (tab === "link") {
        const urls = links
          .split(/[\n,]/)
          .map((u) => u.trim())
          .filter(Boolean);
        if (!urls.length) throw new Error(t("messages.pasteUrl"));
        res = await api.submitLinks(urls, meta);
      } else {
        if (!folder.trim()) throw new Error(t("messages.pasteGoogleDrive"));
        res = await api.submitFolder(folder.trim(), meta);
      }
      router.push(`/jobs/${res.job_id}`);
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setBusy(false);
    }
  }

  const analyzeLabel = busy
    ? `${t("buttons.submit")}…`
    : files.length > 1
      ? t("buttons.analyseMany").replace("{n}", String(files.length))
      : t("buttons.analyseOne");

  return (
    <main className="shell">
      {firstRun && (
        <section className="hero">
          <div>
            <h1>{t("hero.title")}</h1>
            <p>{t("hero.lede")}</p>
          </div>
          <div className="steps">
            {([1, 2, 3] as const).map((n) => (
              <div key={n}>
                <span className="num">{n}</span>
                <div>
                  <strong>{t(`hero.step${n}`)}</strong>
                  <br />
                  {t(`hero.step${n}detail`)}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel" style={{ marginTop: 28, marginBottom: 24 }}>
        <div className="panel-head">
          <div>
            <h2>{t("newCheck.title")}</h2>
            <div className="sub">{t("newCheck.formats")}</div>
          </div>
          <div className="pills">
            {TABS.map((x) => (
              <button
                key={x.key}
                type="button"
                aria-pressed={tab === x.key}
                onClick={() => setTab(x.key)}
              >
                {x.label}
              </button>
            ))}
          </div>
        </div>

        {tab === "upload" && (
          <>
            <div className="dropzone" data-over={dragging} {...dragProps} onDrop={dropFiles}>
              <input
                id="file-input"
                type="file"
                multiple
                accept={ACCEPT}
                onChange={(e) => {
                  addFiles(e.target.files);
                  // Reset so re-picking the same file fires change again.
                  e.target.value = "";
                }}
                style={{ display: "none" }}
              />
              <div className="row" style={{ justifyContent: "center" }}>
                <label htmlFor="file-input" className="btn btn-primary">
                  {t("buttons.browseFiles")}
                </label>
                <span style={{ fontSize: 15, color: "var(--color-neutral-700)" }}>
                  {t("newCheck.dropHere")}
                </span>
              </div>
              <div className="hint">{t("newCheck.eachVerdict")}</div>
              {files.length > 0 && (
                <div className="row" style={{ justifyContent: "center", marginTop: 14, gap: 6 }}>
                  {files.map((f) => (
                    <span key={keyOf(f)} className="file-chip">
                      {f.name}
                      <button
                        type="button"
                        aria-label={t("buttons.removeFile")}
                        onClick={() => setFiles((prev) => prev.filter((x) => keyOf(x) !== keyOf(f)))}
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            {files.length > 0 && (
              <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
                <button type="button" className="btn btn-ghost" onClick={() => setFiles([])}>
                  {t("buttons.removeAll")}
                </button>
                <button type="button" className="btn btn-primary btn-lg" onClick={submit} disabled={busy}>
                  {analyzeLabel}
                </button>
              </div>
            )}
          </>
        )}

        {tab === "csv" && (
          <>
            <div className="dropzone" data-over={dragging} {...dragProps} onDrop={dropCsv}>
              <input
                id="csv-input"
                type="file"
                accept=".csv,.tsv,.txt"
                onChange={(e) => setCsv(e.target.files?.[0] ?? null)}
                style={{ display: "none" }}
              />
              <input
                id="csv-attachments"
                type="file"
                multiple
                accept={ACCEPT}
                onChange={(e) => setCsvAttachments(Array.from(e.target.files ?? []))}
                style={{ display: "none" }}
              />
              <div className="row" style={{ justifyContent: "center" }}>
                <label htmlFor="csv-input" className="btn btn-primary">
                  {t("buttons.browseCsv")}
                </label>
                <span style={{ fontSize: 15, color: "var(--color-neutral-700)" }}>
                  {t("newCheck.dropCsv")}
                </span>
              </div>
              <div className="hint">{t("newCheck.csvColumns")}</div>
              <div className="row" style={{ justifyContent: "center", marginTop: 14, gap: 6 }}>
                {csv && (
                  <span className="file-chip">
                    {csv.name}
                    <button
                      type="button"
                      aria-label={t("buttons.removeFile")}
                      onClick={() => setCsv(null)}
                    >
                      ✕
                    </button>
                  </span>
                )}
                {/* Only meaningful when the CSV names local files rather than
                    URLs — offered next to the CSV so the pairing is obvious. */}
                <label htmlFor="csv-attachments" className="btn btn-ghost">
                  {csvAttachments.length
                    ? t("buttons.attachedN").replace("{n}", String(csvAttachments.length))
                    : t("buttons.attachFiles")}
                </label>
              </div>
            </div>
            {csv && (
              <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
                <button type="button" className="btn btn-primary btn-lg" onClick={submit} disabled={busy}>
                  {busy ? `${t("buttons.submit")}…` : t("buttons.analyseBatch")}
                </button>
              </div>
            )}
          </>
        )}

        {tab === "link" && (
          <div className="pad">
            <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
              <textarea
                value={links}
                placeholder={t("newCheck.linkPlaceholder")}
                onChange={(e) => setLinks(e.target.value)}
                style={{ minHeight: 64 }}
              />
              <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
                {busy ? `${t("buttons.submit")}…` : t("buttons.fetch")}
              </button>
            </div>
            <div className="hint" style={{ textAlign: "left" }}>
              {t("newCheck.linkHint")}
            </div>
          </div>
        )}

        {tab === "folder" && (
          <div className="pad">
            <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
              <input
                type="text"
                value={folder}
                placeholder="https://drive.google.com/drive/folders/FOLDER_ID"
                onChange={(e) => setFolder(e.target.value)}
              />
              <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
                {busy ? `${t("buttons.submit")}…` : t("buttons.connect")}
              </button>
            </div>
            <div className="hint" style={{ textAlign: "left" }}>
              {t("messages.driveFolderHelpPrefix")} <code>GOOGLE_API_KEY</code>{" "}
              {t("messages.driveFolderHelpSuffix")}
            </div>
          </div>
        )}

        <MetadataPicker value={metaState} onChange={setMeta} />

        {error && (
          <div className="error" style={{ marginTop: 14, marginBottom: 0 }}>
            {error}
          </div>
        )}
      </section>
    </main>
  );
}
