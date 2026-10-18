import test from "node:test";
import assert from "node:assert/strict";
import { createInitialState, riskOf, injectTatBreach, injectCriticalValue, signOutSpecimen, changeStage, decideAction, acknowledgeAlert, exportAuditCsv, csvCell } from "../engine.mjs";

const now = Date.parse("2026-01-01T12:00:00Z");
test("risk thresholds and completed specimens are deterministic", () => {
  const s = createInitialState(now);
  assert.deepEqual(s.specimens.map(x => riskOf(x, now)), ["green", "yellow", "green", "complete"]);
  assert.equal(riskOf(s.specimens[1], now + 9*60000), "red");
});
test("OBSERVE stage cannot produce approval proposals", () => {
  const s = createInitialState(now);
  changeStage(s, "OBSERVE", now);
  assert.equal(injectTatBreach(s, now), true);
  assert.equal(injectCriticalValue(s, now), true);
  assert.equal(s.actions.length, 0);
  assert.equal(s.alerts.length, 1);
});
test("SUGGEST creates one proposal and supports human decision", () => {
  const s = createInitialState(now);
  injectTatBreach(s, now);
  injectTatBreach(s, now);
  assert.equal(s.actions.length, 1);
  const id = s.actions[0].id;
  assert.equal(decideAction(s, id, "approved", now), true);
  assert.equal(decideAction(s, id, "approved", now), false);
  assert.equal(s.actions[0].status, "approved");
});
test("switching to OBSERVE withdraws pending proposals", () => {
  const s = createInitialState(now);
  injectTatBreach(s, now);
  changeStage(s, "OBSERVE", now);
  assert.equal(s.actions[0].status, "withdrawn");
  assert.equal(decideAction(s, s.actions[0].id, "approved", now), false);
});
test("critical flags and acknowledgement are separate and idempotent", () => {
  const s = createInitialState(now);
  assert.equal(injectCriticalValue(s, now), true);
  assert.equal(injectCriticalValue(s, now), false);
  assert.equal(s.alerts.length, 1);
  assert.equal(acknowledgeAlert(s, s.alerts[0].id, now), true);
  assert.equal(acknowledgeAlert(s, s.alerts[0].id, now), false);
});
test("signout and safe CSV export", () => {
  const s = createInitialState(now);
  assert.equal(signOutSpecimen(s, now), true);
  assert.equal(signOutSpecimen(s, now), false);
  assert.equal(riskOf(s.specimens[0], now), "complete");
  assert.match(exportAuditCsv(s), /SPECIMEN_SIGNED_OUT/);
  assert.equal(csvCell('=HYPERLINK("a")'), '"\'=HYPERLINK(""a"")"');
});
