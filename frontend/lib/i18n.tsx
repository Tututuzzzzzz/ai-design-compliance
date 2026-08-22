"use client";

import { createContext, useContext } from "react";

import en from "../public/locales/en.json";

/** English only. The type stays a union of one so `Metadata.language` and the
 *  export URLs keep a named type instead of a bare string. */
export type Language = "en";

interface TranslationContextType {
  lang: Language;
  t: (key: string) => string;
}

// Bundled, not fetched. A runtime `fetch("/locales/en.json")` has no origin
// during SSR, so the server rendered raw key names ("tabs.upload") while the
// client rendered real text — a guaranteed hydration mismatch — and on the
// client it raced the first paint. A static import is available synchronously
// everywhere and costs one small JSON.
const STRINGS = en as Record<string, unknown>;

const TranslationContext = createContext<TranslationContextType | undefined>(undefined);

function lookup(table: Record<string, unknown>, key: string): string | undefined {
  let value: unknown = table;
  for (const part of key.split(".")) {
    if (typeof value !== "object" || value === null) return undefined;
    value = (value as Record<string, unknown>)[part];
  }
  return typeof value === "string" ? value : undefined;
}

// Constant, so no re-render is ever triggered by it.
const VALUE: TranslationContextType = {
  lang: "en",
  // The raw key is the last resort: a missing string shows "labels.batches"
  // rather than an empty cell, which is easier to spot and fix.
  t: (key) => lookup(STRINGS, key) ?? key,
};

export function TranslationProvider({ children }: { children: React.ReactNode }) {
  return <TranslationContext.Provider value={VALUE}>{children}</TranslationContext.Provider>;
}

export function useTranslation(): TranslationContextType {
  const context = useContext(TranslationContext);
  if (!context) {
    throw new Error("useTranslation must be used within TranslationProvider");
  }
  return context;
}
