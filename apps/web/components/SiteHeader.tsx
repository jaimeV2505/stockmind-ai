import Link from "next/link";
import { LOCALES, t, type Locale } from "../lib/i18n.ts";

export function SiteHeader({ locale, pathSuffix = "" }: { locale: Locale; pathSuffix?: string }) {
  return (
    <header className="site-header">
      <Link href={`/${locale}`} className="brand">
        {t(locale, "appName")}
      </Link>
      <nav aria-label="Main">
        <Link href={`/${locale}`}>{t(locale, "navDashboard")}</Link>
        <Link href={`/${locale}/method`}>{t(locale, "navMethod")}</Link>
      </nav>
      <nav aria-label={t(locale, "language")} className="locales">
        {LOCALES.map((l) => (
          <Link key={l} href={`/${l}${pathSuffix}`} aria-current={l === locale ? "true" : undefined} lang={l} hrefLang={l}>
            {l.toUpperCase()}
          </Link>
        ))}
      </nav>
    </header>
  );
}
