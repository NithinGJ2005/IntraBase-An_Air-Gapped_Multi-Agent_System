"""Document index data structures with safe, user-facing citations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceCitation:
    document_id: str
    filename: str
    page: int | None


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    filename: str
    page: int | None
    content: str
    allowed_roles: frozenset[str]


@dataclass(frozen=True)
class IndexedDocument:
    document_id: str
    content_hash: str
    filename: str
    allowed_roles: frozenset[str]
    chunks: tuple[DocumentChunk, ...]


@dataclass(frozen=True)
class SearchResult:
    content: str
    citation: SourceCitation
    score: int


@dataclass(frozen=True)
class IndexingReport:
    indexed_documents: int
    reused_documents: int
    skipped_documents: int
