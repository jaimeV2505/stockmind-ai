import { t, type Locale } from "../lib/i18n.ts";
import type { BannerMode } from "../lib/types.ts";

/** Always rendered: a user must always know which data mode is active. "unavailable" claims NO origin (used when data failed to load). */
export function ModeBanner({ locale, mode, source = "" }: { locale: Locale; mode: BannerMode; source?: string }) {
  const text =
    mode === "simulated" ? t(locale, "bannerSimulated")
    : mode === "delayed" ? t(locale, "bannerDelayed", { source })
    : mode === "live" ? t(locale, "bannerLive", { source })
    : t(locale, "bannerUnavailable");
  return (
    <div className={`banner banner-${mode}`} role="status" data-testid="mode-banner" data-mode={mode}>
      <strong>{text}</strong>
    </div>
  );
}
