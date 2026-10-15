# Enterprise Intranet Assistant

Phases 1–10 deliver a complete, secure enterprise intranet AI assistant with authorization boundaries, catalog-only database access, ACL-filtered document retrieval, local LLM inference, LangGraph MCP orchestration, an accessible React chat frontend, air-gapped container deployment, capacity benchmarking, and automated security verification.

## Development setup

Prerequisites: Python 3.11–3.13 and an internal or approved package source containing the pinned packages in `pyproject.toml`.

1. Create a virtual environment and install the project with development dependencies:
   `python -m venv .venv`
   `.venv\Scripts\python -m pip install -e ".[dev]"`
2. Copy `.env.example` to `.env` and replace `SECRET_KEY` with a non-production local secret of at least 32 characters.
3. Start the API: `.venv\Scripts\uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000`
4. Access the web interface at `http://127.0.0.1:8000/`.
5. Check `GET /health/live` and `GET /health/ready`.

## Testing and Verification

Run the full automated test suite (64 unit, integration, and security verification tests):

```powershell
.venv\Scripts\python -m pytest
```

Run dedicated security audit tests:

```powershell
.venv\Scripts\python -m pytest tests/security
```

Run capacity and load testing benchmarks:

```powershell
.venv\Scripts\python scripts/benchmark_capacity.py --concurrency 8 --requests 40
```

## Security and Architecture Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [Implementation Plan (All Phases)](docs/IMPLEMENTATION_PLAN.md)
- [Security Controls](docs/SECURITY.md)
- [Security Verification and Audit Report](docs/SECURITY_VERIFICATION.md)
- [Database Integration Guide](docs/DATABASE_INTEGRATION.md)
- [Document Retrieval Guide](docs/DOCUMENT_RETRIEVAL.md)
- [Local LLM Operations](docs/LLM_OPERATIONS.md)
- [Orchestration and MCP Guide](docs/ORCHESTRATION_MCP.md)
- [Frontend and Accessibility Guide](docs/FRONTEND.md)
- [Deployment and Air-Gap Operations Guide](docs/DEPLOYMENT.md)
- [Observability and Capacity Benchmarks](docs/BENCHMARKS.md)
