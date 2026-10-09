import type { Metadata } from "next";
import { DashboardView } from "../../components/Views.tsx";
import { isLocale, t, DEFAULT_LOCALE } from "../../lib/i18n.ts";
import { loadSnapshotFile } from "../../lib/server-data.ts";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale: raw } = await params;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  return { title: `${t(locale, "appName")} — ${t(locale, "dashboardTitle")}`, description: t(locale, "dashboardIntro") };
}

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  return <DashboardView locale={locale} loaded={loadSnapshotFile()} />;
}
