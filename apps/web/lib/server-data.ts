// Server-only: reads the selected snapshot at build/render time. Failure is returned as a value, never papered over.
import { readFileSync } from "node:fs";
import path from "node:path";
import { checkSelection, resolveSelection } from "./data-select.ts";
import { loadFromText, type Loaded } from "./snapshot.ts";

export function loadSnapshotFile(): Loaded {
  const sel = resolveSelection(process.env.STOCKMIND_DATA);
  if (!sel.ok) return { ok: false, error: sel.error };
  let text: string;
  try {
    text = readFileSync(path.join(process.cwd(), "data", sel.file), "utf8");
  } catch (e) {
    return { ok: false, error: `cannot read data/${sel.file}: ${e instanceof Error ? e.message : String(e)}` };
  }
  return checkSelection(sel.kind, loadFromText(text));
}
