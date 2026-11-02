# LabMind ATLAS

### [Open the Live Application →](https://abusuraihsakhri.github.io/labmind-atlas/)

Laboratory workflow monitoring and governance prototype. LabMind is designed as an **additive read-layer** alongside an existing Laboratory Information System (LIS); it does not replace the LIS.

**Project stage:** research/MVP prototype. **Not clinically validated, not for patient care.** The static browser demonstration uses only invented specimens. It is not connected to a live laboratory or to the Python agent service.

## Explore the browser demonstration

The [live demonstration](https://abusuraihsakhri.github.io/labmind-atlas/) is a dependency-free static application maintained in [`docs/`](docs/). GitHub Actions publishes it to GitHub Pages and checks the deployed HTML, JavaScript and CSS URLs.

The browser demonstration supports:

- A synthetic specimen tracker with illustrative TAT risk indicators.
- Simulated TAT breaches, critical-value flags, and specimen sign-out.
- OBSERVE / SUGGEST trust stages, with no autonomous action execution.
- Local human approval/dismissal and critical-value acknowledgement.
- An ephemeral event timeline and CSV export.

**All demo calculations and decisions are illustrative.** The page does not execute Python, access an LIS, transmit clinical information, contact clinicians, or persist data to a server. Its audit timeline is **not** a cryptographically secured clinical audit log.

## Prototype system

| Component | Technology | Purpose |
| --- | --- | --- |
| On-prem gateway | Python, FastAPI, Presidio, SQLite/Fernet | Event ingestion, identifier tokenization and de-identification boundary |
| Agent service | Python, FastAPI, LangChain/LangGraph | TAT worker, critical-value worker, workflow manager, supervisor |
| Context and records | PostgreSQL/pgvector, Redis | Specimen state, events, memory and audit records |
| Dashboard | Next.js 16, React 19, TypeScript | Authenticated monitoring, action review and governance |
| Simulator | Python | Generate synthetic laboratory event streams |
| Static demo | HTML, CSS, ES modules | Public explanation and interactive sandbox without infrastructure |

The platform design, non-negotiable safety constraints, planned features and MVP scope are described in [`Labmind_spec.md`](Labmind_spec.md). **Those design goals are not claims of achieved clinical or security certification.**

## Local development (backend + web)

Prerequisites: Docker Engine with Compose, adequate RAM/storage for selected local inference models, and network access to obtain dependencies/models. Next.js development outside Docker requires **Node.js 22**.

1. Copy `.env.example` to `.env`.
2. Replace every placeholder with a strong, independent secret. Set `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, gateway/Fernet keys, `AUDIT_SECRET_KEY`, `TOKEN_SALT`, and the Tier 2/Tier 3/service credentials.
3. Configure **`DASHBOARD_SESSION_SECRET`** (at least 32 characters), **`DASHBOARD_TIER2_PASSWORD`** and **`DASHBOARD_TIER3_PASSWORD`** (at least 16 characters each). They must not be copied from the backend bearer tokens.
4. Choose `LLM_PROVIDER` and configure the chosen local/external model endpoint. In Docker, host-based Ollama endpoints typically require `http://host.docker.internal:11434`, not `localhost`.
5. Run:

```bash
docker compose -f infra/docker-compose.yml up --build
```

The dashboard binds to `http://localhost:3000`; API and database ports are bound to localhost in the supplied Compose configuration. Sign in with the configured dashboard password for the appropriate tier. Tier 3 is required for governance actions. **Do not expose the service publicly without HTTPS, an identity provider/MFA, rate limits, network segmentation and a separate security assessment.**

For the standalone browser demo without Docker, serve `docs/` with any static HTTP server, e.g.:

```bash
python -m http.server 8080 --directory docs
```

Then open `http://localhost:8080`.

## Verification

- Browser demonstration: `node --test docs/tests/engine.test.mjs` (Node.js 22).
- Web: from `web/`, run `npm ci`, `npm run lint`, `npx tsc --noEmit`, and `npm run build`.
- Python: `python -m compileall -q gateway agents simulator`; the repository also contains Pytest suites under `agents/tests/` and `gateway/tests/`.
- CI: [GitHub Actions](.github/workflows/ci.yml) checks lint, web build, Python syntax, demo behavior and Docker builds. Full integrated backend testing requires a configured PostgreSQL/Redis/model environment.

## Data handling and limitations

The gateway is designed to tokenize direct identifiers and de-identify free text before agent processing. **Automated de-identification and the outbound pattern guard cannot guarantee that all PHI is removed.** Do not submit real clinical data without institutional privacy review, documented validation and appropriate technical controls.

The deployed web dashboard uses a signed, HTTP-only session tied to a server-configured Tier 2 or Tier 3 password; it is not a full hospital identity and authorization system. For production use, integrate an approved SSO/MFA provider with attributable per-user audit trails and login rate limiting.

The current code is a prototype. Clinical critical-value thresholds, response times, notification delivery, laboratory-specific TAT rules, model output and the audit subsystem require independent validation before clinical deployment. High-priority work remains on [critical-value routing safety](https://github.com/abusuraihsakhri/labmind-atlas/issues/2) and [stream processing reliability](https://github.com/abusuraihsakhri/labmind-atlas/issues/3).

## Event ingestion integrity — P1 (prototype only)

The agent listener now validates incoming specimen event IDs and timezone-aware
timestamps, commits the event, ordered specimen projection and a unique pending
workflow-outbox record in one PostgreSQL transaction, then acknowledges the
Redis Stream ID **only after commit**. Replay is idempotent by source event ID
and conflicting ID reuse raises an error. Older or equal-timestamp events are
preserved as history but do not regress the latest specimen status. Gateway
`received_at` is excluded from replay identity because the gateway may set a
new reception timestamp for the same submitted LIS event.

**Important functional limitation:** This P1 change intentionally pauses
downstream TAT/critical workflow execution. Jobs are persisted in
`workflow_outbox` with status `pending`; no dispatcher has been installed
yet. The next remediation must implement idempotent outbox execution, Redis
pending-entry reclamation, bounded retries and dead-letter handling. Failed
ingestion stays unacknowledged, but P1 alone does **not** recover previously
pending Redis entries. Do not use this implementation for clinical workflow.

Before starting a database that has been initialized under the original
Compose schema, apply the new migration. Back up the database and inspect its
Alembic revision first. The Compose SQL initializer does not create an Alembic
version record. For an existing database known to match the original 001 schema,
baseline it once with `alembic stamp 001_initial`, then apply
`alembic upgrade head`. Do not stamp an unknown schema or run both schema
initializers independently without checking their state. New Compose volumes
receive the outbox table through `infra/init-db/01-init.sql`; migration 002
tolerates that table already existing. An un-migrated service fails closed on
outbox inserts rather than silently acknowledging events.

The CI job `test-event-ingestion-postgres` applies migrations to a fresh
pgvector/PostgreSQL service and runs rollback, ordering, duplicate, conflicting
ID, concurrent-ingestion and acknowledgement boundary tests.

## Event recovery and internal workflow outbox (P2)

The P2 worker reclaims abandoned Redis consumer-group entries using `XAUTOCLAIM`
(30-second minimum idle by default), validates and ingests each record through
the transactional P1 path, and runs a separate durable outbox dispatcher.
Stream messages are acknowledged **only after** their PostgreSQL event
transaction succeeds or a failure is committed to the durable dead-letter
ledger. Invalid/malformed messages and repeated failures use persisted,
exponentially backed-off retries (maximum five attempts). Dead-letter
diagnostics store the Redis entry ID, error *class* and SHA-256 payload digest,
not event bodies. The outbox likewise uses five bounded retries and persists
failed work for operator reconciliation; no automatic reprocessing of
dead-letter work is provided.

Outbox actions use deterministic IDs and complete in the same PostgreSQL
transaction as the outbox status and append-only audit entry. A crash before
commit leaves the job pending without partially committed actions; repeated
workers use row locks to prevent duplicate proposals. Superseded events are
retained but do not create stale proposals. The dispatcher currently performs
**internal TAT risk review and unverified free-text review only**. It does not
invoke language models, create routed critical-value records, contact
clinicians, or send email/SMS. Free-text review matches are not clinically
validated critical results. No external critical-value routing is authorized.

Existing databases must be backed up and migrated through
`003_retry_recovery` before starting the agents. The existing Compose
SQL initializer creates the fresh-volume schema only. The backend remains a
research prototype with **no clinical-use authorization**. Governance,
structured panic thresholds, attributable human approvals and acknowledged
delivery remain outstanding under issue #2.

CI exercises PostgreSQL and Redis crash/retry/dead-letter scenarios in
`test-event-ingestion-postgres`. No clinical deployment is implied by
passing software tests.

## Browser compatibility and license

The static demo targets current evergreen browsers supporting JavaScript ES modules and Blob downloads. The full dashboard requires JavaScript and a compatible Next.js backend.

No `LICENSE` file is included. Public availability of source code does not grant an open-source license; the repository owner should add an explicit license before permitting reuse.
