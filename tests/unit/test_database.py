import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app.audit import InMemoryAuditSink
from app.auth.service import Identity
from app.db.catalog import QueryDefinition
from app.db.service import (
    DatabasePermissionError,
    DatabaseQueryService,
    QueryInputError,
    UnknownQueryError,
)


class Parameters(BaseModel):
    kind: str = Field(min_length=1, max_length=20)


@pytest.fixture
def service():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE items (id INTEGER, kind TEXT, name TEXT)"))
        connection.execute(
            text("INSERT INTO items (id, kind, name) VALUES (1, 'public', 'one'), (2, 'public', 'two')")
        )
    catalog = {
        "items.by_kind": QueryDefinition(
            identifier="items.by_kind",
            statement="SELECT id, name FROM items WHERE kind = :kind ORDER BY id",
            parameter_model=Parameters,
        )
    }
    return DatabaseQueryService(engine, catalog, InMemoryAuditSink(), max_result_rows=1, timeout_seconds=2)


def identity(*permissions: str) -> Identity:
    return Identity(subject="employee-1", roles=frozenset({"employee"}), permissions=frozenset(permissions))


def test_approved_parameterized_query_is_capped(service):
    result = service.execute("items.by_kind", {"kind": "public"}, identity("database:read"), "request-123")
    assert result.rows == [{"id": 1, "name": "one"}]
    assert result.truncated is True


def test_unknown_query_is_denied(service):
    with pytest.raises(UnknownQueryError):
        service.execute("DROP TABLE items", {}, identity("database:read"), "request-123")


def test_malformed_parameters_are_rejected(service):
    with pytest.raises(QueryInputError):
        service.execute("items.by_kind", {"kind": ""}, identity("database:read"), "request-123")


def test_database_permission_is_enforced(service):
    with pytest.raises(DatabasePermissionError):
        service.execute("items.by_kind", {"kind": "public"}, identity(), "request-123")
