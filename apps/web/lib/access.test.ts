import assert from "node:assert/strict";
import { test } from "node:test";

import { decideAccess, MIN_PASSWORD_LENGTH, parseBasic, safeEqual } from "./access.ts";
import { checkSelection, resolveSelection } from "./data-select.ts";
import { loadFromText } from "./snapshot.ts";
import { readFileSync } from "node:fs";

const basic = (u: string, p: string) => "Basic " + Buffer.from(`${u}:${p}`).toString("base64");
const PW = "correct-horse-battery";

test("market data can NEVER be served without a strong password (fails closed)", () => {
  for (const pw of [undefined, "", "short", "elevenchars"]) {
    const d = decideAccess({ authorization: null, dataMode: "market", user: undefined, password: pw });
    assert.equal(d.action, "misconfigured", String(pw));
    if (d.action === "misconfigured") assert.match(d.reason, pw ? /at least 12 characters/ : /must be set/, `reason for ${String(pw)}`);   // the operator gets the RIGHT diagnosis
  }
  assert.equal("elevenchars".length, MIN_PASSWORD_LENGTH - 1);
  assert.equal(decideAccess({ authorization: null, dataMode: " MARKET ", user: undefined, password: undefined }).action, "misconfigured");   // case/space tolerant
  assert.equal(decideAccess({ authorization: null, dataMode: "market", user: undefined, password: PW }).action, "challenge");
});

test("demo data is public unless a password is set; with a password it is enforced", () => {
  for (const mode of [undefined, "", "demo"]) assert.equal(decideAccess({ authorization: null, dataMode: mode, user: undefined, password: undefined }).action, "allow");
  assert.equal(decideAccess({ authorization: null, dataMode: "demo", user: undefined, password: PW }).action, "challenge");
});

test("credential checking", () => {
  const ok = { dataMode: "market", user: undefined, password: PW };
  assert.equal(decideAccess({ ...ok, authorization: basic("stockmind", PW) }).action, "allow");          // default user
  assert.equal(decideAccess({ ...ok, user: "jaime", authorization: basic("jaime", PW) }).action, "allow");
  assert.equal(decideAccess({ ...ok, user: "jaime", authorization: basic("stockmind", PW) }).action, "challenge");
  for (const bad of [basic("stockmind", "wrong-password-x"), basic("stockmind", PW + "x"), basic("stockmind", PW.slice(0, -1)), basic("", ""), basic("stockmind", ""),
                     "Basic", "Basic !!!notbase64!!!", "Bearer abc", "basic " + Buffer.from("nocolon").toString("base64"), null, ""]) {
    assert.equal(decideAccess({ ...ok, authorization: bad }).action, "challenge", String(bad));
  }
  assert.equal(decideAccess({ ...ok, authorization: basic("stockmind", "pässwörd-ünïcode-ok") }).action, "challenge");
  assert.equal(decideAccess({ ...ok, password: "pässwörd-ünïcode-ok", authorization: basic("stockmind", "pässwörd-ünïcode-ok") }).action, "allow");
  assert.equal(decideAccess({ ...ok, password: "pass:with:colons-123", authorization: basic("stockmind", "pass:with:colons-123") }).action, "allow");   // only the first colon splits
});

test("safeEqual / parseBasic primitives", () => {
  assert.ok(safeEqual("abc", "abc") && safeEqual("", ""));
  assert.ok(!safeEqual("abc", "abd") && !safeEqual("abc", "abcd") && !safeEqual("abcd", "abc") && !safeEqual("", "a"));
  assert.deepEqual(parseBasic(basic("u", "p:q")), { user: "u", password: "p:q" });
  assert.equal(parseBasic("Basic"), null);
});

const RAW = readFileSync(new URL("../data/demo-snapshot.json", import.meta.url), "utf8");

test("data selection is explicit; an unknown value is an error, never a silent default to demo", () => {
  assert.deepEqual(resolveSelection(undefined), { ok: true, kind: "demo", file: "demo-snapshot.json" });
  assert.deepEqual(resolveSelection("Market "), { ok: true, kind: "market", file: "market-snapshot.json" });
  for (const bad of ["live", "real", "true", "1", "../market", "demo,market"]) assert.equal(resolveSelection(bad).ok, false, bad);
});

test("a simulated file can never be served as market data (and vice versa)", () => {
  const sim = loadFromText(RAW);
  assert.equal(checkSelection("demo", sim).ok, true);
  const asMarket = checkSelection("market", sim);
  assert.equal(asMarket.ok, false);
  const d = JSON.parse(RAW);
  d.meta.mode = "delayed";
  d.meta.symbols_are_fictional = false;
  const market = loadFromText(JSON.stringify(d));
  assert.equal(market.ok, true);
  assert.equal(checkSelection("market", market).ok, true);
  assert.equal(checkSelection("demo", market).ok, false);
  assert.equal(checkSelection("market", { ok: false, error: "x" }).ok, false);
});

test("the validator rejects a snapshot whose mode and fictional flag disagree, and malformed 'excluded'", () => {
  const mk = (f: (d: any) => void) => { const d = JSON.parse(RAW); f(d); return loadFromText(JSON.stringify(d)); };
  assert.equal(mk((d) => { d.meta.mode = "delayed"; }).ok, false);                                     // real mode but fictional=true
  assert.equal(mk((d) => { d.meta.symbols_are_fictional = false; }).ok, false);                        // simulated mode but fictional=false
  assert.equal(mk((d) => { d.meta.mode = "delayed"; d.meta.symbols_are_fictional = false; d.meta.excluded = [{ symbol: "X", reason: "r" }]; }).ok, true);
  assert.equal(mk((d) => { d.meta.excluded = "nope"; }).ok, false);
  assert.equal(mk((d) => { d.meta.excluded = [{ symbol: "X" }]; }).ok, false);
});
