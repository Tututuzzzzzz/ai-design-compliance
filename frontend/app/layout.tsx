import type { Metadata } from "next";
import "./globals.css";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { TranslationProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "VinaSources — Design compliance check",
  description: "Niche detection + trademark & copyright screening for print-on-demand designs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `lang` is corrected client-side once a stored preference is read; keeping
    // "en" here matches the provider's initial state so hydration is clean.
    <html lang="en">
      <head>
        {/* Caprasimo (headings) + Figtree (body) — the Organic design system's
            typefaces. Preconnect so the display face lands with the first paint
            rather than after it. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Caprasimo&family=Figtree:wght@400;600;700&display=swap"
        />
      </head>
      <body>
        <TranslationProvider>
          <SiteHeader />
          {children}
          <SiteFooter />
        </TranslationProvider>
      </body>
    </html>
  );
}
