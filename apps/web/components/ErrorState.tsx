import { t, type Locale } from "../lib/i18n.ts";

/** Shown when data is missing/invalid. Never falls back to invented numbers. */
export function ErrorState({ locale, detail }: { locale: Locale; detail: string }) {
  return (
    <section className="card error" role="alert" data-testid="error-state">
      <h1>{t(locale, "errorTitle")}</h1>
      <p>{t(locale, "errorBody")}</p>
      <pre>{detail}</pre>
    </section>
  );
}
