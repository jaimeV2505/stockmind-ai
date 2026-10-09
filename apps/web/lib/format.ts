import type { Locale } from "./i18n.ts";

const TAG: Record<Locale, string> = { es: "es-ES", en: "en-US" };
export const DASH = "—";
const ok = (x: number | null | undefined): x is number => typeof x === "number" && Number.isFinite(x);

export function formatNumber(x: number | null | undefined, locale: Locale, digits = 2): string {
  return ok(x) ? new Intl.NumberFormat(TAG[locale], { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(x) : DASH;
}
export const formatPrice = (x: number | null | undefined, locale: Locale): string => formatNumber(x, locale, 2);
export function formatInt(x: number | null | undefined, locale: Locale): string {
  return ok(x) ? new Intl.NumberFormat(TAG[locale], { maximumFractionDigits: 0 }).format(x) : DASH;
}
/** x is a FRACTION (0.125 -> 12.5 %). */
export function formatPct(x: number | null | undefined, locale: Locale, digits = 2): string {
  return ok(x) ? new Intl.NumberFormat(TAG[locale], { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(x) : DASH;
}
export function formatDate(iso: string, locale: Locale): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : new Intl.DateTimeFormat(TAG[locale], { year: "numeric", month: "short", day: "2-digit", timeZone: "UTC" }).format(d);
}
export function formatDateTime(iso: string, locale: Locale): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? DASH
    : `${new Intl.DateTimeFormat(TAG[locale], { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).format(d)} UTC`;
}
/** Tone for colouring: never the only cue (callers also print the sign). */
export const tone = (x: number | null | undefined): "up" | "down" | "flat" => (!ok(x) || x === 0 ? "flat" : x > 0 ? "up" : "down");
export const signed = (s: string, x: number | null | undefined): string => (ok(x) && x > 0 ? `+${s}` : s);
