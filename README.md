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

## Browser compatibility and license

The static demo targets current evergreen browsers supporting JavaScript ES modules and Blob downloads. The full dashboard requires JavaScript and a compatible Next.js backend.

No `LICENSE` file is included. Public availability of source code does not grant an open-source license; the repository owner should add an explicit license before permitting reuse.
