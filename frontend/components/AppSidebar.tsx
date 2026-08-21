"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import SystemStatus from "@/components/SystemStatus";
import { api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";

type Item = {
  key: string;
  icon: string;
  label: string;
  href: string | null;
  active: boolean;
  soon?: boolean;
};

export default function AppSidebar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const [latestJob, setLatestJob] = useState<string | null>(null);

  // "Dashboard" in the design means *the current batch*, which only exists once
  // something has been analysed. Resolve it to the newest job — the list comes
  // back newest-first — and leave the item inert until there is one. Re-read on
  // navigation rather than on a timer: chrome should not poll.
  useEffect(() => {
    api
      .jobs()
      .then((r) => setLatestJob(r.jobs[0]?.id ?? null))
      .catch(() => setLatestJob(null));
  }, [pathname]);

  const items: Item[] = [
    {
      key: "dashboard",
      icon: "▦",
      label: t("nav.dashboard"),
      href: latestJob ? `/jobs/${latestJob}` : null,
      active: pathname.startsWith("/jobs/"),
    },
    { key: "import", icon: "⇪", label: t("nav.import"), href: "/", active: pathname === "/" },
    {
      key: "history",
      icon: "≣",
      label: t("nav.history"),
      href: "/jobs",
      active: pathname === "/jobs",
    },
    { key: "watchlist", icon: "✳", label: t("nav.watchlist"), href: null, active: false, soon: true },
    { key: "settings", icon: "⚙", label: t("nav.settings"), href: null, active: false, soon: true },
  ];

  return (
    <aside className="sidebar">
      <Link href="/" className="brand">
        <span className="mark" aria-hidden="true">
          ◎
        </span>
        <span>
          <span className="name">Compliance</span>
          <span className="sub">DESIGN AGENT</span>
        </span>
      </Link>

      <nav>
        {items.map((i) =>
          i.href ? (
            <Link key={i.key} href={i.href} className="nav-item" data-active={i.active}>
              <span className="ico" aria-hidden="true">
                {i.icon}
              </span>
              {i.label}
            </Link>
          ) : (
            <span key={i.key} className="nav-item" data-disabled="true" aria-disabled="true">
              <span className="ico" aria-hidden="true">
                {i.icon}
              </span>
              {i.label}
              {i.soon && <span className="soon">{t("nav.soon")}</span>}
            </span>
          ),
        )}
      </nav>

      <div className="sidebar-foot">
        <SystemStatus />
        <LanguageSwitcher />
      </div>
    </aside>
  );
}
