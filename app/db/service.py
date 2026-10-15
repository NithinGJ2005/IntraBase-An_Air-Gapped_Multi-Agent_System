"""SQLAlchemy execution of reviewed, parameterized catalog entries only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from app.audit import AuditSink, new_event
from app.auth.service import Identity
from app.db.catalog import QueryDefinition


class DatabaseQueryError(Exception):
    pass


class UnknownQueryError(DatabaseQueryError):
    pass


class QueryInputError(DatabaseQueryError):
    pass


class DatabasePermissionError(DatabaseQueryError):
    pass


@dataclass(frozen=True)
class QueryResult:
    query_id: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


def create_read_only_engine(database_url: str) -> Engine:
    """Create an engine; the database account itself must be read-only and least-privileged."""
    url = URL.make_url(database_url)
    return create_engine(url, pool_pre_ping=True)


class DatabaseQueryService:
    def __init__(
        self,
        engine: Engine,
        catalog: dict[str, QueryDefinition],
        audit_sink: AuditSink,
        max_result_rows: int,
        timeout_seconds: int,
    ) -> None:
        self._engine = engine
        self._catalog = catalog
        self._audit_sink = audit_sink
        self._max_result_rows = max_result_rows
        self._timeout_seconds = timeout_seconds

    def execute(self, query_id: str, raw_parameters: dict[str, Any], identity: Identity, request_id: str) -> QueryResult:
        definition = self._catalog.get(query_id)
        if definition is None:
            self._audit_sink.record(new_event("database_query", "denied", request_id, identity.subject, query_id))
            raise UnknownQueryError("The requested query is not approved")
        if definition.required_permission not in identity.permissions:
            self._audit_sink.record(new_event("database_query", "denied", request_id, identity.subject, query_id))
            raise DatabasePermissionError("Database access is not permitted")
        try:
            parameters = definition.parameter_model.model_validate(raw_parameters).model_dump()
        except ValidationError as error:
            self._audit_sink.record(new_event("database_query", "denied", request_id, identity.subject, query_id))
            raise QueryInputError("Query parameters are invalid") from error

        try:
            with self._engine.connect() as connection:
                result = connection.execute(
                    text(definition.statement).execution_options(timeout=self._timeout_seconds), parameters
                )
                mappings = result.mappings().fetchmany(self._max_result_rows + 1)
        except Exception as error:
            self._audit_sink.record(new_event("database_query", "failed", request_id, identity.subject, query_id))
            raise DatabaseQueryError("Approved query execution failed") from error

        truncated = len(mappings) > self._max_result_rows
        rows = [dict(row) for row in mappings[: self._max_result_rows]]
        columns = list(rows[0].keys()) if rows else list(result.keys())
        self._audit_sink.record(new_event("database_query", "allowed", request_id, identity.subject, query_id))
        return QueryResult(query_id=query_id, columns=columns, rows=rows, truncated=truncated)
