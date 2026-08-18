"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import HealthBar from "@/components/HealthBar";
import MetadataPicker from "@/components/MetadataPicker";
import { api, type Metadata } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";

type Tab = "upload" | "csv" | "link" | "folder";

export default function Home() {
  const { t, lang } = useTranslation();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("upload");
  const [metaState, setMeta] = useState<Metadata>({ markets: ["US"], platforms: ["etsy"] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [csv, setCsv] = useState<File | null>(null);
  const [csvAttachments, setCsvAttachments] = useState<File[]>([]);
  const [links, setLinks] = useState("");
  const [folder, setFolder] = useState("");

  const TABS: { key: Tab; label: string; hint: string }[] = [
    { key: "upload", label: t("tabs.upload"), hint: t("hints.upload") },
    { key: "csv", label: t("tabs.csv"), hint: t("hints.csv") },
    { key: "link", label: t("tabs.link"), hint: t("hints.link") },
    { key: "folder", label: t("tabs.folder"), hint: t("hints.folder") },
  ];

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

  return (
    <main className="shell">
      <HealthBar />

      <div className="card">
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.key} data-active={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        <p className="muted" style={{ marginTop: 0 }}>
          {TABS.find((t) => t.key === tab)!.hint}
        </p>

        {tab === "upload" && (
          <div className="field">
            <label>{t("labels.designFiles")}</label>
            <input
              type="file"
              multiple
              accept=".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif,.heic,.psd,.pdf,.ai,.eps"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            {files.length > 0 && (
              <p className="muted" style={{ marginBottom: 0 }}>
                {files.length} {t("labels.filesSelected")}
              </p>
            )}
          </div>
        )}

        {tab === "csv" && (
          <>
            <div className="field">
              <label>{t("labels.csvManifest")}</label>
              <input
                type="file"
                accept=".csv,.tsv,.txt"
                onChange={(e) => setCsv(e.target.files?.[0] ?? null)}
              />
              <p className="muted" style={{ marginBottom: 0 }}>
                {t("messages.csvColumnsHelp")} <code>filename</code>, <code>url</code> /{" "}
                <code>link</code>, <code>title</code>, <code>markets</code>, <code>platforms</code>,{" "}
                <code>notes</code>. {t("messages.csvOverrideHelp")}
              </p>
            </div>
            <div className="field">
              <label>{t("labels.attachments")}</label>
              <input
                type="file"
                multiple
                onChange={(e) => setCsvAttachments(Array.from(e.target.files ?? []))}
              />
              <p className="muted" style={{ marginBottom: 0 }}>
                {t("messages.csvAttachmentsHelp")}
              </p>
            </div>
          </>
        )}

        {tab === "link" && (
          <div className="field">
            <label>{t("labels.urls")}</label>
            <textarea
              value={links}
              placeholder={
                "https://drive.google.com/file/d/FILE_ID/view\nhttps://www.dropbox.com/s/xxx/design.png?dl=0\nhttps://bucket.s3.amazonaws.com/art.png"
              }
              onChange={(e) => setLinks(e.target.value)}
            />
          </div>
        )}

        {tab === "folder" && (
          <div className="field">
            <label>{t("labels.googleDriveFolder")}</label>
            <input
              type="text"
              value={folder}
              placeholder="https://drive.google.com/drive/folders/FOLDER_ID"
              onChange={(e) => setFolder(e.target.value)}
            />
            <p className="muted" style={{ marginBottom: 0 }}>
              {t("messages.driveFolderHelpPrefix")} <code>GOOGLE_API_KEY</code>{" "}
              {t("messages.driveFolderHelpSuffix")}
            </p>
          </div>
        )}

        <hr style={{ border: 0, borderTop: "1px solid var(--border)", margin: "18px 0" }} />

        <MetadataPicker value={metaState} onChange={setMeta} />

        {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}

        <button className="primary" onClick={submit} disabled={busy}>
          {busy ? t("buttons.submit") + "…" : t("buttons.submit")}
        </button>
      </div>
    </main>
  );
}
