import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { isLocale, LOCALES } from "../../lib/i18n.ts";
import "../globals.css";

export const dynamicParams = false;
export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

// The locale segment is the ROOT layout so <html lang> is correct for each language.
export default async function RootLayout({ children, params }: { children: ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return (
    <html lang={locale}>
      <body>
        <a href="#main" className="skip">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
