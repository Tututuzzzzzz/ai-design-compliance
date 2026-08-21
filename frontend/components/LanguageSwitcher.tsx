"use client";

import { useTranslation } from "@/lib/i18n";

// Two letters, not two words: the switcher shares the header row with the
// provenance chip and the nav links, and full language names pushed that row
// onto a second line.
const LANGS = [
  { key: "en", label: "EN", title: "English" },
  { key: "vi", label: "VI", title: "Tiếng Việt" },
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
          title={l.title}
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
