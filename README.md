# LabMind ATLAS 🧠🔬

<div align="center">

![License](https://img.shields.io/badge/license-Private-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black.svg?logo=next.js&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local_AI-white.svg?logo=ollama&logoColor=black)
![pgvector](https://img.shields.io/badge/pgvector-PostgreSQL_16-336791.svg?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Streams_7-DC382D.svg?logo=redis&logoColor=white)

**ATLAS: Autonomous Turnaround & Laboratory Agent System**

*A privacy-preserving agentic intelligence and workflow supervision layer for Laboratory Information Systems (LIS)*

*100% Air-Gapped / On-Premise Privacy • Zero-PHI Leakage Architecture • Bring Your Own Model (Local Ollama, Claude, OpenAI)*

</div>

---

## 📑 Table of Contents

- [What is LabMind ATLAS?](#-what-is-labmind-atlas)
- [Key Features & Capabilities](#-key-features--capabilities)
- [System Architecture](#-system-architecture)
- [System Requirements](#-system-requirements)
- [OS-Specific Prerequisites](#-os-specific-prerequisites)
  - [🐧 Linux (Ubuntu, Debian, Fedora, RHEL)](#-linux-ubuntu-debian-fedora-rhel)
  - [🍎 macOS (Apple Silicon M1/M2/M3/M4 & Intel)](#-macos-apple-silicon-m1m2m3m4--intel)
  - [🪟 Windows (WSL2 / PowerShell)](#-windows-wsl2--powershell)
- [Quick Start with Docker (Recommended)](#-quick-start-with-docker-recommended)
- [Local Air-Gapped AI Setup with Ollama](#-local-air-gapped-ai-setup-with-ollama)
- [Bare-Metal Local Development Setup](#-bare-metal-local-development-setup)
- [Bring Your Own Model (BYOM) Configuration](#-bring-your-own-model-byom-configuration)
- [Environment Variables Reference](#-environment-variables-reference)
- [ATLAS Agent Hierarchy & Mechanics](#-atlas-agent-hierarchy--mechanics)
- [Dashboard Walkthrough & Web Interface](#-dashboard-walkthrough--web-interface)
- [API Reference](#-api-reference)
- [Testing & Quality Verification](#-testing--quality-verification)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [Project Directory Structure](#-project-directory-structure)
- [License](#-license)

---

## 📖 What is LabMind ATLAS?

**ATLAS** (**A**utonomous **T**urnaround & **L**aboratory **A**gent **S**ystem) is a healthcare-grade, on-premises agentic monitoring layer designed for clinical pathology, hematology, and clinical chemistry laboratories.

Sitting seamlessly alongside a hospital's existing **Laboratory Information System (LIS)** via HL7 v2, FHIR R4, or synthetic event pipelines, ATLAS observes specimen lifecycles from accessioning to final sign-out. A persistent memory engine and a hierarchy of specialized AI agents work together to:
1. **Forecast Turnaround Time (TAT) Breaches:** Detect potential delays before statutory or clinical SLA thresholds are crossed.
2. **Intercept Critical / Panic Values:** Detect dangerous diagnostic thresholds (e.g. panic potassium, severe thrombocytopenia, frozen-section malignancies) and trigger jailed alert escalations.
3. **Provide Supervisor Operations Chat:** Give lab managers and pathologists instant natural-language insights over active lab bottlenecks without exposing raw patient data.

---

## ✨ Key Features & Capabilities

- 🔒 **Zero-PHI De-Identification Boundary:** Microsoft Presidio strips patient names, MRNs, phone numbers, and free-text demographics at the on-premise gateway. Deterministic HMAC tokens replace all real-world identifiers.
- 🦙 **100% Air-Gapped Local AI (Ollama Support):** Run completely offline on hospital infrastructure using local open models (`llama3.2`, `mistral`, `meditron`, `qwen2.5`). No medical data ever leaves the local network.
- 🧠 **Tri-Tier ATLAS Memory Subsystem:**
  - **Working Memory:** High-speed Redis Streams mirroring live specimen states.
  - **Episodic Memory:** PostgreSQL 16 + `pgvector` performing cosine similarity searches against past laboratory episodes.
  - **Semantic Memory:** Versioned Standard Operating Procedures (SOPs), protocol libraries, and instrument reference ranges.
- 🚦 **Staged Autonomy & Action Gating:**
  - **`OBSERVE` Mode:** Read-only mode for audit, baselining, and calibration.
  - **`SUGGEST` Mode:** Proposes actionable clinical interventions into an operator approval queue with calibrated confidence scoring.
- 🛡️ **Cryptographic Append-Only Audit Trail:** Every event, approval, dismissal, and configuration change is chained via HMAC-SHA256 and protected at the database level by PostgreSQL mutation-blocking triggers.

---

## 🏛️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               HOSPITAL / LAB INTRANET                                  │
│                                                                                        │
│  ┌──────────────┐     Raw LIS Events      ┌─────────────────────────────────────────┐  │
│  │ LIS / Feed   │ ──────────────────────▶ │            On-Premise Gateway           │  │
│  │ (HL7 / FHIR) │     (with raw PHI)      │  - Microsoft Presidio De-Identification │  │
│  └──────────────┘                         │  - Fernet-Encrypted Local Token Map DB  │  │
│                                           │  - HMAC Deterministic Token Generator   │  │
│                                           └────────────────────┬────────────────────┘  │
│                                                                │                       │
│                                         De-Identified Events   │ (Zero PHI Boundary)   │
│                                                                ▼                       │
│                                           ┌─────────────────────────────────────────┐  │
│                                           │           Redis Event Stream            │  │
│                                           │       `specimen_events_stream`          │  │
│                                           └────────────────────┬────────────────────┘  │
│                                                                │                       │
│                                                                ▼                       │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                            ATLAS Intelligence Core                               │  │
│  │                                                                                  │  │
│  │  ┌──────────────────┐    Context Assembly    ┌────────────────────────────────┐  │  │
│  │  │ Pipeline Consumer│ ─────────────────────▶ │        ATLAS Memory Core       │  │  │
│  │  └────────┬─────────┘                        │ - Working Memory (Redis)       │  │  │
│  │           │                                  │ - Episodic Recall (pgvector)   │  │  │
│  │           ▼                                  │ - Semantic SOP Rules (Postgres)│  │  │
│  │  ┌────────────────────────────────────────┐  └───────────────┬────────────────┘  │  │
│  │  │           Workflow Manager             │                  │                   │  │
│  │  └────────┬──────────────────────┬────────┘                  │                   │  │
│  │           │                      │                           │                   │  │
│  │           ▼                      ▼                           ▼                   │  │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────────────┐  │  │
│  │  │   TAT Monitor    │   │  Critical Value  │   │     Supervisor AI Agent      │  │  │
│  │  │   Worker Agent   │   │  Router Worker   │   │  - Read-Only Natural Query   │  │  │
│  │  └────────┬─────────┘   └────────┬─────────┘   │  - Context Aware Assistance  │  │  │
│  │           │                      │             └──────────────┬───────────────┘  │  │
│  │           └──────────┬───────────┘                            │                  │  │
│  │                      ▼                                        │                  │  │
│  │          ┌───────────────────────┐                            │                  │  │
│  │          │    Action Executor    │                            │                  │  │
│  │          │ - Trust Stage Gating  │                            │                  │  │
│  │          │ - Hash-Chained Audit  │                            │                  │  │
│  │          └───────────┬───────────┘                            │                  │  │
│  └──────────────────────┼────────────────────────────────────────┼──────────────────┘  │
│                         │                                        │                     │
│                         ▼                                        ▼                     │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │              Next.js 16 Real-Time Clinical Operations Dashboard                  │  │
│  │   - Live Specimen Tracker   - Action Approval Queue   - Audit Trail & Governance │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 💻 System Requirements

| Specification | Minimum (Cloud / API Mode) | Recommended (Local Ollama AI Mode) |
|---|---|---|
| **CPU** | 2 Cores (x86_64 / ARM64) | 4+ Cores (Apple Silicon or modern Intel/AMD) |
| **RAM** | 4 GB | 8 GB – 16 GB (for local 3B–8B parameter models) |
| **Disk** | 10 GB SSD space | 25 GB SSD space (includes local LLM weights) |
| **GPU** | Not required | Optional (Apple Metal / NVIDIA CUDA speeds inference) |
| **Network** | Outbound HTTPS (if using Cloud LLMs) | **100% Offline / Air-Gapped Supported** |

---

## 🛠️ OS-Specific Prerequisites

### 🐧 Linux (Ubuntu, Debian, Fedora, RHEL)

```bash
# 1. Update and install base utilities
sudo apt-get update && sudo apt-get install -y curl git python3 python3-pip python3-venv

# 2. Install Docker and Docker Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 3. (Optional) Install Ollama for local air-gapped processing
curl -fsSL https://ollama.com/install.sh | sh
```

### 🍎 macOS (Apple Silicon M1/M2/M3/M4 & Intel)

```bash
# 1. Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install Docker Desktop or OrbStack
brew install --cask docker

# 3. Install Python 3.12 and Node.js
brew install python@3.12 node

# 4. (Optional) Install Ollama for local air-gapped processing
brew install ollama
```

### 🪟 Windows (WSL2 / PowerShell)

1. Install **[Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)** with the **WSL2 Backend** enabled.
2. (Optional) Download and run the **[Ollama for Windows Installer](https://ollama.com/download/windows)**.
3. Open **PowerShell** (or Windows Terminal with WSL2 Ubuntu) to execute the setup commands.

---

## 🚀 Quick Start with Docker (Recommended)

The easiest way to launch the entire stack (Gateway, Agents Core, Web Dashboard, Synthetic Simulator, PostgreSQL + pgvector, and Redis) is via Docker Compose.

### Step 1: Clone Repository & Create `.env`

```bash
git clone https://github.com/abusuraihsakhri/labmind-atlas.git
cd labmind-atlas

# Copy the configuration template
cp .env.example .env
```

### Step 2: Configure Environment Variables

Open `.env` in your favorite editor and configure your secrets. For a quick local start:

```bash
# Choose LLM Provider: 'ollama' (local), 'anthropic', 'openai', or 'custom'
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_WORKER_MODEL=llama3.2
OLLAMA_SUPERVISOR_MODEL=llama3.2

# Generate secure random secrets (e.g. with openssl rand -hex 32)
POSTGRES_DB=labmind
POSTGRES_USER=labmind_admin
POSTGRES_PASSWORD=secure_postgres_pass_123!
REDIS_PASSWORD=secure_redis_pass_123!

RE_ID_MAP_KEY=dGhpcy1pcy1hLXNhbXBsZS1mZXJuZXQta2V5LTMyYnl0ZXM9
GATEWAY_RESOLVE_SECRET=gateway_resolve_secret_key_123456789
GATEWAY_INGEST_SECRET=gateway_ingest_secret_key_123456789
AUDIT_SECRET_KEY=audit_hash_secret_key_123456789

TIER2_AUTH_SECRET=operator_tier2_secret_token_123456789
TIER3_AUTH_SECRET=admin_tier3_secret_token_123456789
SERVICE_AUTH_SECRET=system_service_secret_token_123456789
TOKEN_SALT=token_salt_random_string_123456789
```

> **Generating a Fernet Key in Python:**
> ```python
> python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
> ```

### Step 3: Build & Launch the Services

```bash
cd infra
docker compose up --build -d
```

### Step 4: Access the System

Once the containers are healthy:
- 🌐 **Web Dashboard:** [http://localhost:3000](http://localhost:3000)
- 🔬 **Agents API & Supervisor:** [http://localhost:8001/health](http://localhost:8001/health)
- 🔒 **On-Premise Gateway:** [http://localhost:8000/health](http://localhost:8000/health)
- 📊 **Prometheus Metrics:** [http://localhost:8001/metrics](http://localhost:8001/metrics)

---

## 🦙 Local Air-Gapped AI Setup with Ollama

For hospitals and diagnostic laboratories requiring strict compliance (HIPAA, GDPR, DPDPA) where clinical reasoning must **never leave the local server**, ATLAS connects natively to **Ollama**.

```
┌───────────────────────────────────────────────────────────┐
│                    AIR-GAPPED DEPLOYMENT                  │
│                                                           │
│  [ De-identified Specimen ] ──▶ [ ATLAS Agents Core ]     │
│                                          │                │
│                                          ▼                │
│                              [ Local Ollama Engine ]      │
│                              (llama3.2 / meditron)        │
│                                          │                │
│                              100% On-Premise GPU/CPU      │
│                              Zero Cloud Outbound Data     │
└───────────────────────────────────────────────────────────┘
```

### 1. Start Ollama on Host Machine

```bash
# On Linux / macOS / Windows Terminal
ollama serve
```

### 2. Pull Recommended Models

```bash
# Ultra-fast lightweight model for workers (TAT & Critical alert detection)
ollama pull llama3.2

# (Alternative) High-accuracy general model
ollama pull mistral

# (Alternative) Specialized clinical model
ollama pull meditron
```

### 3. Wire into ATLAS

In your `.env` file:
```env
LLM_PROVIDER=ollama
# If running ATLAS in Docker on Linux/macOS/Windows:
OLLAMA_BASE_URL=http://host.docker.internal:11434

# If running ATLAS directly on bare-metal Python:
# OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_WORKER_MODEL=llama3.2
OLLAMA_SUPERVISOR_MODEL=llama3.2
```

ATLAS will now perform all turnaround time evaluations, panic value classifications, and supervisor conversations completely on-premise without an active internet connection.

---

## 💻 Bare-Metal Local Development Setup

If you prefer running services directly on your host machine without Docker:

### 1. Start Databases (PostgreSQL + Redis)

Using local services or minimal Docker containers:

```bash
# Start PostgreSQL with pgvector
docker run -d --name labmind-db -p 5432:5432 \
  -e POSTGRES_DB=labmind \
  -e POSTGRES_USER=labmind_admin \
  -e POSTGRES_PASSWORD=your_password \
  pgvector/pgvector:pg16

# Start Redis
docker run -d --name labmind-redis -p 6379:6379 \
  redis:7-alpine redis-server --requirepass your_redis_password
```

Initialize database schema:
```bash
psql -h localhost -U labmind_admin -d labmind -f infra/init-db/01-init.sql
```

### 2. Run Gateway Service (Terminal 1)

```bash
cd gateway
python -m venv .venv
source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
python -m spacy download en_core_web_sm

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Run Agents Core (Terminal 2)

```bash
cd agents
python -m venv .venv
source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Run Alembic migrations
alembic upgrade head

uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Run Next.js Dashboard (Terminal 3)

```bash
cd web
npm install
npm run dev
```

### 5. Run LIS Simulator (Terminal 4)

```bash
cd simulator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Stream continuous live synthetic lab events
python main.py

# Or seed a 14-day historical database backfill
python main.py --backfill
```

---

## 🤖 Bring Your Own Model (BYOM) Configuration

ATLAS includes an intelligent model abstraction layer (`agents/llm_factory.py`) allowing you to swap between local open-source models, enterprise cloud providers, or custom inference clusters.

### Option A: Local Ollama (Air-Gapped / Private)
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_WORKER_MODEL=llama3.2
OLLAMA_SUPERVISOR_MODEL=llama3.2
```

### Option B: Anthropic Claude (Cloud)
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_WORKER_MODEL=claude-3-haiku-20240307
ANTHROPIC_SUPERVISOR_MODEL=claude-3-5-sonnet-20241022
```

### Option C: OpenAI / Azure Endpoints
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_WORKER_MODEL=gpt-4o-mini
OPENAI_SUPERVISOR_MODEL=gpt-4o
```

### Option D: Custom Self-Hosted Endpoints (vLLM / LM Studio / LocalAI)
```env
LLM_PROVIDER=custom
CUSTOM_LLM_BASE_URL=http://your-gpu-server:8000/v1
CUSTOM_LLM_API_KEY=optional-api-key
CUSTOM_LLM_MODEL=meta-llama/Llama-3.2-3B-Instruct
```

---

## ⚙️ Environment Variables Reference

| Variable | Required | Default / Example | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | No | `ollama` | Selected LLM backend (`ollama`, `anthropic`, `openai`, `custom`) |
| `OLLAMA_BASE_URL` | If Ollama | `http://localhost:11434` | URL of the local Ollama instance |
| `OLLAMA_WORKER_MODEL` | No | `llama3.2` | Model used for worker agents (TAT, Critical alerts) |
| `OLLAMA_SUPERVISOR_MODEL`| No | `llama3.2` | Model used for supervisor conversational queries |
| `ANTHROPIC_API_KEY` | If Claude | — | Anthropic API key |
| `OPENAI_API_KEY` | If OpenAI | — | OpenAI API key |
| `DATABASE_URL` | Yes | `postgresql://...` | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://:pass@host:6379/0`| Authenticated Redis connection URI |
| `RE_ID_MAP_KEY` | Yes | `Fernet.generate_key()` | 32-byte Fernet key for encrypting patient mapping table |
| `GATEWAY_INGEST_SECRET` | Yes | 64-char random | Token required for LIS event ingestion (`X-Auth-Token`) |
| `GATEWAY_RESOLVE_SECRET`| Yes | 64-char random | Token required to resolve clinician tokens for emergency alerts |
| `AUDIT_SECRET_KEY` | Yes | 64-char random | Key used to HMAC hash-chain the immutable audit ledger |
| `TIER2_AUTH_SECRET` | Yes | 32-byte random | Bearer token for Operator (Tier 2) actions |
| `TIER3_AUTH_SECRET` | Yes | 32-byte random | Bearer token for Administrator (Tier 3) governance |
| `SERVICE_AUTH_SECRET` | Yes | 32-byte random | Bearer token for internal system inter-service communication |
| `TOKEN_SALT` | Yes | 64-char random | Salt used for deterministic patient & specimen tokenization |
| `SMTP_HOST` | No | `smtp.gmail.com` | Optional SMTP server for critical value alert emails |
| `ALERT_EMAIL` | No | `clinician@lab.org` | Recipient email for panic laboratory values |

---

## 🩺 ATLAS Agent Hierarchy & Mechanics

```
                                  ┌─────────────────────────┐
                                  │     Supervisor Agent    │
                                  │  (Read-Only Ops Chat)   │
                                  └────────────┬────────────┘
                                               │
                                               ▼
                                  ┌─────────────────────────┐
                                  │    Workflow Manager     │
                                  │ (Delegation Controller) │
                                  └──────┬───────────┬──────┘
                                         │           │
                     ┌───────────────────┘           └───────────────────┐
                     ▼                                                   ▼
       ┌───────────────────────────┐                       ┌───────────────────────────┐
       │     TAT Monitor Worker    │                       │ Critical Value Router     │
       │ - Turnaround Time Risk    │                       │ - Panic Value Detection   │
       │ - Bottleneck Forecasting  │                       │ - Jailed Alert Routing    │
       └─────────────┬─────────────┘                       └─────────────┬─────────────┘
                     │                                                   │
                     └───────────────────┐           ┌───────────────────┘
                                         ▼           ▼
                                  ┌─────────────────────────┐
                                  │     Action Executor     │
                                  │ - OBSERVE/SUGGEST Gates │
                                  │ - Hash-Chained Audit    │
                                  └─────────────────────────┘
```

1. **TAT Monitor Worker (`agents/tat_worker.py`):**
   - Monitors specimen progress across testing phases (`ACCESSIONED` ➔ `PROCESSING` ➔ `SIGNED_OUT`).
   - Compares elapsed time against test-specific target SLAs (e.g. Surgical Biopsy: 48h, Chem: 1h, CBC: 45m).
   - Computes risk levels: **`GREEN`** (nominal), **`YELLOW`** (approaching breach), **`RED`** (overdue).
2. **Critical Value Router Worker (`agents/critical_worker.py`):**
   - Intercepts dangerous panic laboratory values.
   - Automatically writes to non-erasable, jailed audit tables with a mandatory 10-year retention policy.
   - Dispatches emergency clinician notifications (Email/SMS).
3. **Supervisor Agent (`agents/supervisor.py`):**
   - Provides read-only conversational assistance for laboratory managers.
   - Built with strict input sanitization and prompt injection isolation boundaries (`<laboratory_context>`, `<user_query>`).
4. **Action Executor (`agents/base.py`):**
   - Enforces trust stages: In **`OBSERVE`** mode, actions are logged without execution. In **`SUGGEST`** mode, proposed actions are placed into the Operator Approval Queue.
   - Automatically calculates HMAC-SHA256 hash chains on the audit ledger.

---

## 🖥️ Dashboard Walkthrough & Web Interface

The web interface is built with **Next.js 16**, **React 19**, and **Tailwind CSS 4**, communicating securely through a server-side BFF proxy (`/api/proxy`):

- 📋 **Live Specimen Tracker:** Real-time list of all active laboratory specimens, status indicators, and color-coded TAT risk badges.
- ⚡ **Action Approval Queue:** Interactive card interface allowing Tier 2 operators to review agent recommendations, inspect reasoning, and approve or dismiss actions.
- 💬 **ATLAS Supervisor Chat:** Conversational drawer allowing staff to ask natural-language questions (*"Which specimens are at risk?"*, *"Show pending panic alerts"*).
- 🔒 **Immutable Audit Log Viewer (`/audit`):** Cryptographic verification tool that iterates through the HMAC hash chain, verifying ledger integrity and displaying real-time validity flags.
- 🗑️ **Governed Erasure Controls:** Administrator interface to request compliant data erasures (enforces 90-day retention minimums and blocks deletions on jailed categories).

---

## 📡 API Reference

### 🔒 On-Premise Gateway (Port `8000`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/ingest/event` | `X-Auth-Token: GATEWAY_INGEST_SECRET` | Ingests raw LIS event, strips PHI, publishes to Redis Stream |
| `GET` | `/resolve/{token}` | `X-Auth-Token: GATEWAY_RESOLVE_SECRET` | Resolves encrypted clinician tokens for emergency routing |
| `GET` | `/health` | None | Service health status |

### 🧠 ATLAS Agents API (Port `8001`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/specimens` | Bearer (Tier 2/3) | Retrieve live specimen tracking states |
| `GET` | `/events/specimens` | Bearer (Tier 2/3) | Server-Sent Events (SSE) live specimen update stream |
| `GET` | `/actions` | Bearer (Tier 2/3) | Retrieve pending proposed actions in SUGGEST queue |
| `POST` | `/actions/{id}/approve` | Bearer (Tier 2/3) | Approve proposed action and append to audit ledger |
| `POST` | `/actions/{id}/dismiss` | Bearer (Tier 2/3) | Dismiss proposed action and append to audit ledger |
| `POST` | `/alerts/{id}/ack` | Bearer (Tier 2/3) | Acknowledge critical value panic alert |
| `POST` | `/supervisor/chat` | Bearer (Tier 2/3) | Query Supervisor conversational agent |
| `GET` | `/admin/stage` | Bearer (Tier 2/3) | Retrieve current global trust stage (`OBSERVE`/`SUGGEST`) |
| `POST` | `/admin/stage` | Bearer (Tier 3) | Update global trust stage |
| `GET` | `/audit` | Bearer (Tier 3) | Retrieve and verify cryptographic HMAC audit trail |
| `POST` | `/admin/erasure/request`| Bearer (Tier 3) | Request GDPR/retention-compliant episodic memory erasure |
| `GET` | `/export/specimens` | Bearer (Tier 3) | Export active specimen records as CSV |
| `GET` | `/export/audit` | Bearer (Tier 3) | Export full audit trail as CSV |
| `GET` | `/metrics` | None | Prometheus telemetry metrics |

---

## 🧪 Testing & Quality Verification

ATLAS includes a comprehensive test suite covering the PHI Outbound Guard, notification dispatchers, and cryptographic token generators.

```bash
# Run unit & integration tests
pytest agents/tests -v
```

Expected output:
```
============================= test session starts =============================
agents/tests/test_base.py ........                                       [ 76%]
agents/tests/test_notifications.py ...                                   [100%]
======================== 11 passed, 2 skipped in 0.84s ========================
```

---

## ❓ Troubleshooting & FAQ

### 1. `Ollama connection refused` inside Docker
- **Cause:** Docker container cannot reach Ollama running on host `localhost:11434`.
- **Solution:** Ensure `OLLAMA_BASE_URL` in `.env` is set to `http://host.docker.internal:11434`. The `infra/docker-compose.yml` file is pre-configured with `extra_hosts: ["host.docker.internal:host-gateway"]`.

### 2. `Database is locked` in SQLite token map
- **Cause:** High concurrency bursts on the gateway.
- **Solution:** The gateway is pre-configured with `PRAGMA journal_mode=WAL;` and a `20.0s` busy timeout. Ensure the gateway process has write permissions to its local directory.

### 3. How do I switch from OBSERVE to SUGGEST mode?
- Click the **"Toggle Stage"** button on the web dashboard header, or issue a `POST /admin/stage` request with a Tier 3 authorization token.

---

## 📂 Project Directory Structure

```
Labmind/
├── gateway/              # On-Premises PHI De-Identification Gateway (FastAPI + Presidio)
│   ├── main.py           # Ingestion, tokenization, and Redis Stream publishing
│   ├── requirements.txt  # Gateway dependencies
│   └── Dockerfile        # Hardened non-root container specification
├── agents/               # ATLAS Agent Core & Memory Engine
│   ├── atlas.py          # ATLAS Context Assembler (Working, Episodic, Semantic)
│   ├── llm_factory.py    # Multi-Provider Model Factory (Ollama, Claude, OpenAI)
│   ├── base.py           # Action Executor, Outbound PHI Guard, HMAC Chaining
│   ├── tat_worker.py     # Turnaround Time Monitor Worker
│   ├── critical_worker.py# Critical/Panic Value Router Worker
│   ├── supervisor.py     # Supervisor Read-Only Conversational Agent
│   ├── workflow_manager.py # Orchestration & Delegation
│   ├── pipeline.py       # Redis Stream Batch Consumer & State Sync
│   ├── database.py       # SQLAlchemy Session Management & Connection Pooling
│   ├── models.py         # SQLAlchemy ORM Models (pgvector, audit_events)
│   ├── notifications.py  # SMTP email & SMS panic alert dispatcher
│   ├── metrics.py        # Prometheus telemetry counters & histograms
│   ├── requirements.txt  # Agent dependencies
│   └── tests/            # Test Suite
├── web/                  # Next.js 16 Clinical Operations Dashboard
│   ├── app/              # App Router Pages & API BFF Proxy Route
│   ├── package.json      # Frontend dependencies
│   └── Dockerfile        # Multi-stage standalone container specification
├── simulator/            # Synthetic LIS Event Generator (HL7/Event Simulation)
│   ├── main.py           # Synthetic specimen event emitter with backfill
│   └── requirements.txt  # Simulator dependencies
├── infra/                # Infrastructure & Orchestration
│   ├── docker-compose.yml# Multi-service stack definition
│   └── init-db/          # PostgreSQL + pgvector Schema & Security Triggers
├── .env.example          # Environment configuration template
└── README.md             # Comprehensive System Documentation
```

---

## 📄 License

Private — All rights reserved. LabMind ATLAS Architecture.
