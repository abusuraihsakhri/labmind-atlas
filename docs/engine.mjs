// All state in this module is synthetic and ephemeral. There is no backend or patient data.
export const STAGES = Object.freeze(["OBSERVE", "SUGGEST"]);
const stamp = (now) => new Date(now).toISOString();
const specimen = (token, test, status, minutesToDue, now) => ({
  token, test, status, expectedAt: stamp(now + minutesToDue * 60000)
});
export function createInitialState(now = Date.now()) {
  return {
    stage: "SUGGEST",
    specimens: [
      specimen("SYN-2401", "Histopathology", "PROCESSING", 210, now),
      specimen("SYN-2402", "Clinical chemistry", "PROCESSING", 8, now),
      specimen("SYN-2403", "Hematology", "ACCESSIONED", 55, now),
      specimen("SYN-2404", "Cytology", "SIGNED_OUT", -30, now)
    ],
    actions: [],
    alerts: [],
    audit: [{ id: 1, at: stamp(now), event: "SANDBOX_INITIALIZED", detail: "Synthetic workflow loaded" }],
    counter: 1
  };
}
export function riskOf(s, now = Date.now()) {
  if (s.status === "SIGNED_OUT") return "complete";
  const minutesRemaining = (Date.parse(s.expectedAt) - now) / 60000;
  if (minutesRemaining < 0) return "red";
  if (minutesRemaining <= 15) return "yellow";
  return "green";
}
export function record(state, event, detail, now = Date.now()) {
  state.counter += 1;
  state.audit.unshift({ id: state.counter, at: stamp(now), event, detail });
}
const findSpecimen = (state, token) => state.specimens.find(s => s.token === token);
function propose(state, type, token, explanation, now) {
  if (state.stage !== "SUGGEST") return;
  if (state.actions.some(a => a.type === type && a.token === token && a.status === "pending")) return;
  state.counter += 1;
  const action = { id: state.counter, type, token, explanation, status: "pending" };
  state.actions.unshift(action);
  record(state, "ACTION_PROPOSED", type + " for " + token + " (human review required)", now);
}
export function injectTatBreach(state, now = Date.now()) {
  const s = findSpecimen(state, "SYN-2403");
  if (!s || s.status === "SIGNED_OUT") return false;
  s.expectedAt = stamp(now - 21 * 60000);
  record(state, "TAT_BREACH_SIMULATED", s.token + " crossed its illustrative TAT target", now);
  propose(state, "TAT_DELAY_ALERT", s.token, "Illustrative sign-out target exceeded. Review the specimen workflow.", now);
  return true;
}
export function injectCriticalValue(state, now = Date.now()) {
  const token = "SYN-2402";
  if (state.alerts.some(a => a.token === token && !a.acknowledged)) return false;
  state.counter += 1;
  const alert = { id: state.counter, token, summary: "Synthetic critical chemistry result", acknowledged: false };
  state.alerts.unshift(alert);
  record(state, "CRITICAL_VALUE_SIMULATED", token + " requires a human acknowledgement", now);
  propose(state, "ROUTE_CRITICAL_ALERT", token, "A synthetic critical-value flag was detected. Review required.", now);
  return true;
}
export function signOutSpecimen(state, now = Date.now()) {
  const s = findSpecimen(state, "SYN-2401");
  if (!s || s.status === "SIGNED_OUT") return false;
  s.status = "SIGNED_OUT";
  record(state, "SPECIMEN_SIGNED_OUT", s.token + " was marked signed out in simulation", now);
  return true;
}
export function changeStage(state, stage, now = Date.now()) {
  if (!STAGES.includes(stage)) throw new Error("Invalid trust stage");
  if (state.stage === stage) return false;
  state.stage = stage;
  if (stage === "OBSERVE") {
    const pending = state.actions.filter(a => a.status === "pending");
    for (const action of pending) action.status = "withdrawn";
    if (pending.length) record(state, "PENDING_ACTIONS_WITHDRAWN", pending.length + " pending proposals withdrawn", now);
  }
  record(state, "TRUST_STAGE_CHANGED", "Sandbox trust stage set to " + stage, now);
  return true;
}
export function decideAction(state, id, decision, now = Date.now()) {
  if (!["approved", "dismissed"].includes(decision)) return false;
  if (state.stage !== "SUGGEST") return false;
  const action = state.actions.find(a => a.id === Number(id));
  if (!action || action.status !== "pending") return false;
  action.status = decision;
  record(state, "ACTION_" + decision.toUpperCase(), action.type + " for " + action.token + " (simulation only; no external action)", now);
  return true;
}
export function acknowledgeAlert(state, id, now = Date.now()) {
  const alert = state.alerts.find(a => a.id === Number(id));
  if (!alert || alert.acknowledged) return false;
  alert.acknowledged = true;
  record(state, "CRITICAL_VALUE_ACKNOWLEDGED", "Synthetic alert for " + alert.token + " acknowledged", now);
  return true;
}
export function csvCell(value) {
  let s = String(value ?? "");
  // Treat CSV fields beginning with spreadsheet-formula prefixes as literal text.
  if (/^[=+@\-\t\r]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
export function exportAuditCsv(state) {
  const rows = [["id", "timestamp_utc", "event", "detail"], ...state.audit.map(a => [a.id, a.at, a.event, a.detail])];
  return rows.map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
