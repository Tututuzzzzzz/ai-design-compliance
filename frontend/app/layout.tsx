import type { Metadata } from "next";
import "./globals.css";
import SiteHeader from "@/components/SiteHeader";
import { TranslationProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "AI Design Compliance Agent",
  description: "Niche detection + trademark & copyright screening for print-on-demand designs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `lang` is corrected client-side once a stored preference is read; keeping
    // "en" here matches the provider's initial state so hydration is clean.
    <html lang="en">
      <body>
        <TranslationProvider>
          <SiteHeader />
          {children}
        </TranslationProvider>
      </body>
    </html>
  );
}
