import { t, type Locale } from "../lib/i18n.ts";
import type { Mode } from "../lib/types.ts";

/** Always rendered: a user must always know which data mode is active (simulated / delayed / live). */
export function ModeBanner({ locale, mode }: { locale: Locale; mode: Mode }) {
  const text = mode === "simulated" ? t(locale, "bannerSimulated") : mode === "delayed" ? t(locale, "bannerDelayed") : t(locale, "bannerLive");
  return (
    <div className={`banner banner-${mode}`} role="status" data-testid="mode-banner" data-mode={mode}>
      <strong>{text}</strong>
    </div>
  );
}
