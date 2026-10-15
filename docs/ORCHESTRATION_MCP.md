# Orchestration and MCP Integration Guide

## Overview

Phase 6 implements the LangGraph-based bounded orchestration workflow and Model Context Protocol (MCP) tool contracts. The assistant handles employee inquiries by orchestrating internal tools (document search and database catalog queries) through a stateful graph while enforcing security, schema validation, prompt injection defenses, and strict process-local capacity controls.

## Architecture

```text
Employee Request (Bearer token)
        │
        ▼
FastAPI `/api/v1/chat` (require_permission "chat:use")
        │
        ▼
IntranetAssistantService (Context budgeting & State initialization)
        │
        ▼
LangGraph StateGraph Workflow
 ┌────────────────────────────────────────────────────────┐
 │ 1. reason_node: evaluates context, decides tool/answer │
 │    ├─ calls LocalLLMClient (bounded admission)         │
 │    └─ parses tool request JSON vs. natural answer      │
 ├────────────────────────────────────────────────────────┤
 │ 2. tools_node: executes approved MCP tools             │
 │    ├─ search_documents (requires documents:search)    │
 │    └─ query_database (requires database:read)          │
 ├────────────────────────────────────────────────────────┤
 │ 3. synthesize_node: combines verified tool outputs     │
 │    └─ produces final response with safe citations      │
 └────────────────────────────────────────────────────────┘
        │
        ▼
ChatResponse (response text, citations, request_id)
```

## Security Invariants

### 1. Independent Authorization (MCP Is Not an Auth Boundary)
MCP provides standard schemas and invocation protocols for LLM tools. However, tool execution does **not** trust model output or client claims:
- Each tool (`search_documents`, `query_database`) independently inspects the authenticated caller's server-side `Identity`.
- `search_documents` requires the `documents:search` permission and strictly filters returned chunks against file-adjacent `.acl.json` files and the caller's verified roles.
- `query_database` requires the `database:read` permission and accepts only pre-approved, code-reviewed static `SELECT` statements in `SAMPLE_QUERY_CATALOG`.
- If permission is lacking, the tool raises `MCPAuthorizationError`, logs a `denied` audit event, and returns a safe denial message.

### 2. Prompt Injection and Untrusted Data Defenses
All data retrieved from document files and database rows is treated as **untrusted**:
- The orchestration system prompt explicitly instructs the LLM that retrieved content is raw external data and must never be treated as system directives or executable instructions.
- Retrieved data is wrapped in explicit structural boundaries (`[Internal Tool Result for '...'] ... [End of Tool Result]`).
- Citations return only safe identifiers (`filename`, `document_id`, `page`), never full absolute filesystem paths.

### 3. Bounded Orchestration Limits
To prevent infinite tool loops, Denial-of-Service, or runaway token generation:
- The graph enforces an iteration cap (`ORCHESTRATION_MAX_ITERATIONS`, default `3`).
- Context budget is constrained by `LLM_CONTEXT_BUDGET_TOKENS`.
- Overloaded or unavailable local inference services return standardized HTTP 429 (`service_overloaded`) or 503 (`service_unavailable`) safe JSON responses.

### 4. Audit Trail
All chat queries and tool invocations record privacy-preserving audit events:
- Chat requests log `action="assistant_chat"` with actor, decision (`allowed`/`denied`), and correlation `request_id`.
- Tool executions log `action="mcp_tool_execute"` with resource name (`search_documents`, `query_database`), actor, decision, and `request_id`.
- Sensitive token values, database credentials, and raw prompts are excluded from audit sinks.

## API Endpoints

- `POST /api/v1/chat`: Main conversation endpoint. Requires `chat:use`.
- `GET /api/v1/mcp/tools`: Lists available MCP tools with their parameters JSON Schema. Requires `chat:use`.
- `POST /api/v1/mcp/tools/{tool_name}`: Directly invokes an MCP tool. Requires a valid token; checks tool-specific permissions internally.
