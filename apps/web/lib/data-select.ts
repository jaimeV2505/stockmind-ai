// Which snapshot file the server may read, chosen EXPLICITLY by STOCKMIND_DATA. An unknown value is an error (never "default to demo").
import type { Loaded } from "./snapshot.ts";

export type DataKind = "demo" | "market";
export type Selection = { ok: true; kind: DataKind; file: string } | { ok: false; error: string };

export function resolveSelection(value: string | undefined): Selection {
  const v = (value ?? "").trim().toLowerCase();
  if (v === "" || v === "demo") return { ok: true, kind: "demo", file: "demo-snapshot.json" };
  if (v === "market") return { ok: true, kind: "market", file: "market-snapshot.json" };
  return { ok: false, error: `STOCKMIND_DATA must be "demo" or "market", got ${JSON.stringify(value)}` };
}

/** The loaded file must match the configured kind: a demo file may never be served as market data, nor the reverse. */
export function checkSelection(kind: DataKind, loaded: Loaded): Loaded {
  if (!loaded.ok) return loaded;
  const simulated = loaded.data.meta.mode === "simulated";
  if (kind === "demo" && !simulated) return { ok: false, error: "STOCKMIND_DATA=demo but the file is not simulated data" };
  if (kind === "market" && simulated) return { ok: false, error: "STOCKMIND_DATA=market but the file is simulated data: refusing to serve it as real" };
  return loaded;
}
