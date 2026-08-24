# LabMind — Engineering Build Specification (`spec.md`)

> **Purpose of this document.** This is the build bible for LabMind: an agentic intelligence layer that sits on top of any existing Laboratory Information System (LIS) and reasons across the full specimen‑to‑sign‑out workflow. A developer — or an agentic coding tool such as Claude Code — should be able to read this document and begin building the MVP without further context. It is deliberately opinionated about stack and structure so that the build is unambiguous.

> **Status:** v0.1 — MVP scope. Sections marked `[POST-MVP]` are deferred to later phases and are documented for architectural completeness only. Do not build them first.

---

## 0. Reading guide

- **If you are building the MVP**, read sections 1–9 and 14. Build only what is in the **MVP Cut Line** (section 4).
- **If you are scoping the full system**, read everything.
- **Non‑negotiables** are flagged with 🔒. These are safety, privacy, or compliance constraints. They are not optional, ever, regardless of how much they slow the build.

---

## 1. Product summary

LabMind connects to a lab's existing LIS through a standard interface (HL7 v2, FHIR R4, or a flat‑file fallback), observes the specimen workflow as a stream of events, and runs a hierarchy of AI agents that monitor, reason about, and assist that workflow. A persistent intelligence core (codename **ATLAS**) gives the system memory: it learns each lab's normal behavior and improves over time.

**LabMind never replaces the LIS.** It is additive. It reads events, produces alerts, drafts, and dashboards, and — only with human approval, and only after an earned‑trust period — takes limited autonomous actions.

### Core value, in one sentence per buyer
- **Lab director:** real‑time turnaround‑time (TAT) visibility and automatic bottleneck flagging.
- **Pathologist / senior tech:** pre‑populated report shells and protocol checks that cut clerical load.
- **Hospital / chain administrator:** fewer diagnostic errors, audit‑ready compliance documentation, lower cost per test.

---

## 2. Architectural principles (🔒 binding)

1. **🔒 Read‑layer first.** LabMind does not store raw Protected Health Information (PHI) on its own servers. PHI stays inside the hospital's infrastructure. The cloud reasoning layer operates on de‑identified event metadata only. (See section 8.)
2. **🔒 Non‑destructive by default.** No agent writes back to the LIS or takes an irreversible action without either (a) explicit human approval, or (b) a high‑confidence autonomous permission that was earned through the staged trust model and is individually revocable. (See section 6.4.)
3. **🔒 Human in the loop for patient‑safety events.** Critical value routing, even when automated, always produces an acknowledgement loop with a human and is logged immutably.
4. **Everything is logged.** Every agent decision is timestamped, attributable, and written to an append‑only audit store. (See section 9.)
5. **Lab‑specific learning stays on‑premise.** The model that makes a given lab's ATLAS unique never leaves that lab's infrastructure. Only de‑identified, differentially‑private gradient updates may (with opt‑in) join the federated network. `[POST-MVP]`
6. **Fail safe, not silent.** If the cloud reasoning layer is unreachable, the system degrades to a local read‑only monitoring mode and surfaces that state to the user. It never blocks the lab's own workflow.

---

## 3. System context (C4 level 1)

```
                ┌─────────────────────────────────────────────┐
                │           HOSPITAL / LAB NETWORK             │
                │                                              │
  ┌──────────┐  │  ┌───────────┐      ┌────────────────────┐  │
  │  LIS/HIS │──┼─▶│  LabMind  │─────▶│  On-Prem Gateway   │  │
  │ (Cerner, │  │  │  Adapter  │ HL7/ │  - PHI tokenizer   │  │
  │ Meditech,│◀─┼──│ (inbound) │ FHIR │  - local event bus │  │
  │ custom)  │  │  └───────────┘      │  - local cache     │  │
  └──────────┘  │                     └─────────┬──────────┘  │
                │                               │ de-identified │
                └───────────────────────────────┼──────────────┘
                                                 │ TLS 1.3
                                                 ▼
                        ┌────────────────────────────────────┐
                        │        LABMIND CLOUD (or VPC)        │
                        │  ┌────────┐  ┌────────┐  ┌────────┐  │
                        │  │Supervis│  │Managers│  │Workers │  │
                        │  │  Agent │─▶│ (x3)   │─▶│ (x6)   │  │
                        │  └────────┘  └────────┘  └────────┘  │
                        │        ▲          │          │       │
                        │        └──────────┴──────────┘       │
                        │             ATLAS core               │
                        │   (5 memory types, learning loop)    │
                        │  ┌──────────┐ ┌────────┐ ┌────────┐  │
                        │  │ Postgres │ │ Redis  │ │ Neo4j  │  │
                        │  │ +pgvector│ │ streams│ │ (KG)   │  │
                        │  └──────────┘ └────────┘ └────────┘  │
                        └────────────────────────────────────┘
                                         │
                                         ▼
                            ┌─────────────────────────┐
                            │  Web app (Next.js)      │
                            │  - Supervisor chat      │
                            │  - TAT dashboard        │
                            │  - Alerts & approvals   │
                            │  - Audit / governance   │
                            └─────────────────────────┘
```

**Deployment note.** For the MVP and most customers, the "LabMind Cloud" block runs as a **single‑tenant instance inside the country's sovereign cloud region** (e.g. Azure UAE North, AWS Bahrain/Mumbai) — not a shared multi‑tenant SaaS. This is what makes the data‑residency story true rather than aspirational.

---

## 4. The MVP cut line

Build this, and only this, for v0.1. Resist scope creep. The goal of the MVP is a **convincing, demoable, single‑lab deployment of two worker agents plus the dashboard and audit trail**, proving the read‑layer architecture end to end.

### In scope for MVP
- ✅ LabMind Adapter with **one** inbound interface: HL7 v2 ADT/ORM/ORU **or** a CSV/flat‑file simulator (build the simulator first — see §13).
- ✅ On‑prem gateway service with **PHI tokenization** (🔒 the de‑identification boundary must be real, even in the MVP).
- ✅ ATLAS with **three** memory types implemented for real: **working** (Redis), **episodic** (Postgres + pgvector), **semantic** (start as Postgres tables; Neo4j is post‑MVP).
- ✅ **Two** worker agents: **TAT Monitor** and **Critical Value Router**. These two prove the highest‑value, most demoable behaviors.
- ✅ **One** manager agent: **Workflow Manager** (coordinates the two workers).
- ✅ **Supervisor agent** with a natural‑language chat interface (read + ask; no destructive actions).
- ✅ Web dashboard: live specimen list, TAT view, alert feed, approval queue.
- ✅ Append‑only **audit log** with a viewer.
- ✅ The **OBSERVE → SUGGEST** trust stages (see §6.4). MVP stops at SUGGEST; do not ship autonomous ACT.

### Explicitly out of scope for MVP `[POST-MVP]`
- ❌ Federated / collective memory and differential privacy.
- ❌ Procedural memory with reinforcement‑style threshold learning (stub the interface; hard‑code thresholds for now).
- ❌ The four remaining worker agents (Specimen Tracker, Protocol Checker, Report Pre‑populator, Clinician Communicator).
- ❌ The full governed‑erasure protocol with dual‑person integrity (build a *simplified admin‑only erasure with audit logging*; the nine‑step protocol is post‑MVP — but 🔒 even the simplified version must write an immutable audit record and must refuse to erase jailed categories).
- ❌ Air‑gapped deployment mode.
- ❌ FHIR interface (HL7/CSV only for MVP).

---

## 5. Technology stack (opinionated — use these unless there is a hard reason not to)

| Layer | Choice | Notes |
|---|---|---|
| Web app / API | **Next.js 15 (App Router)** + TypeScript | Matches existing team familiarity. Server actions for mutations. |
| Auth | **Supabase Auth** (or Clerk) | RBAC tiers in §6.3. MFA required for Tier 3+. |
| Primary DB | **PostgreSQL 16** | Single source of truth. |
| Vector store | **pgvector** extension on the same Postgres | Episodic memory embeddings. Avoids a separate vector DB for MVP. |
| Embedding Model | **`sentence-transformers/all-MiniLM-L6-v2`** (local) | Runs locally on-premise to preserve data residency compliance. |
| Cache / working memory | **Redis** (Redis Streams) | Real‑time event bus + shift‑scoped working memory. |
| Knowledge graph | **Neo4j** | Semantic memory. `[POST-MVP]` — use Postgres tables in MVP. |
| Agent orchestration | **LangGraph** (Python) | Deterministic, inspectable agent graphs. Each agent is a node. |
| Agent reasoning model | **Claude (Haiku for speed, Sonnet for the Supervisor)** via Anthropic API | Haiku for high‑volume worker reasoning; Sonnet where judgment matters. |
| PHI de‑identification | **Microsoft Presidio** | Runs in the on‑prem gateway only. |
| HL7 parsing | **`hl7apy`** (Python) or **`node-hl7-client`** | Pick one; Python recommended to keep the agent layer in one language. |
| Audit / tracing | **OpenTelemetry** → Postgres append‑only table + optional export | Every agent step is a span. |
| Background jobs | **Celery** (Python) or **Inngest** (TS) | Learning loop, scheduled scans. |
| Infra | **Docker Compose** for local; **Terraform** for cloud | Single‑tenant per customer. |
| Payments (product side) | **Lemon Squeezy** | (Per business preference — not Stripe.) Out of band from the clinical system. |

**Language split:** the **agent/ATLAS core is Python** (LangGraph + Claude + Presidio + hl7apy). The **web app is TypeScript/Next.js**. They communicate over an internal REST/gRPC boundary. Keep the clinical reasoning out of the web tier.

---

## 6. Agent architecture (detailed)

### 6.1 Hierarchy
```
Human (lab director / pathologist)
        │  natural language only
        ▼
   SUPERVISOR AGENT          ← Sonnet; the single human interface
        │  structured task delegation
        ▼
   MANAGER AGENTS            ← one per domain
   • Workflow Manager        ← (MVP)
   • Quality & Safety Mgr    ← [POST-MVP, but Critical Value Router reports here conceptually]
   • Reporting Manager       ← [POST-MVP]
        │  specific instructions
        ▼
   WORKER AGENTS             ← Haiku; do the actual work
   • TAT Monitor             ← (MVP)
   • Critical Value Router   ← (MVP)
   • Specimen Tracker        ← [POST-MVP]
   • Protocol Checker        ← [POST-MVP]
   • Report Pre-populator    ← [POST-MVP]
   • Clinician Communicator  ← [POST-MVP]
```

> **MVP simplification:** in v0.1, the Critical Value Router may report directly to the Workflow Manager so you only build one manager. Keep the code structured so a second manager can be slotted in later.

### 6.2 Agent contract (every agent implements this interface)

```python
class Agent(Protocol):
    name: str
    tier: Literal["supervisor", "manager", "worker"]

    def handle(self, event: Event, context: ContextPacket) -> AgentResult:
        """Pure-ish function: given an event and assembled context,
        decide on zero or more Actions. MUST NOT call the LIS directly;
        emits Action objects that the executor gates."""
        ...

@dataclass
class AgentResult:
    actions: list[Action]          # proposed, not executed
    confidence: float              # 0.0–1.0
    reasoning: str                 # human-readable, stored in audit
    memory_writes: list[MemoryWrite]
```

🔒 **Agents never execute side effects themselves.** They *propose* `Action` objects. A central **Action Executor** decides — based on trust stage, confidence, and permission scope — whether to (a) require human approval, (b) execute autonomously and log, or (c) reject. This single chokepoint is where safety lives.

### 6.3 Privilege tiers (RBAC) (🔒)

| Tier | Role | Can |
|---|---|---|
| 1 Viewer | tech / junior | view dashboards, acknowledge alerts |
| 2 Operator | senior tech / pathologist | accept/dismiss/override suggestions; view episodic summaries |
| 3 Administrator | lab director / IT head | update semantic memory (SOPs), adjust parameters, view full audit, **initiate** erasure request |
| 4 Super Admin | CIO / data‑governance officer | **approve** erasure (dual‑person), manage privileges |
| 5 LabMind Root | LabMind eng | break‑glass only, signed legal instrument, live‑streamed to CIO |

MFA mandatory for Tier 3+. 🔒 No tier can edit the audit log.

### 6.4 Trust / autonomy stages (🔒 staged rollout)

| Stage | When | Agent behavior |
|---|---|---|
| **OBSERVE** | days 1–14 | read‑only; builds baseline; takes **no** actions |
| **SUGGEST** | weeks 3–8 | proposes actions; **every** action requires human accept/dismiss; **MVP STOPS HERE** |
| ACT `[POST-MVP]` | months 3–6 | high‑confidence actions execute autonomously, still logged, still revocable per‑agent |
| OPTIMIZE `[POST-MVP]` | months 6–12 | proactive systemic suggestions |
| EVOLVE `[POST-MVP]` | year 2+ | self‑tunes thresholds within governed bounds |

The Action Executor enforces the current stage. Stage transitions are a Tier‑3 administrative action and are themselves audited.

---

## 7. ATLAS — memory subsystem

### 7.1 Memory types

| Type | Store (MVP) | Persistence | Purpose |
|---|---|---|---|
| **Working** | Redis Streams | shift‑scoped TTL | live state of every specimen now |
| **Episodic** | Postgres + pgvector | 90‑day rolling | what happened, when, outcome; de‑identified |
| **Semantic** | Postgres tables (Neo4j `[POST-MVP]`) | permanent, versioned | SOPs, reference ranges, clinician directory, lab rules |
| Procedural `[POST-MVP]` | Postgres + policy store | continuous | learned execution strategies; threshold tuning |
| Collective `[POST-MVP]` | federated model | monthly sync, opt‑in | cross‑lab anonymized learnings |

### 7.2 Context Assembler (build this early — agents depend on it)
Before any agent runs, ATLAS assembles a `ContextPacket`:
```
ContextPacket = working_memory(specimen) 
              + episodic_recall(similar_events, k=5 via pgvector) 
              + semantic_rules(applicable SOPs, ranges)
```
Target latency < 200 ms. This is the single most reused component; write it first and test it hard.

### 7.3 Learning loop `[POST-MVP]`
Weekly job: harvest episodic memory → evaluate precision/recall per action type → detect drift vs baseline → adjust confidence thresholds → write to procedural memory → generate plain‑language weekly report. **For MVP, thresholds are hard‑coded constants in config; expose them but do not auto‑tune.**

---

## 8. Data & privacy (🔒 the part that must not be cut)

### 8.1 The de‑identification boundary
- PHI **enters** the on‑prem gateway from the LIS.
- The gateway runs **Presidio** to tokenize/strip PHI: patient name, MRN, DOB, clinician name, free‑text that may contain identifiers, insurance/billing fields.
- Only **de‑identified events** (specimen type, test code, timestamps, status transitions, anonymous specimen token, anonymous clinician token) cross TLS 1.3 to the reasoning layer.
- 🔒 **Never logged, never sent to the cloud, never embedded:** the fields listed in §8.3.

### 8.2 Re‑identification
- A re‑identification map (anon token ↔ real MRN) lives **only** in the on‑prem gateway, encrypted at rest (AES‑256), accessible only to the local alert‑delivery component when it must reach a real clinician for a critical value.
- The cloud layer can request "deliver this alert to the clinician for specimen TOKEN_X" — the gateway resolves the identity locally and delivers. The cloud never sees the identity.

### 8.3 🔒 Fields that never leave the hospital
`patient_name, mrn, dob, national_id, clinician_name, raw_report_text, diagnosis_text, insurance_id, billing_data, any free-text not passed through Presidio`

### 8.4 Compliance targets
- **UAE:** ADHICS v2.0 — encrypted authenticated APIs, breach reporting 24–72h, annual audit + quarterly self‑assessment, Malaffi/NABIDH‑compatible interfaces.
- **India:** NABL (ISO 15189:2022) documentation support; DPDPA 2023 erasure compliance.
- **International:** ISO 27001, HIPAA‑ready architecture (BAA‑compatible).
- Encryption: TLS 1.3 in transit, AES‑256 at rest, key management via cloud KMS / HSM.

### 8.5 PHI Outbound Guard (🔒)
- 🔒 **Automated Pre-Flight Guard:** Every outbound prompt sent to Claude/external LLMs must pass through a validation layer.
- If any raw PHI fields from §8.3 or patterns matching MRNs/patient names are detected, the request must fail immediately with a security exception, blocking transmission.

---

## 9. Audit & governance

### 9.1 Audit log (🔒 append‑only)
- Every agent decision, every human approval/override, every stage transition, every config change, every erasure event → one append‑only Postgres table (`audit_events`) with a per‑row hash chaining to the previous row (tamper‑evident).
- 🔒 No API path, no role, can `UPDATE` or `DELETE` from `audit_events`. Enforce at the DB level (revoke update/delete; insert‑only role).

### 9.2 Erasure (MVP = simplified; full protocol `[POST-MVP]`)
**MVP erasure:** Tier‑3 may request erasure of episodic memory in a time range. The system:
1. 🔒 Runs a **jail check** — refuses if the scope intersects jailed categories (§9.3).
2. 🔒 Runs a retention check — refuses if within statutory minimums.
3. Writes an immutable audit record **before** deleting.
4. Cryptographically erases (destroy key, then overwrite).
5. Writes a completion record. 🔒 This record is itself jailed.

**`[POST-MVP]` full protocol** adds: 72‑hour cooling‑off, dual‑person Tier‑4 authorization (two‑key rule), pre‑erasure snapshot to an external regulatory vault, and federated unlearning.

### 9.3 🔒 Jailed categories — never erasable by any tier
`critical_value_routing_logs (10y), all_erasure_records (10y), legal_hold_records (until court release), accreditation_audit_evidence (cycle+2y), privilege_assignment_history (7y), system_integrity_checksums`

---

## 10. API surface (internal, v0.1)

```
# Gateway (on-prem) → Cloud
POST /ingest/event           # de-identified event in
GET  /health

# Cloud agent layer
POST /agents/run             # (internal) run agents for an event
GET  /specimens              # live working-memory view (de-identified)
GET  /specimens/:token       # one specimen's state + episodic recall
GET  /alerts                 # alert feed
POST /alerts/:id/ack         # human acknowledges (critical value loop)
POST /actions/:id/approve    # human approves a proposed action (SUGGEST stage)
POST /actions/:id/dismiss
POST /supervisor/chat        # natural-language query to Supervisor (read-only in MVP)

# Governance
GET  /audit                  # paginated, filterable; read-only
POST /admin/erasure/request  # Tier 3; runs jail+retention checks
GET  /admin/stage            # current trust stage
POST /admin/stage            # Tier 3; transition stage (audited)
```

All mutating endpoints require auth + tier check + write an audit event.

**Real-Time Data Streaming:**
- Server-Sent Events (SSE) stream updates from `/alerts` and `/specimens` directly to the Next.js frontend, driven by Redis Stream subscription events in the agent service.
- Strict Pydantic models in Python act as the single source of truth for schema validation, exported or compiled to TypeScript interface types in the Next.js project.

---

## 11. Data model (core tables, abbreviated)

```sql
-- de-identified specimen event stream (episodic source)
specimen_events(
  id, specimen_token, event_type, test_code, status,
  occurred_at, received_at, anon_clinician_token, meta_jsonb
);

-- working memory snapshot is in Redis; this is the durable mirror
specimen_state(
  specimen_token PRIMARY KEY, current_status, accessioned_at,
  expected_signout_at, tat_risk_level, last_event_at
);

-- episodic embeddings for recall
episodic_memory(
  id, specimen_token, summary_text, embedding vector(1536),
  outcome, occurred_at  -- 90-day rolling purge
);

-- semantic memory (SOPs, ranges) - versioned
semantic_rules(
  id, rule_type, key, value_jsonb, version, valid_from, valid_to
);

-- proposed + executed actions
actions(
  id, agent_name, specimen_token, action_type, payload_jsonb,
  confidence, reasoning, status,  -- proposed|approved|dismissed|executed|rejected
  proposed_at, resolved_at, resolved_by
);

-- 🔒 append-only, hash-chained
audit_events(
  id BIGSERIAL, prev_hash, row_hash, actor, actor_tier,
  event_type, detail_jsonb, created_at
  -- DB role has INSERT only; UPDATE/DELETE revoked
);

-- critical value acknowledgement loop (jailed)
critical_value_events(
  id, specimen_token, value_summary, routed_to_token,
  routed_at, acknowledged_at, acknowledged_by, escalated  -- 10y retention
);
```

---

## 12. Build phases & milestones

**Phase 0 — Skeleton (week 1)**
- Monorepo: `/gateway` (py), `/agents` (py), `/web` (next), `/infra` (compose+tf).
- Docker Compose brings up Postgres+pgvector, Redis, the gateway, the agent service, the web app.
- `audit_events` table with insert‑only role and hash chaining; prove you cannot delete a row.

**Phase 1 — Event spine (week 2)**
- CSV/flat‑file simulator emits realistic specimen events (§13).
- Gateway ingests, runs Presidio, emits de‑identified events to Redis stream.
- `specimen_state` mirror updates; web app shows a live specimen list.

**Phase 2 — Context + first worker (week 3)**
- Context Assembler (working + episodic + semantic).
- TAT Monitor worker: predicts expected sign‑out, raises risk levels, proposes alert actions.
- SUGGEST stage: alerts appear in approval queue; human accept/dismiss; both audited.

**Phase 3 — Safety worker + Supervisor (week 4)**
- Critical Value Router worker: detects panic values, proposes routing, acknowledgement loop, jailed logging.
- Supervisor chat (read‑only): "what's at risk right now?", "show me today's TAT".
- Workflow Manager coordinates the two workers.

**Phase 4 — Governance + polish (week 5)**
- Audit viewer; simplified erasure with jail+retention checks; stage controls.
- Dashboard polish; demo script; seed a believable 2‑week history so ATLAS has episodic memory to recall.

**Demo‑ready target: ~5 weeks** for a single simulated lab. Real HL7 against a real/sandbox LIS is the first post‑demo hardening task.

---

## 13. The LIS simulator (build this first — it unblocks everything)

A small service that replays a realistic stream of specimen events so the whole system can be built and demoed without a live hospital LIS.
- Generate N specimens/day with realistic test mixes (histopath + clinical chemistry + haematology).
- Realistic timestamps, shift patterns, occasional TAT breaches, occasional panic values.
- Inject deliberately identifiable PHI into free‑text fields so you can **prove Presidio strips it**.
- Output either HL7 v2 messages or CSV rows (config flag), so the same simulator validates both interfaces over time.

🔒 The simulator must contain **only synthetic data**. Never seed it with real patient records.

---

## 14. Definition of done for the MVP

- [ ] A simulated lab runs for a "two‑week" seeded history; ATLAS has episodic memory.
- [ ] TAT Monitor raises a correct early warning on a breaching specimen; it appears in the approval queue; a human accepts; the decision is in the audit log.
- [ ] Critical Value Router detects a panic value, proposes routing, a human acknowledges, and the event is written to the jailed `critical_value_events` table.
- [ ] Supervisor answers "what is at risk right now?" correctly from working memory.
- [ ] 🔒 A scripted attempt to send PHI to the cloud fails — the event captured in the cloud layer contains **no** §8.3 fields.
- [ ] 🔒 A scripted attempt to `DELETE` from `audit_events` fails at the DB level.
- [ ] 🔒 An erasure request that intersects a jailed category is refused, with the refusal audited.
- [ ] The system degrades to local read‑only when the cloud reasoning endpoint is unreachable, and says so in the UI.

---

## 15. Open decisions (resolve before/early in build)

1. **Primary inbound interface for the first real customer:** HL7 v2 vs FHIR vs flat‑file. (Likely dictated by the pilot lab's LIS.)
2. **Episodic retention window:** 90 days is the default; confirm against the pilot's regulatory context.
3. **Where the Anthropic API calls run:** ensure the reasoning calls only ever receive de‑identified payloads; add a guard that asserts no §8.3 field is present in any outbound model prompt. 🔒
4. **Single‑tenant region** for the pilot (Azure UAE North vs AWS Mumbai/Bahrain).
5. **Co‑founder / engineering ownership:** who owns the Python agent core vs the Next.js app long‑term.

---

## 16. What this is NOT (anti‑scope)

LabMind is **not** a diagnostic AI. It does not interpret slides, make diagnoses, or replace the pathologist's judgment. It is a **workflow and governance intelligence layer**. Any feature drifting toward autonomous clinical diagnosis is out of scope and carries regulatory burdens (medical‑device classification) that are deliberately avoided in this product. 🔒 Keep LabMind on the workflow side of that line.

---

*End of `spec.md` v0.1. Build the simulator, then the audit spine, then the context assembler, then the two workers. Everything else follows.*
