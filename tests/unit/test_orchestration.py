import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app.audit import InMemoryAuditSink
from app.auth.service import Identity
from app.config import Settings
from app.db.catalog import QueryDefinition
from app.db.service import DatabaseQueryService
from app.documents.service import DocumentIndexer
from app.llm.service import LocalLLMClient
from app.orchestration.mcp import (
    DatabaseQueryMCPTool,
    DocumentSearchMCPTool,
    MCPToolRegistry,
)
from app.orchestration.service import IntranetAssistantService


def make_test_settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "secret_key": "x" * 32,
        "dev_auth_signing_key": "y" * 32,
        "llm_enabled": True,
        "llm_base_url": "http://llm.internal:8000/v1",
        "llm_allowed_hosts": ["llm.internal"],
        "llm_model": "test-model",
        "orchestration_max_iterations": 2,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class ScriptedHttpClient:
    """Mock HTTP client that returns scripted LLM responses in sequence."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"url": url, "kwargs": kwargs})
        content = self.responses.pop(0) if self.responses else "Fallback answer"
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )


class DeptParams(BaseModel):
    department: str = Field(min_length=1)


@pytest.fixture
def test_setup(tmp_path: Path):
    audit_sink = InMemoryAuditSink()

    # Document indexer
    doc_path = tmp_path / "policies.md"
    doc_path.write_text("Paid time off is 25 days per calendar year.", encoding="utf-8")
    doc_path.with_suffix(".md.acl.json").write_text(
        json.dumps({"allowed_roles": ["employee"]}), encoding="utf-8"
    )
    indexer = DocumentIndexer([tmp_path], chunk_size=100, chunk_overlap=10)
    indexer.reindex()

    # Database service
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE directory (dept TEXT, name TEXT)"))
        conn.execute(text("INSERT INTO directory VALUES ('Product', 'Carol')"))
    catalog = {
        "directory.dept": QueryDefinition(
            identifier="directory.dept",
            statement="SELECT dept, name FROM directory WHERE dept = :department",
            parameter_model=DeptParams,
        )
    }
    db_service = DatabaseQueryService(engine, catalog, audit_sink, max_result_rows=10, timeout_seconds=5)

    registry = MCPToolRegistry(audit_sink)
    registry.register(DocumentSearchMCPTool(indexer, audit_sink))
    registry.register(DatabaseQueryMCPTool(db_service, audit_sink))

    return audit_sink, registry


def identity(*permissions: str) -> Identity:
    return Identity(
        subject="employee-test",
        roles=frozenset({"employee"}),
        permissions=frozenset(permissions),
    )


def test_orchestration_direct_answer(test_setup):
    audit_sink, registry = test_setup
    http_client = ScriptedHttpClient(["Hello! How can I assist you with company resources today?"])
    llm_client = LocalLLMClient(make_test_settings(), http_client)
    service = IntranetAssistantService(make_test_settings(), llm_client, registry, audit_sink)

    result = service.ask("Hi", identity("chat:use"), "req-101")
    assert "Hello!" in result.response
    assert len(result.citations) == 0
    assert audit_sink.events[-1].action == "assistant_chat"
    assert audit_sink.events[-1].decision == "allowed"


def test_orchestration_document_search_flow(test_setup):
    audit_sink, registry = test_setup
    responses = [
        '{"tool": "search_documents", "parameters": {"query": "paid time off"}}',
        "According to our internal handbook, employees receive 25 days of paid time off per year [policies.md].",
    ]
    http_client = ScriptedHttpClient(responses)
    llm_client = LocalLLMClient(make_test_settings(), http_client)
    service = IntranetAssistantService(make_test_settings(), llm_client, registry, audit_sink)

    result = service.ask(
        "How much PTO do I get?",
        identity("chat:use", "documents:search"),
        "req-102",
    )

    assert "25 days" in result.response
    assert len(result.citations) == 1
    assert result.citations[0].filename == "policies.md"
    assert len(http_client.calls) == 2


def test_orchestration_database_query_flow(test_setup):
    audit_sink, registry = test_setup
    responses = [
        '{"tool": "query_database", "parameters": {"query_id": "directory.dept", "parameters": {"department": "Product"}}}',
        "In the Product department, Carol is listed in the company directory.",
    ]
    http_client = ScriptedHttpClient(responses)
    llm_client = LocalLLMClient(make_test_settings(), http_client)
    service = IntranetAssistantService(make_test_settings(), llm_client, registry, audit_sink)

    result = service.ask(
        "Who works in Product?",
        identity("chat:use", "database:read"),
        "req-103",
    )

    assert "Carol" in result.response
    assert len(http_client.calls) == 2


def test_orchestration_bounded_iteration_limit(test_setup):
    audit_sink, registry = test_setup
    # Scripted client that loops forever attempting to search
    looping_call = '{"tool": "search_documents", "parameters": {"query": "infinite loop"}}'
    http_client = ScriptedHttpClient([looping_call, looping_call, looping_call, looping_call])
    llm_client = LocalLLMClient(make_test_settings(orchestration_max_iterations=2), http_client)
    service = IntranetAssistantService(make_test_settings(orchestration_max_iterations=2), llm_client, registry, audit_sink)

    result = service.ask(
        "Test loop bound",
        identity("chat:use", "documents:search"),
        "req-104",
    )

    # Must terminate without infinite recursion
    assert result.response is not None
    assert len(http_client.calls) <= 3


def test_orchestration_missing_chat_permission_denied(test_setup):
    audit_sink, registry = test_setup
    http_client = ScriptedHttpClient(["Hello"])
    llm_client = LocalLLMClient(make_test_settings(), http_client)
    service = IntranetAssistantService(make_test_settings(), llm_client, registry, audit_sink)

    with pytest.raises(PermissionError, match="chat:use"):
        service.ask("Hello", identity("documents:search"), "req-105")  # Missing chat:use

    assert audit_sink.events[-1].action == "assistant_chat"
    assert audit_sink.events[-1].decision == "denied"
