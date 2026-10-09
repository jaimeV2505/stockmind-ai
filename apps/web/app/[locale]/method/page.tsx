import type { Metadata } from "next";
import { MethodView } from "../../../components/Views.tsx";
import { DEFAULT_LOCALE, isLocale, t } from "../../../lib/i18n.ts";
import { loadSnapshotFile } from "../../../lib/server-data.ts";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale: raw } = await params;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  return { title: `${t(locale, "appName")} — ${t(locale, "methodTitle")}` };
}

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  const loaded = loadSnapshotFile();
  return <MethodView locale={locale} mode={loaded.ok ? loaded.data.meta.mode : "simulated"} />;
}
