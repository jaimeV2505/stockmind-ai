// The Python engines emit English warnings/notes. Known ones are localised here; UNKNOWN ones are shown verbatim (never dropped).
// Notes that duplicate text the UI already shows in a dedicated, localised element are reported as "redundant" and may be hidden.
import type { Locale } from "./i18n.ts";

interface Rule { test: RegExp; es: (m: RegExpMatchArray) => string; en: (m: RegExpMatchArray) => string; redundant?: boolean }

const RULES: Rule[] = [
  { test: /^signal on the last bar ignored/i, es: () => "Señal en la última barra ignorada: no hay barra siguiente donde ejecutarla.", en: () => "Signal on the last bar ignored: no next bar to execute on." },
  { test: /^(\d+) entry signal\(s\) skipped: not enough cash/i, es: (m) => `${m[1]} señal(es) de entrada omitida(s): efectivo insuficiente para una acción tras costes.`, en: (m) => `${m[1]} entry signal(s) skipped: not enough cash for one share after costs.` },
  { test: /^Similarity scores are uncalibrated/i, es: () => "", en: () => "", redundant: true },
  { test: /^n=(\d+) < 30: no confidence interval/i, es: () => "", en: () => "", redundant: true },
  { test: /^Matches drawn from the same calendar period are correlated/i, es: () => "Las coincidencias de un mismo período están correlacionadas: la muestra efectiva es menor que n.", en: (m) => m.input ?? "" },
  { test: /^very small sample: treat the statistics as anecdotal/i, es: () => "Muestra muy pequeña: trate las estadísticas como anecdóticas.", en: (m) => m.input ?? "" },
  { test: /INSUFFICIENT EVIDENCE/i, es: () => "Sin coincidencias históricas: EVIDENCIA INSUFICIENTE.", en: (m) => m.input ?? "" },
];

export interface LocalisedNote { text: string; redundant: boolean; known: boolean }

export function localiseNote(locale: Locale, note: string): LocalisedNote {
  for (const r of RULES) {
    const m = note.match(r.test);
    if (m) return { text: (locale === "es" ? r.es : r.en)(m) || note, redundant: r.redundant === true, known: true };
  }
  return { text: note, redundant: false, known: false };
}

/** Localised notes to display: redundant ones hidden, unknown ones kept verbatim, original order preserved. */
export const visibleNotes = (locale: Locale, notes: string[]): string[] =>
  notes.map((n) => localiseNote(locale, n)).filter((n) => !n.redundant).map((n) => n.text);
