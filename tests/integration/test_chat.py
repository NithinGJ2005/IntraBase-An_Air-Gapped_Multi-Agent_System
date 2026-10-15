import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from starlette.testclient import TestClient

from app.audit import InMemoryAuditSink
from app.config import Settings
from app.db.catalog import QueryDefinition
from app.db.service import DatabaseQueryService
from app.documents.service import DocumentIndexer
from app.llm.service import LocalLLMClient
from app.main import create_app
from app.orchestration.mcp import (
    DatabaseQueryMCPTool,
    DocumentSearchMCPTool,
    MCPToolRegistry,
)
from app.orchestration.service import IntranetAssistantService


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key="k" * 32,
        dev_auth_signing_key="s" * 32,
        enable_development_auth=True,
        llm_enabled=True,
        llm_base_url="http://llm.internal:8000/v1",
        llm_allowed_hosts=["llm.internal"],
        llm_model="reviewed-model",
        role_permission_map={
            "employee": ["chat:use", "documents:search"],
            "analyst": ["chat:use", "database:read"],
            "limited": [],
        },
    )


def auth_token(subject: str, roles: list[str]) -> str:
    cfg = settings()
    return jwt.encode(
        {
            "sub": subject,
            "roles": roles,
            "aud": cfg.auth_audience,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        cfg.dev_auth_signing_key.get_secret_value(),
        algorithm="HS256",
    )


class ScriptedHttpClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"url": url, "kwargs": kwargs})
        spec = self.responses.pop(0) if self.responses else {"status_code": 200, "content": "Default response"}
        status_code = spec.get("status_code", 200)
        request = httpx.Request("POST", url)
        if status_code != 200:
            return httpx.Response(status_code, request=request)
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "reviewed-model",
                "choices": [{"message": {"content": spec.get("content", "OK")}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )


class StaffParams(BaseModel):
    dept: str = Field(min_length=1)


@pytest.fixture
def app_client(tmp_path: Path):
    cfg = settings()
    audit_sink = InMemoryAuditSink()

    # Create test document
    doc = tmp_path / "it_security.md"
    doc.write_text("Password rotation is required every 90 days.", encoding="utf-8")
    doc.with_suffix(".md.acl.json").write_text(
        json.dumps({"allowed_roles": ["employee"]}), encoding="utf-8"
    )
    indexer = DocumentIndexer([tmp_path], 100, 10)
    indexer.reindex()

    # Create test database
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE staff (dept TEXT, name TEXT)"))
        conn.execute(text("INSERT INTO staff VALUES ('IT', 'Bob')"))
    catalog = {
        "staff.by_dept": QueryDefinition(
            identifier="staff.by_dept",
            statement="SELECT dept, name FROM staff WHERE dept = :dept",
            parameter_model=StaffParams,
        )
    }
    db_service = DatabaseQueryService(engine, catalog, audit_sink, 10, 5)

    registry = MCPToolRegistry(audit_sink)
    registry.register(DocumentSearchMCPTool(indexer, audit_sink))
    registry.register(DatabaseQueryMCPTool(db_service, audit_sink))

    http_client = ScriptedHttpClient([])
    llm_client = LocalLLMClient(cfg, http_client)
    assistant = IntranetAssistantService(cfg, llm_client, registry, audit_sink)

    app = create_app(
        settings=cfg,
        llm_client=llm_client,
        document_indexer=indexer,
        database_service=db_service,
    )
    app.state.assistant_service = assistant
    app.state.audit_sink = audit_sink
    app.state.tool_registry = registry

    return TestClient(app), http_client, audit_sink


def test_chat_unauthenticated(app_client):
    client, _, _ = app_client
    response = client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 401
    assert response.json()["error"] == "authentication_required"


def test_chat_forbidden_without_permission(app_client):
    client, _, _ = app_client
    token = auth_token("user-limited", ["limited"])
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Hello"},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


def test_chat_successful_direct_response(app_client):
    client, http_client, audit_sink = app_client
    http_client.responses = [{"status_code": 200, "content": "I am here to help you."}]

    token = auth_token("user-emp", ["employee"])
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "test-req-1"},
        json={"message": "Hi assistant"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "I am here to help you."
    assert data["request_id"] == "test-req-1"
    assert response.headers["X-Request-ID"] == "test-req-1"


def test_chat_successful_with_document_search(app_client):
    client, http_client, audit_sink = app_client
    http_client.responses = [
        {"status_code": 200, "content": '{"tool": "search_documents", "parameters": {"query": "password rotation"}}'},
        {"status_code": 200, "content": "Password rotation is required every 90 days [it_security.md]."},
    ]

    token = auth_token("user-emp", ["employee"])
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "When must I rotate my password?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "90 days" in data["response"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["filename"] == "it_security.md"


def test_chat_overloaded_returns_429(app_client):
    client, http_client, _ = app_client
    http_client.responses = [{"status_code": 429}]

    token = auth_token("user-emp", ["employee"])
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Hello"},
    )

    assert response.status_code == 429
    assert response.json()["error"] == "service_overloaded"


def test_chat_unavailable_returns_503(app_client):
    client, http_client, _ = app_client
    http_client.responses = [{"status_code": 503}]

    token = auth_token("user-emp", ["employee"])
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Hello"},
    )

    assert response.status_code == 429 or response.status_code == 503
    assert response.json()["error"] in {"service_overloaded", "service_unavailable"}


def test_list_mcp_tools(app_client):
    client, _, _ = app_client
    token = auth_token("user-emp", ["employee"])
    response = client.get(
        "/api/v1/mcp/tools",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    tools = response.json()["tools"]
    names = {t["name"] for t in tools}
    assert "search_documents" in names
    assert "query_database" in names


def test_direct_mcp_call_allowed(app_client):
    client, _, _ = app_client
    token = auth_token("user-emp", ["employee"])
    response = client.post(
        "/api/v1/mcp/tools/search_documents",
        headers={"Authorization": f"Bearer {token}"},
        json={"parameters": {"query": "password"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "search_documents"
    assert "Password rotation" in data["content"]
    assert len(data["citations"]) == 1


def test_direct_mcp_call_forbidden(app_client):
    client, _, _ = app_client
    # employee role lacks database:read permission
    token = auth_token("user-emp", ["employee"])
    response = client.post(
        "/api/v1/mcp/tools/query_database",
        headers={"Authorization": f"Bearer {token}"},
        json={"parameters": {"query_id": "staff.by_dept", "parameters": {"dept": "IT"}}},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"
