"""Static approved-query catalog. No model-generated SQL is accepted."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel, Field


class DepartmentDirectoryParameters(BaseModel):
    department: str = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class QueryDefinition:
    identifier: str
    statement: str
    parameter_model: Type[BaseModel]
    required_permission: str = "database:read"

    def __post_init__(self) -> None:
        # Catalog entries are code-reviewed, static, and strictly read-only.
        if not self.statement.lstrip().lower().startswith("select"):
            raise ValueError(f"Query {self.identifier} is not a SELECT statement")


# Synthetic example only. Administrators must replace this with reviewed queries
# matching their confirmed database engine and authorization policy.
SAMPLE_QUERY_CATALOG: dict[str, QueryDefinition] = {
    "directory.by_department": QueryDefinition(
        identifier="directory.by_department",
        statement="""
            SELECT employee_id, display_name, department
            FROM employee_directory
            WHERE department = :department
            ORDER BY display_name
            LIMIT 100
        """,
        parameter_model=DepartmentDirectoryParameters,
    )
}
