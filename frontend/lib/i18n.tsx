"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

import en from "../public/locales/en.json";
import vi from "../public/locales/vi.json";

export type Language = "en" | "vi";

interface TranslationContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  t: (key: string) => string;
}

// Bundled, not fetched. A runtime `fetch("/locales/en.json")` has no origin
// during SSR, so the server rendered raw key names ("tabs.upload") while the
// client rendered real text — a guaranteed hydration mismatch — and on the
// client it raced the first paint. Static imports are available synchronously
// everywhere and cost one small JSON each.
const TRANSLATIONS: Record<Language, Record<string, unknown>> = { en, vi };

const STORAGE_KEY = "language";

const TranslationContext = createContext<TranslationContextType | undefined>(undefined);

function lookup(table: Record<string, unknown>, key: string): string | undefined {
  let value: unknown = table;
  for (const part of key.split(".")) {
    if (typeof value !== "object" || value === null) return undefined;
    value = (value as Record<string, unknown>)[part];
  }
  return typeof value === "string" ? value : undefined;
}

export function TranslationProvider({ children }: { children: React.ReactNode }) {
  // Always "en" on the server and on the first client render so the two agree;
  // a stored preference is applied after mount, below.
  const [lang, setLang] = useState<Language>("en");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "vi") setLang(saved);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo<TranslationContextType>(
    () => ({
      lang,
      setLang,
      // Fall back to English before falling back to the raw key, so a missing
      // Vietnamese string shows readable text instead of "labels.batches".
      t: (key) => lookup(TRANSLATIONS[lang], key) ?? lookup(TRANSLATIONS.en, key) ?? key,
    }),
    [lang],
  );

  // The provider must render unconditionally. Returning bare `children` while
  // waiting for mount left every consumer outside the context, so the first
  // render of any page that calls useTranslation() threw.
  return <TranslationContext.Provider value={value}>{children}</TranslationContext.Provider>;
}

export function useTranslation(): TranslationContextType {
  const context = useContext(TranslationContext);
  if (!context) {
    throw new Error("useTranslation must be used within TranslationProvider");
  }
  return context;
}
