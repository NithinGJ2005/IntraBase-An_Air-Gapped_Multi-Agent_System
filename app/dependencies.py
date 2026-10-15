"""Phase 1 dependency injection boundaries.

Concrete database, retrieval, authentication, and LLM implementations are intentionally
deferred to later phases. Routes depend on these interfaces rather than global clients.
"""

from __future__ import annotations

from typing import Protocol


class DatabaseService(Protocol):
    async def check_ready(self) -> bool: ...


class DocumentRetrievalService(Protocol):
    async def check_ready(self) -> bool: ...


class AuthenticationService(Protocol):
    async def check_ready(self) -> bool: ...


class LLMService(Protocol):
    async def check_ready(self) -> bool: ...
