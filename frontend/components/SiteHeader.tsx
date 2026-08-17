"use client";

import Link from "next/link";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useTranslation } from "@/lib/i18n";

export default function SiteHeader() {
  const { t } = useTranslation();

  return (
    <header className="top">
      <div className="inner">
        <div>
          <h1>
            <Link href="/" style={{ color: "inherit" }}>
              {t("header.title")}
            </Link>
          </h1>
          <p>{t("header.tagline")}</p>
        </div>
        <div className="spacer" />
        <Link href="/" className="muted">
          {t("nav.new")}
        </Link>
        <Link href="/jobs" className="muted">
          {t("nav.batches")}
        </Link>
        <LanguageSwitcher />
      </div>
    </header>
  );
}
