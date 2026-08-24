# LabMind MVP — Build Progress Memory

This file serves as the single source of truth for the LabMind MVP build progress. It is structured to allow any developer or AI assistant to pick up the build at any moment.

---

## 🏗️ Monorepo Structure

```
Labmind/
├── gateway/          # Python — on-premise gateway (Presidio de-identification)
├── agents/           # Python — LangGraph agent core & ATLAS memory
├── web/              # TypeScript — Next.js 15 App Router dashboard
├── simulator/        # Python — LIS synthetic event simulator
├── infra/            # Docker Compose environment
└── memory.md         # Active progress tracker (this file)
```

---

## 🔒 Hard Security Constraints (Non-Negotiable)

1. **De-identification Boundary:** Raw PHI (§8.3) must never leave the gateway. Only tokenized, de-identified events are sent to the agent service.
2. **Action Gating:** Worker agents cannot execute side-effects directly. They propose `Action` items which must be authorized by the Action Executor.
3. **Append-Only Auditing:** The `audit_events` table enforces insert-only access at the database level.
4. **Pre-flight LLM Guard:** Every outbound model prompt must be checked for PHI leakage; violation halts the execution immediately.
5. **No Jailed Category Deletions:** Jailed categories (§9.3) cannot be erased under any circumstances.

---

## 📋 Build Step Checklist

### Phase 0 — Skeleton & Foundation
- [x] **Step 0.1:** Project skeleton structure initialized (gateway, agents, web, simulator)
- [x] **Step 0.2:** Docker Compose base config (Postgres + pgvector, Redis, networking)
- [x] **Step 0.3:** Database schemas created (`audit_events` with insert-only rule & chaining)

### Phase 1 — Event Spine & LIS Simulator
- [x] **Step 1.1:** LIS Simulator (synthetic CSV/flat-file event generator)
- [x] **Step 1.2:** On-premise gateway (FastAPI + Microsoft Presidio integration)
- [x] **Step 1.3:** Event pipeline (Redis Streams -> DB consumer, `specimen_state` tracking)
- [x] **Step 1.4:** Web app UI skeleton (Next.js 15 setup, active specimen list layout)

### Phase 2 — ATLAS Context & TAT Monitor
- [x] **Step 2.1:** Context Assembler (Working, Episodic with pgvector, Semantic retrieval)
- [x] **Step 2.2:** Agent orchestration base (LangGraph nodes, Action Executor, stage gating)
- [x] **Step 2.3:** TAT Monitor Worker agent (Claude Haiku reasoning, expected sign-out alerts)
- [x] **Step 2.4:** Action approval dashboard (SUGGEST queue, accept/dismiss actions, audit triggers)

### Phase 3 — Safety Worker & Supervisor Chat
- [x] **Step 3.1:** Critical Value Router agent (panic value detection, loop ack, jailed logging)
- [x] **Step 3.2:** Workflow Manager agent (delegation and routing logic)
- [x] **Step 3.3:** Supervisor Agent (Claude Sonnet chat interface, read-only queries)
- [x] **Step 3.4:** Real-time frontend updates (SSE connection from agents API to Next.js)

### Phase 4 — Governance & Final Verification
- [x] **Step 4.1:** Audit log viewer dashboard (tamper-evident hash validation UI)
- [x] **Step 4.2:** Admin erasure controls (with jail/retention validation)
- [x] **Step 4.3:** Graceful degradation logic (offline fallback mock in web UI)
- [x] **Step 4.4:** Complete MVP verification (execution of definition of done checklist)

---

## 🎯 Current Status

- **Active Step:** None (All build steps completed)
- **Status:** Completed
- **Next Action:** Walk through running the application stack with the user.
