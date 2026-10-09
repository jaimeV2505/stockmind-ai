// Server-only: reads the committed snapshot at build/render time. Failure is returned as a value, never papered over.
import { readFileSync } from "node:fs";
import path from "node:path";
import { loadFromText, type Loaded } from "./snapshot.ts";

export function loadSnapshotFile(): Loaded {
  let text: string;
  try {
    text = readFileSync(path.join(process.cwd(), "data", "demo-snapshot.json"), "utf8");
  } catch (e) {
    return { ok: false, error: `cannot read data/demo-snapshot.json: ${e instanceof Error ? e.message : String(e)}` };
  }
  return loadFromText(text);
}
