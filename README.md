# 🤖 Multi-Agent Hybrid RAG Knowledge Assistant

> A production-oriented, multi-tenant AI knowledge assistant that combines **Hybrid RAG, bounded Multi-Agent orchestration, persistent memory, human-in-the-loop review, grounded generation, and observable agent execution**.

<p align="center">

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_AI-1C3C3C?style=for-the-badge)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

</p>

<p align="center">
  <a href="https://docpilot-rag-assistant.vercel.app">
    <strong>🌐 Live Demo</strong>
  </a>
  •
  <a href="#-architecture">
    Architecture
  </a>
  •
  <a href="#-quick-start">
    Quick Start
  </a>
</p>

---

## 📌 Overview

**Multi-Agent Hybrid RAG** is a full-stack AI knowledge assistant designed to answer questions and perform bounded research tasks using information contained in user-provided documents.

Unlike a conventional RAG chatbot that follows a fixed:

```text
Question → Retrieve → Generate
```

pipeline, this system dynamically chooses between a **low-latency Simple RAG path** and a **bounded Multi-Agent workflow**.

```text
                         ┌─────────────────────┐
                         │      User Query     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Query Router      │
                         └──────────┬──────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ▼                             ▼
             ┌───────────────┐           ┌─────────────────┐
             │   Simple RAG   │           │ Multi-Agent RAG │
             └───────┬───────┘           └────────┬────────┘
                     │                            │
                     │                    ┌───────▼────────┐
                     │                    │    Planner     │
                     │                    └───────┬────────┘
                     │                            │
                     │                    ┌───────▼────────┐
                     │                    │   Retrieval    │
                     │                    │     Agents     │
                     │                    └───────┬────────┘
                     │                            │
                     │                    ┌───────▼────────┐
                     │                    │    Synthesis   │
                     │                    └───────┬────────┘
                     │                            │
                     │                    ┌───────▼────────┐
                     │                    │     Writer     │
                     │                    └───────┬────────┘
                     │                            │
                     └──────────────┬─────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Citation Validation │
                         │   + Confidence      │
                         └──────────┬──────────┘
                                    │
                           ┌────────┴────────┐
                           │                 │
                           ▼                 ▼
                      ┌─────────┐      ┌────────────┐
                      │ Publish │      │ Human      │
                      │ Answer  │      │ Review     │
                      └─────────┘      └────────────┘
```

The objective is not simply to make an LLM answer questions, but to build an **inspectable and controlled AI system** where retrieval, generation, agent execution, citations, permissions, and human review are treated as first-class engineering concerns.

---

# ✨ Key Features

## 🔎 Hybrid Retrieval

Combines two complementary retrieval strategies:

* **Semantic vector search** using embeddings
* **PostgreSQL full-text search**
* Reciprocal Rank Fusion (RRF)
* Workspace-scoped retrieval
* Metadata filtering
* Near-duplicate suppression
* Retrieval caching
* Versioned index profiles

This helps handle both:

* semantic questions
* exact keyword / terminology searches

---

## 🤖 Bounded Multi-Agent Orchestration

Complex questions can be processed through a **LangGraph-based agent workflow**.

The agent graph contains specialized stages for:

* Query routing
* Planning
* Retrieval
* Synthesis
* Writing
* Review

Agent execution is intentionally bounded through:

* Maximum agent steps
* Recursion limits
* Concurrency limits
* Wall-clock timeouts
* Context budgets
* Output limits
* Retry limits

This prevents uncontrolled autonomous execution and keeps the system predictable.

---

## ⚡ Simple RAG Fast Path

Not every question needs multiple agents.

Straightforward questions are routed through a lightweight RAG workflow:

```text
Query
  ↓
Embedding + Keyword Retrieval
  ↓
Hybrid Rank Fusion
  ↓
Evidence Selection
  ↓
Grounded Generation
  ↓
Citation Validation
  ↓
Answer
```

This reduces unnecessary model calls and keeps common queries fast.

---

## 📚 Grounded Answers & Citations

The system is designed to prevent unsupported answers.

Every factual response is associated with explicit evidence identifiers:

```text
C1
C2
C3
...
```

Citations are validated against:

* Retrieved chunks
* Source documents
* Page / section provenance
* Citation coverage
* Retrieval quality

When sufficient evidence is unavailable, the system can return an explicit:

```text
insufficient_evidence
```

state rather than fabricating an answer.

---

## 🧠 Persistent Memory

The assistant supports attributable long-term memory.

Memory records include:

* Source
* Confidence
* Visibility
* Provenance
* Expiration
* Ownership

Only explicitly requested memories are automatically persisted.

Users can inspect and delete their stored memories.

Memory is treated as **untrusted context** and cannot override:

* System instructions
* Workspace permissions
* Document evidence
* Citation requirements

---

## 👨‍⚖️ Human-in-the-Loop Review

The system supports human approval before publishing certain outputs.

A run can be escalated when:

* Confidence falls below the configured threshold
* Citation coverage is insufficient
* Conflicting evidence is detected
* Sensitive actions are requested
* A generated report is being exported
* Shared memory is modified
* A replay requires approval

Reviewers can:

* ✅ Approve
* ✏️ Edit
* ❌ Reject
* 🔄 Request revision

All decisions are stored as durable audit events.

---

## 🔐 Multi-Tenant Security

Workspace membership is the primary authorization boundary.

The system uses:

* Supabase Auth
* PostgreSQL Row Level Security
* Workspace-scoped queries
* Owner / Reviewer / Member roles
* Server-side JWT verification
* Private object storage
* Audit events
* Secure response headers
* CORS allowlists

The architecture is designed so that tenant-owned records are associated with a `workspace_id`.

Cross-workspace access is explicitly tested through negative authorization and RLS tests.

---

## 📄 Document Ingestion

Supported formats include:

* PDF
* Markdown
* HTML
* Plain text

The ingestion pipeline performs:

```text
Upload
   ↓
Checksum Verification
   ↓
Validation
   ↓
Storage
   ↓
Parsing
   ↓
Chunking
   ↓
Embedding
   ↓
Vector + FTS Index
   ↓
Ready
```

The ingestion system supports:

* SHA-256 checksums
* Deduplication
* Page provenance
* Durable jobs
* Retry handling
* Visibility timeouts
* Quarantine states
* Idempotent processing
* Realtime status updates

Maximum supported document size is currently **25 MB**.

---

# 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│                    React + Vite + TS                        │
│                                                             │
│  Chat │ Documents │ Memory │ Reviews │ Traces │ Evaluation │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ REST / SSE
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         FastAPI                             │
│                                                             │
│ Auth │ Workspaces │ Documents │ Chat │ Runs │ Reviews       │
│                                                             │
│                  ┌──────────────────────┐                   │
│                  │     Query Router     │                   │
│                  └──────────┬───────────┘                   │
│                             │                               │
│              ┌──────────────┴──────────────┐                │
│              ▼                             ▼                │
│        Simple RAG                     LangGraph             │
│                                      Agent Graph            │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌─────────────────────────────────────────────────────────────┐
│                       Retrieval Layer                       │
│                                                             │
│  pgvector Semantic Search + PostgreSQL Full-Text Search    │
│                         ↓                                   │
│              Reciprocal Rank Fusion                         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         Supabase                            │
│                                                             │
│ PostgreSQL │ pgvector │ RLS │ Auth │ Storage │ PGMQ         │
│ Realtime   │ Cron     │ Audit │ Durable State              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                       ┌───────────────┐
                       │ Gemini Models │
                       │  Embeddings   │
                       │  Generation   │
                       └───────────────┘
```

---

# 🧩 Technology Stack

| Layer               | Technology                  |
| ------------------- | --------------------------- |
| Frontend            | React, TypeScript, Vite     |
| Backend             | Python, FastAPI             |
| Agent Orchestration | LangGraph                   |
| Database            | PostgreSQL                  |
| Vector Search       | pgvector                    |
| Keyword Search      | PostgreSQL Full-Text Search |
| Authentication      | Supabase Auth               |
| Object Storage      | Supabase Storage            |
| Durable Jobs        | PostgreSQL PGMQ             |
| Realtime            | Supabase Realtime           |
| LLM / Embeddings    | Google Gemini               |
| PDF Processing      | PyMuPDF                     |
| Validation          | Pydantic                    |
| Logging             | Structlog                   |
| Testing             | Pytest, Vitest, Playwright  |
| Static Analysis     | Ruff, Mypy, ESLint          |
| Containers          | Docker                      |
| Frontend Deployment | Vercel / Cloudflare Pages   |
| Backend Deployment  | Render                      |
| Database Platform   | Supabase                    |

The backend currently targets Python 3.12–3.13 and uses LangGraph 1.2.9 alongside FastAPI and the other core dependencies.

---

# 🔄 Retrieval Pipeline

The retrieval engine combines dense and sparse search.

```text
                    User Query
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
        Query Embedding      Keyword Query
              │                   │
              ▼                   ▼
        Vector Search        PostgreSQL FTS
              │                   │
              └─────────┬─────────┘
                        ▼
              Reciprocal Rank Fusion
                        │
                        ▼
             Duplicate Suppression
                        │
                        ▼
               Metadata Filtering
                        │
                        ▼
                 Top Evidence
                        │
                        ▼
                 LLM Generation
```

This approach allows the system to benefit from both semantic similarity and exact textual matching.

---

# 🤖 Multi-Agent Workflow

For complex research questions, LangGraph coordinates multiple bounded stages.

```text
                         ┌──────────────┐
                         │   Supervisor │
                         └───────┬──────┘
                                 │
                         ┌───────▼──────┐
                         │    Planner   │
                         └───────┬──────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
             Retrieval Agent           Retrieval Agent
                    │                         │
                    └────────────┬────────────┘
                                 ▼
                         ┌──────────────┐
                         │   Synthesizer │
                         └───────┬───────┘
                                 │
                         ┌───────▼──────┐
                         │    Writer    │
                         └───────┬──────┘
                                 │
                         ┌───────▼──────┐
                         │    Reviewer  │
                         └───────┬──────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
                 Publish                 Human Review
```

The graph is intentionally **bounded and resumable**, with durable checkpoints and explicit execution limits.

---

# 📊 Observability & Tracing

Each run can expose an inspectable execution trace containing:

* Request ID
* Run ID
* Agent steps
* Retrieval evidence
* Tool calls
* Timing information
* Model usage
* Errors
* Routing decisions
* Final outcome

Sensitive information is redacted from operational logs.

The system intentionally exposes **execution decisions and tool outcomes rather than private chain-of-thought**.

---

# 🧪 Evaluation

The project includes a versioned evaluation framework designed to compare different retrieval and generation strategies.

Evaluation dimensions include:

* Retrieval quality
* Citation precision
* Citation coverage
* Groundedness
* Answer coverage
* Safety
* Latency
* Token usage
* Model-call count
* Failure rate

The evaluation suite includes scenarios covering:

* Direct lookup
* Multi-document synthesis
* Conflicting evidence
* Missing evidence
* Prompt injection
* Adversarial queries

Retrieval strategies can be compared across:

```text
Keyword-only
Dense-only
Hybrid
Simple RAG
Agentic RAG
```

---

# 🛡️ Security Design

Security is implemented across multiple layers.

### Authentication

Supabase Auth provides user authentication and session management.

### Authorization

Every request is associated with an active workspace.

### Database Security

PostgreSQL Row Level Security prevents cross-tenant data access.

### Storage Security

Uploaded documents are stored in private, workspace-scoped storage.

### Agent Security

The tool registry follows a deny-by-default approach.

Agents cannot:

* Execute arbitrary shell commands
* Perform financial transactions
* Send external messages
* Modify arbitrary third-party systems
* Delete an entire workspace

### Prompt Injection Protection

Retrieved documents are explicitly treated as **untrusted data**.

The system does not allow instructions embedded inside retrieved documents to override system-level instructions or authorization policies.

---

# 📁 Project Structure

```text
multi-agent-rag/
│
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── agents/
│   │   │   ├── api/
│   │   │   ├── auth/
│   │   │   ├── chat/
│   │   │   ├── documents/
│   │   │   ├── evaluation/
│   │   │   ├── memory/
│   │   │   ├── retrieval/
│   │   │   ├── runs/
│   │   │   ├── security/
│   │   │   └── main.py
│   │   │
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   └── web/
│       ├── src/
│       ├── tests/
│       └── package.json
│
├── contracts/
│   ├── openapi.yaml
│   └── events.asyncapi.yaml
│
├── docs/
│   ├── adr/
│   ├── security/
│   ├── performance/
│   ├── operations/
│   └── phase-*-acceptance.md
│
├── scripts/
│   ├── check_contracts.py
│   └── check_migrations.py
│
├── supabase/
│   ├── migrations/
│   └── config.toml
│
├── docker-compose.yml
├── package.json
├── .env.example
└── README.md
```

---

# 🚀 Quick Start

## Prerequisites

Make sure the following are installed:

* Python **3.12+**
* Node.js **24+**
* npm **11+**
* Git
* Docker *(optional)*

---

## 1. Clone the repository

```bash
git clone https://github.com/dshambhavi980-cpu/multi-agent-rag.git

cd multi-agent-rag
```

---

## 2. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Configure the required Supabase and Gemini credentials in `.env`.

> Never commit `.env` or provider secrets to the repository.

---

## 3. Create the Python environment

### Windows

```powershell
python -m venv .venv

.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 -m venv .venv

source .venv/bin/activate
```

---

## 4. Install backend dependencies

```bash
python -m pip install -e "./apps/api[dev]"
```

---

## 5. Install frontend dependencies

```bash
npm install
```

---

## 6. Start the backend

```powershell
Set-Location apps\api

python -m uvicorn app.main:app --reload --port 8000
```

The API will be available at:

```text
http://127.0.0.1:8000
```

---

## 7. Start the frontend

In another terminal:

```powershell
npm run dev:web
```

The frontend will be available at:

```text
http://127.0.0.1:5173
```

The frontend proxies `/api` requests to the FastAPI backend.

---

# 🧪 Testing

The project uses multiple testing layers.

### Backend

```bash
cd apps/api

python -m pytest
```

The backend test configuration enforces a **90% minimum coverage threshold**.

### Static analysis

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

### Frontend

```bash
npm run lint:web
npm run typecheck:web
npm run test:web
npm run build:web
```

### End-to-end

```bash
npm run test:e2e
```

### Full frontend validation

```bash
npm run check:web
```

---

# ⚙️ Engineering Principles

The project follows several important engineering principles.

### 1. Retrieval before generation

The LLM should generate from evidence rather than relying solely on model knowledge.

### 2. Simple path before agentic path

Agentic execution is reserved for questions that benefit from planning and multiple reasoning stages.

### 3. Bounded autonomy

Agents operate within explicit limits for:

* Steps
* Time
* Context
* Concurrency
* Retries
* Output

### 4. Evidence is first-class data

Retrieval results and citations are persisted and traceable.

### 5. Security at every layer

Authorization is enforced at both the API and database levels.

### 6. Human control for sensitive operations

The system can pause execution and request human approval.

### 7. Reproducibility

Migrations, contracts, tests, configuration, and deployment workflows are version-controlled.

---

# 📈 Product Constraints

The initial production-oriented configuration includes:

| Parameter                         |           Default |
| --------------------------------- | ----------------: |
| Maximum document size             |             25 MB |
| Maximum documents / workspace     |               100 |
| Maximum active chunks / workspace |            10,000 |
| Maximum retrieved chunks          |                10 |
| Default final evidence            |                 6 |
| Maximum agent steps               |                 8 |
| Concurrent agent runs / user      |                 2 |
| Approval confidence threshold     |              0.65 |
| Citation coverage threshold       |              0.90 |
| Trace retention                   | 30 days / 50 runs |

These limits are intentionally conservative because the initial deployment targets free-tier infrastructure.

---

# 🌐 Live Demo

A deployed frontend is available at:

**[DocPilot — Multi-Agent RAG Assistant](https://docpilot-rag-assistant.vercel.app)**

The deployed experience includes:

* Authentication
* Workspace management
* Document workflows
* Streaming chat
* Source evidence
* Memory
* Human review
* Agent execution traces

---

# 🗺️ Roadmap

### Completed

* [x] Product requirements & architecture
* [x] FastAPI backend
* [x] React/Vite frontend
* [x] Supabase authentication
* [x] Multi-tenant workspace isolation
* [x] Document ingestion
* [x] Hybrid retrieval
* [x] Grounded RAG
* [x] Citation validation
* [x] LangGraph multi-agent orchestration
* [x] Persistent memory
* [x] Human-in-the-loop review
* [x] Execution tracing
* [x] Evaluation framework
* [x] Production hardening
* [x] Deployment & release workflow

### Future Improvements

* [ ] Additional embedding providers
* [ ] Multimodal document understanding
* [ ] OCR for image-based PDFs
* [ ] Advanced reranking models
* [ ] Additional agent tools
* [ ] Enterprise SSO
* [ ] SCIM provisioning
* [ ] Larger-scale evaluation datasets
* [ ] Dedicated vector database support
* [ ] Advanced cost optimization

---

# 🔒 Security Considerations

If you discover a security issue, please do not open a public issue containing sensitive information.

Instead, contact the repository maintainers privately with:

* A description of the vulnerability
* Reproduction steps
* Potential impact
* Suggested mitigation

Never submit API keys, access tokens, passwords, private documents, or other credentials.


# 🤝 Contributing

Contributions are welcome.

A typical workflow is:

```bash
git checkout -b feature/your-feature

# Make your changes

# Run validation
python -m pytest
python -m ruff check .
npm run check:web

git commit -m "feat: describe your change"

git push origin feature/your-feature
```

Then open a pull request describing:

* What changed
* Why it changed
* Testing performed
* Any architectural implications
* Any security considerations

---

# 📜 License

This project is intended as an engineering and portfolio project.

See the repository license for the applicable terms.

---

## ⭐ Why This Project?

This project demonstrates practical implementation of modern AI application architecture beyond simply calling an LLM API.

It brings together:

**RAG + Hybrid Search + Vector Databases + Agentic AI + LangGraph + FastAPI + React + PostgreSQL + Authentication + RLS + Memory + Human-in-the-Loop + Observability + Evaluation + Production Engineering**

The core goal is to demonstrate how an AI assistant can be designed to be:

> **Grounded, secure, observable, bounded, explainable, and production-oriented.**

---

<p align="center">
  Built with ❤️ using Python, FastAPI, React, LangGraph, PostgreSQL, Supabase and Gemini.
</p>
