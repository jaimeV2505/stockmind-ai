// Site access control (HTTP Basic) used by middleware.ts. Pure and tested. When REAL market data is served a password is MANDATORY:
// provider licences generally forbid public redistribution, so the site fails closed instead of going public by accident.
export type Access = { action: "allow" } | { action: "challenge" } | { action: "misconfigured"; reason: string };
export const MIN_PASSWORD_LENGTH = 12;

export interface AccessInput {
  authorization: string | null;
  dataMode: string | undefined;     // STOCKMIND_DATA
  user: string | undefined;         // SITE_USER (default "stockmind")
  password: string | undefined;     // SITE_PASSWORD
}

/** Length-independent comparison (no early exit on the first differing character). */
export function safeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const x = enc.encode(a);
  const y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

export function parseBasic(header: string | null): { user: string; password: string } | null {
  if (!header) return null;
  const m = /^Basic\s+([A-Za-z0-9+/=_-]+)$/i.exec(header.trim());
  if (!m) return null;
  let decoded: string;
  try {
    const bin = atob(m[1].replace(/-/g, "+").replace(/_/g, "/"));
    decoded = new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  } catch {
    return null;
  }
  const i = decoded.indexOf(":");
  return i < 0 ? null : { user: decoded.slice(0, i), password: decoded.slice(i + 1) };
}

export function decideAccess(input: AccessInput): Access {
  const market = (input.dataMode ?? "").trim().toLowerCase() === "market";
  const pw = input.password ?? "";
  if (market && pw === "") return { action: "misconfigured", reason: "SITE_PASSWORD must be set when STOCKMIND_DATA=market" };
  if (market && pw.length < MIN_PASSWORD_LENGTH) return { action: "misconfigured", reason: `SITE_PASSWORD must be at least ${MIN_PASSWORD_LENGTH} characters when serving market data` };
  if (pw === "") return { action: "allow" };                       // demo data, no password configured: public by design
  const cred = parseBasic(input.authorization);
  if (!cred) return { action: "challenge" };
  const okUser = safeEqual(cred.user, input.user && input.user !== "" ? input.user : "stockmind");
  const okPass = safeEqual(cred.password, pw);
  return okUser && okPass ? { action: "allow" } : { action: "challenge" };
}
