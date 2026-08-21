"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useTranslation } from "@/lib/i18n";

// Two entries only: the dashboard's own tab row owns the Export and History
// views, so duplicating them up here would give the same view two different
// "current" markers.
const LINKS = [
  { href: "/", key: "nav.new" },
  { href: "/dashboard", key: "nav.dashboard" },
];

export default function SiteHeader() {
  const { t } = useTranslation();
  const path = usePathname();

  return (
    <header className="top">
      <div className="inner">
        {/* Logo only. The tagline and the register chip that used to sit here
            moved to the footer, where the disclaimer already says the same
            thing — and the row now fits on one line at laptop widths. */}
        <Link href="/" className="brand" aria-label={t("header.title")}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="https://vinasources.com/icons/wws/logo-vinasources.svg" alt="VinaSources" />
        </Link>
        <nav>
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={path === l.href ? "page" : undefined}
            >
              {t(l.key)}
            </Link>
          ))}
          <LanguageSwitcher />
        </nav>
      </div>
    </header>
  );
}
