# Architecture

## Target topology

```text
Employee browser → internal TLS reverse proxy / SSO → React frontend → FastAPI
                                                                    │
                                              LangGraph orchestration / MCP tools
                                                  ├─ approved database query service
                                                  ├─ authorized document retrieval
                                                  └─ internal local LLM service
```

Every service remains on the organization network. The reverse proxy terminates TLS and applies edge controls; FastAPI independently authenticates, authorizes, validates, and audits requests. MCP is an internal tool contract, never an authentication or authorization boundary.

## Architecture Implementation Status

The application architecture is fully implemented across all 10 planned phases:

1. **Edge & Reverse Proxy (`deploy/nginx.conf`)**:
   - Internal TLS termination (TLSv1.2/1.3), rate limiting (`10r/s`), CSP and security headers, and reverse proxying to FastAPI.
2. **Web Frontend (`app/static/`, `frontend/`)**:
   - Accessible React chat interface with citation chips, in-flight cancellation (`AbortController`), reset, safe error banners, and restricted diagnostics.
3. **Core API & Security Gateway (`app/main.py`, `app/security.py`, `app/audit.py`)**:
   - FastAPI server with signed JWT claim verification, deny-by-default role-permission mapping, correlation tracking (`X-Request-ID`, `X-Correlation-ID`), safe structured error responses, and append-only privacy-preserving audit logging (`JsonlAuditSink`).
4. **LangGraph Orchestration (`app/orchestration/graph.py`, `app/orchestration/service.py`)**:
   - Stateful agent workflow coordinating inquiries, enforcing bounded tool iterations (`ORCHESTRATION_MAX_ITERATIONS`), prompt injection structural boundaries, and citation synthesis.
5. **Model Context Protocol (MCP) Tool Contracts (`app/orchestration/mcp.py`)**:
   - `search_documents`: Schema-validated parameter model requiring `documents:search`, executing lexical chunk search filtered by file-adjacent `.acl.json` rules.
   - `query_database`: Schema-validated parameter model requiring `database:read`, executing static reviewed SQL queries in `SAMPLE_QUERY_CATALOG` with parameter binding, row limits, and statement timeouts.
6. **Local LLM Inference Client (`app/llm/service.py`)**:
   - Process-local bounded admission controls (`BoundedAdmission`), context budgeting, timeout management, and safe load shedding (HTTP 429).
7. **Deployment & Network Isolation (`deploy/`)**:
   - Multi-stage non-root Dockerfile (`appuser`, UID 10001), Compose/Podman specification with internal air-gapped networks (`internal: true`) for complete outbound blocking, and offline package/model staging scripts.
8. **Observability & Benchmarks (`docs/BENCHMARKS.md`, `scripts/benchmark_capacity.py`)**:
   - Operational `/api/v1/admin/metrics` endpoint, capacity load testing harness, and documented throughput/latency baselines.
9. **Automated Security Verification (`tests/security/`)**:
   - Comprehensive test suite validating prompt injection defenses, SQL injection prevention, role/permission boundaries, document ACL isolation, overload shedding, audit integrity, and production air-gap configuration invariants.
