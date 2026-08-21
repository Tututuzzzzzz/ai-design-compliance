"use client";

import { useTranslation } from "@/lib/i18n";

export default function SiteFooter() {
  const { t } = useTranslation();

  return (
    <footer className="legal">
      {t("footer.powered")}
      <br />
      {t("footer.disclaimer")}
    </footer>
  );
}
