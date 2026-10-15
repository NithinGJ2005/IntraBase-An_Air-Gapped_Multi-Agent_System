# Implementation Plan and Repository Assessment

## Current repository assessment

Assessment date: 2026-10-14. The supplied workspace was empty: it contained no README, configuration, backend, frontend, database, MCP, deployment, or test scaffold. Git was also unavailable in the current shell. Therefore, there was no existing implementation to reuse or security posture to audit. The initial Phase 1 skeleton is intentionally small and does not claim to implement later capabilities.

## Proposed architecture

Use an internal reverse proxy for TLS, SSO hand-off, and edge rate limits; a React/TypeScript frontend; FastAPI for server-side identity, authorization, validation, auditing, and API endpoints; LangGraph for bounded orchestration; independently authorized MCP tools for document retrieval and approved database queries; and an internal OpenAI-compatible local inference endpoint (vLLM preferred, llama.cpp documented where appropriate). No component may require public AI APIs.

## Phases

1. **Foundation — implemented in this increment:** central configuration, JSON structured logs, request/correlation IDs, safe API errors, lifecycle, health endpoints, dependency boundaries, and tests.
2. **Authentication, authorization, and auditing — implemented in this increment:** OIDC and isolated development-token adapters, signed-claim validation, server-side deny-by-default role/permission mapping, protected session/diagnostics endpoints, and privacy-preserving audit events. Organization-specific OIDC and retention values remain required prerequisites.
3. **Database — implemented in this increment:** SQLAlchemy catalog-only adapter, validated parameters, permission checks, audit events, result caps, and timeout execution options. An actual database driver, read-only account, server-side timeouts, and approved catalog remain IT prerequisites.
4. **Documents — implemented in this increment:** approved-root discovery, symlink/path defenses, PDF/TXT/Markdown extraction, hash-based incremental re-indexing, stale deletion handling, ACL filtering, lexical ranking, and safe citations. Local embeddings remain intentionally deferred.
5. **Inference — implemented in this increment:** internal-only OpenAI-compatible client, configurable model/output/context controls, bounded per-process admission, safe overload/unavailable errors, and capacity metrics. Global multi-worker admission, actual model approval, and hardware benchmarks remain deployment prerequisites.
6. **Orchestration/MCP — implemented in this increment:** LangGraph state graph flow, bounded execution iterations, prompt injection defenses, schema-validated internal MCP tool contracts for documents and database queries, independent authorization enforcement, and chat/tool endpoints.
7. **Frontend — implemented in this increment:** accessible React chat, safe source citations, graceful overload/unavailable error handling, in-flight cancel, session reset, and restricted diagnostics.
8. **Deployment — implemented in this increment:** internal Compose/Podman layout, Nginx TLS reverse proxy, non-root execution, offline wheelhouse and model weights staging scripts, and isolated network outbound blocking validation.
9. **Observability/load testing — implemented in this increment:** operational admin metrics endpoint, automated capacity benchmarking harness, measured throughput/latency percentiles, and hardware sizing guide.
10. **Security verification — implemented in this increment:** automated prompt injection defenses, SQL injection prevention, permission/ACL isolation, overload shedding, audit record integrity, and production air-gap configuration checks.

## Dependencies and configuration

All project dependencies are pinned in `pyproject.toml` (FastAPI, httpx, langchain-core, langgraph, PyJWT, pydantic-settings, PyMuPDF, SQLAlchemy, and uvicorn). Python 3.11–3.13 is required. `.env.example` provides explicit template variables. Packages and models are staged via `deploy/offline-staging.sh` / `deploy/offline-staging.ps1` from an IT-approved internal mirror/wheelhouse for offline air-gapped operation.

## Security risks and mitigations

- **Unauthenticated access:** Production enforces `AUTH_MODE=oidc` with RS256/ES256 signature verification; development authentication is strictly rejected by production validators.
- **Privilege escalation:** Only verified server-side claims and deny-by-default permissions (`ROLE_PERMISSION_MAP`) control access; client headers cannot assert permissions.
- **Data exfiltration:** All inference and tools are strictly internal; Docker/Podman networks enforce `internal: true` outbound blocking.
- **Database abuse:** Only cataloged, parameterized read queries from `SAMPLE_QUERY_CATALOG` with Pydantic parameter schemas, row caps, timeouts, and read-only accounts are executed.
- **Document leakage/prompt injection:** Canonical approved roots, symlink defense, chunk-level `.acl.json` filtering, safe source citations, and untrusted-data boundary isolation prevent injection attacks.
- **Overload & DoS:** Thread-safe process-local admission (`BoundedAdmission`), bounded queue depths/timeouts, in-flight cancellation (`AbortController`), and fast 429/503 responses prevent resource exhaustion.
- **Sensitive logging:** Structured logs and privacy-preserving append-only JSONL audit events omit secrets, bearer tokens, passwords, raw prompts, and database credentials.

## Test and acceptance criteria

The test suite contains 64 automated tests covering configuration validation, authentication/authorization boundaries, database queries, document indexing and ACLs, local LLM admission controls, LangGraph MCP orchestration, React chat frontend, prompt/SQL injection defenses, overload load shedding, and deployment air-gap invariants. All tests pass in an offline, Python-enabled environment without requiring real external services or production data.

## Unresolved infrastructure assumptions

IT must provide: the production database engine and read-only credentials; OIDC/SSO issuer, audience, claims, and key-discovery policy; document roots and ACL source; document retention policy; reverse-proxy/TLS certificates; GPU and server inventory; internal inference endpoint; approved model revision/license/quantization; internal package/model staging process; audit retention/access rules; and authorization to run non-production load tests. No values have been invented.
