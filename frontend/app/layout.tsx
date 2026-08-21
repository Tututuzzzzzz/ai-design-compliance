import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import AppSidebar from "@/components/AppSidebar";
import { TranslationProvider } from "@/lib/i18n";

// Fetched at build time and self-hosted from the bundle, so the running app
// never reaches out to Google. The `vietnamese` subset is required — the UI
// ships a full VI locale (public/locales/vi.json).
const archivo = Archivo({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-archivo",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AI Design Compliance Agent",
  description: "Niche detection + trademark & copyright screening for print-on-demand designs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `lang` is corrected client-side once a stored preference is read; keeping
    // "en" here matches the provider's initial state so hydration is clean.
    <html lang="en" className={`${archivo.variable} ${plexMono.variable}`}>
      <body>
        <TranslationProvider>
          {/* Fixed 216px rail, one scrolling content pane — the shell holds the
              viewport so only the pane moves, as in the canvas design. */}
          <div className="app">
            <AppSidebar />
            <div className="content">{children}</div>
          </div>
        </TranslationProvider>
      </body>
    </html>
  );
}
