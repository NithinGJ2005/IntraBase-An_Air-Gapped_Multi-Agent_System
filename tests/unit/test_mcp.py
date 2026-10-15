import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app.audit import InMemoryAuditSink
from app.auth.service import Identity
from app.db.catalog import QueryDefinition
from app.db.service import DatabaseQueryService
from app.documents.service import DocumentIndexer
from app.orchestration.mcp import (
    DatabaseQueryMCPTool,
    DocumentSearchMCPTool,
    MCPAuthorizationError,
    MCPToolNotFoundError,
    MCPToolRegistry,
    MCPValidationError,
)


class SampleParams(BaseModel):
    dept: str = Field(min_length=1)


@pytest.fixture
def audit_sink():
    return InMemoryAuditSink()


@pytest.fixture
def doc_indexer(tmp_path: Path):
    doc_file = tmp_path / "handbook.md"
    doc_file.write_text("Remote work is permitted two days per week.", encoding="utf-8")
    doc_file.with_suffix(".md.acl.json").write_text(
        json.dumps({"allowed_roles": ["employee"]}), encoding="utf-8"
    )
    indexer = DocumentIndexer([tmp_path], chunk_size=100, chunk_overlap=10)
    indexer.reindex()
    return indexer


@pytest.fixture
def db_service(audit_sink):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE staff (id INT, dept TEXT, name TEXT)"))
        conn.execute(text("INSERT INTO staff VALUES (1, 'Engineering', 'Alice'), (2, 'Engineering', 'Bob')"))
    catalog = {
        "staff.by_dept": QueryDefinition(
            identifier="staff.by_dept",
            statement="SELECT id, name FROM staff WHERE dept = :dept ORDER BY name",
            parameter_model=SampleParams,
        )
    }
    return DatabaseQueryService(engine, catalog, audit_sink, max_result_rows=10, timeout_seconds=5)


def make_identity(*permissions: str, roles: tuple[str, ...] = ("employee",)) -> Identity:
    return Identity(subject="test-user", roles=frozenset(roles), permissions=frozenset(permissions))


def test_document_search_tool_success(doc_indexer, audit_sink):
    tool = DocumentSearchMCPTool(doc_indexer, audit_sink)
    identity = make_identity("documents:search")
    result = tool.execute({"query": "remote work", "limit": 2}, identity, "req-1")

    assert len(result.citations) == 1
    assert result.citations[0].filename == "handbook.md"
    assert "Remote work is permitted" in result.content
    assert audit_sink.events[-1].action == "mcp_tool_execute"
    assert audit_sink.events[-1].decision == "allowed"


def test_document_search_tool_authorization_denied(doc_indexer, audit_sink):
    tool = DocumentSearchMCPTool(doc_indexer, audit_sink)
    identity = make_identity()  # No documents:search permission

    with pytest.raises(MCPAuthorizationError, match="documents:search"):
        tool.execute({"query": "remote work"}, identity, "req-2")

    assert audit_sink.events[-1].decision == "denied"


def test_document_search_tool_validation_error(doc_indexer, audit_sink):
    tool = DocumentSearchMCPTool(doc_indexer, audit_sink)
    identity = make_identity("documents:search")

    with pytest.raises(MCPValidationError):
        tool.execute({"query": ""}, identity, "req-3")  # Empty query violates min_length=1


def test_database_query_tool_success(db_service, audit_sink):
    tool = DatabaseQueryMCPTool(db_service, audit_sink)
    identity = make_identity("database:read")
    result = tool.execute(
        {"query_id": "staff.by_dept", "parameters": {"dept": "Engineering"}},
        identity,
        "req-4",
    )

    data = json.loads(result.content)
    assert len(data["rows"]) == 2
    assert data["rows"][0]["name"] == "Alice"
    assert audit_sink.events[-1].decision == "allowed"


def test_database_query_tool_authorization_denied(db_service, audit_sink):
    tool = DatabaseQueryMCPTool(db_service, audit_sink)
    identity = make_identity()  # No database:read permission

    with pytest.raises(MCPAuthorizationError, match="database:read"):
        tool.execute(
            {"query_id": "staff.by_dept", "parameters": {"dept": "Engineering"}},
            identity,
            "req-5",
        )

    assert audit_sink.events[-1].decision == "denied"


def test_database_query_tool_unapproved_query(db_service, audit_sink):
    tool = DatabaseQueryMCPTool(db_service, audit_sink)
    identity = make_identity("database:read")

    with pytest.raises(MCPValidationError, match="not approved"):
        tool.execute(
            {"query_id": "unknown.query", "parameters": {}},
            identity,
            "req-6",
        )


def test_mcp_registry(doc_indexer, db_service, audit_sink):
    registry = MCPToolRegistry(audit_sink)
    doc_tool = DocumentSearchMCPTool(doc_indexer, audit_sink)
    db_tool = DatabaseQueryMCPTool(db_service, audit_sink)

    registry.register(doc_tool)
    registry.register(db_tool)

    descriptors = registry.list_descriptors()
    assert len(descriptors) == 2
    tool_names = {d["name"] for d in descriptors}
    assert tool_names == {"search_documents", "query_database"}

    with pytest.raises(MCPToolNotFoundError):
        registry.execute("non_existent_tool", {}, make_identity(), "req-7")
