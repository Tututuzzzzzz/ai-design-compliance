"use client";

import { useTranslation } from "@/lib/i18n";

const LANGS = [
  { key: "en", label: "English" },
  { key: "vi", label: "Tiếng Việt" },
] as const;

export default function LanguageSwitcher() {
  const { lang, setLang } = useTranslation();

  return (
    <div className="chips" role="group" aria-label="Language">
      {LANGS.map((l) => (
        <button
          key={l.key}
          type="button"
          className="chip"
          data-on={lang === l.key}
          aria-pressed={lang === l.key}
          onClick={() => setLang(l.key)}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
