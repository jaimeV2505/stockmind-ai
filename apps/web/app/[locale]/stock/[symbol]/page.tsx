import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { StockView } from "../../../../components/Views.tsx";
import { DEFAULT_LOCALE, isLocale, LOCALES, t } from "../../../../lib/i18n.ts";
import { loadSnapshotFile } from "../../../../lib/server-data.ts";

type Params = Promise<{ locale: string; symbol: string }>;

export function generateStaticParams() {
  const loaded = loadSnapshotFile();
  return loaded.ok ? LOCALES.flatMap((locale) => loaded.data.symbols.map((s) => ({ locale, symbol: s.symbol }))) : [];
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale: raw, symbol } = await params;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  return { title: `${symbol} — ${t(locale, "appName")}`, description: t(locale, "footer") };
}

export default async function Page({ params }: { params: Params }) {
  const { locale: raw, symbol } = await params;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  const loaded = loadSnapshotFile();
  if (loaded.ok && !loaded.data.symbols.some((s) => s.symbol === symbol)) notFound();   // unknown symbol => real 404, not an empty page
  return <StockView locale={locale} loaded={loaded} symbol={symbol} />;
}
