import { createInitialState, riskOf, injectTatBreach, injectCriticalValue, signOutSpecimen, changeStage, decideAction, acknowledgeAlert, exportAuditCsv } from "./engine.mjs";

let state = createInitialState();
const el = (id) => document.getElementById(id);
const node = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = String(text);
  if (className) item.className = className;
  return item;
};
function formattedTime(dateString) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(dateString));
}
function queueButton(label, action, id) {
  const button = node("button", label);
  button.type = "button";
  button.dataset.action = action;
  button.dataset.id = String(id);
  return button;
}
function empty(label) { return node("div", label, "empty"); }

function renderSpecimens(now) {
  const rows = state.specimens.map(s => {
    const tr = node("tr");
    const tokenTd = node("td");
    tokenTd.append(node("span", s.token, "token"), node("span", s.test, "cell-detail"));
    const statusTd = node("td");
    statusTd.append(node("span", s.status.replaceAll("_", " "), "status-tag"));
    const dueTd = node("td", formattedTime(s.expectedAt));
    const risk = riskOf(s, now);
    const riskTd = node("td");
    riskTd.append(node("span", risk === "complete" ? "COMPLETE" : risk.toUpperCase(), "risk " + risk));
    tr.append(tokenTd, statusTd, dueTd, riskTd);
    return tr;
  });
  el("specimen-rows").replaceChildren(...rows);
}
function renderActions() {
  const pending = state.actions.filter(a => a.status === "pending");
  const container = el("action-list");
  if (!pending.length) {
    container.replaceChildren(empty(state.stage === "OBSERVE" ? "OBSERVE stage: no action proposals are created." : "No pending actions. Inject an event to create a proposal."));
    return;
  }
  const cards = pending.map(a => {
    const div = node("article", undefined, "queue-item");
    const heading = node("div", undefined, "queue-head");
    heading.append(node("strong", a.type.replaceAll("_", " ")), node("span", a.token, "token"));
    const buttons = node("div", undefined, "queue-buttons");
    buttons.append(queueButton("Approve locally", "approve", a.id), queueButton("Dismiss", "dismiss", a.id));
    div.append(heading, node("p", a.explanation), buttons);
    return div;
  });
  container.replaceChildren(...cards);
}
function renderAlerts() {
  const open = state.alerts.filter(a => !a.acknowledged);
  const cards = open.map(a => {
    const div = node("article", undefined, "queue-item");
    const heading = node("div", undefined, "queue-head");
    heading.append(node("strong", a.summary), node("span", a.token, "token"));
    const buttons = node("div", undefined, "queue-buttons");
    buttons.append(queueButton("Acknowledge locally", "ack", a.id));
    div.append(heading, node("p", "Demonstration only: no message has been routed to a clinician."), buttons);
    return div;
  });
  el("alert-list").replaceChildren(...(cards.length ? cards : [empty("No unacknowledged synthetic alerts.")]));
}
function renderAudit() {
  const items = state.audit.slice(0, 20).map(event => {
    const li = node("li");
    li.append(node("strong", event.event.replaceAll("_", " ")), node("span", " — " + event.detail));
    const time = node("time", new Date(event.at).toLocaleString());
    time.dateTime = event.at;
    li.append(time);
    return li;
  });
  el("audit-list").replaceChildren(...items);
}
function render() {
  const now = Date.now();
  el("metric-specimens").textContent = String(state.specimens.length);
  el("metric-risk").textContent = String(state.specimens.filter(s => ["yellow", "red"].includes(riskOf(s, now))).length);
  el("metric-actions").textContent = String(state.actions.filter(a => a.status === "pending").length);
  el("metric-critical").textContent = String(state.alerts.filter(a => !a.acknowledged).length);
  for (const stage of ["OBSERVE", "SUGGEST"]) {
    const button = el(stage.toLowerCase());
    button.setAttribute("aria-pressed", String(state.stage === stage));
  }
  el("stage-message").textContent = state.stage + " stage";
  renderSpecimens(now);
  renderActions();
  renderAlerts();
  renderAudit();
}
function act(fn, messageOk, messageNo = "The scenario has already been applied.") {
  el("feedback").textContent = fn(state, Date.now()) ? messageOk : messageNo;
  render();
}
el("observe").addEventListener("click", () => act(s => changeStage(s, "OBSERVE"), "OBSERVE stage: new proposals are disabled."));
el("suggest").addEventListener("click", () => act(s => changeStage(s, "SUGGEST"), "SUGGEST stage: proposed actions require human review."));
el("inject-delay").addEventListener("click", () => act(injectTatBreach, "Synthetic TAT breach recorded."));
el("inject-critical").addEventListener("click", () => act(injectCriticalValue, "Synthetic critical value recorded; acknowledgement required.", "An unacknowledged synthetic alert is already open."));
el("advance-specimen").addEventListener("click", () => act(signOutSpecimen, "Synthetic specimen marked SIGNED_OUT."));
el("reset").addEventListener("click", () => {state = createInitialState(); el("feedback").textContent = "Synthetic sandbox reset."; render();});
el("action-list").addEventListener("click", e => {
  const target = e.target.closest("button[data-action]");
  if (!target) return;
  const status = target.dataset.action === "approve" ? "approved" : "dismissed";
  act(s => decideAction(s, target.dataset.id, status), "Synthetic action " + status + "; no external action was performed.", "This action can no longer be changed.");
});
el("alert-list").addEventListener("click", e => {
  const target = e.target.closest("button[data-action=ack]");
  if (!target) return;
  act(s => acknowledgeAlert(s, target.dataset.id), "Synthetic critical alert acknowledged.", "Alert has already been acknowledged.");
});
el("download-audit").addEventListener("click", () => {
  const blob = new Blob([exportAuditCsv(state)], {type:"text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "labmind-synthetic-audit.csv";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  el("feedback").textContent = "Synthetic event trail exported. It is not a cryptographic audit record.";
});
render();
