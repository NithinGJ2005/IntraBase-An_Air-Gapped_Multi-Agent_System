"""Safe local document discovery, extraction, incremental indexing, and lexical search."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import fitz

from app.auth.service import Identity
from app.documents.models import DocumentChunk, IndexedDocument, IndexingReport, SearchResult, SourceCitation

SUPPORTED_SUFFIXES = frozenset({".pdf", ".txt", ".md", ".markdown"})
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)


class DocumentRootError(ValueError):
    pass


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in TOKEN_PATTERN.findall(value)}


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class DocumentIndexer:
    def __init__(self, roots: list[Path], chunk_size: int, chunk_overlap: int) -> None:
        self._roots = [self._validated_root(root) for root in roots]
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._documents: dict[str, IndexedDocument] = {}

    @staticmethod
    def _validated_root(root: Path) -> Path:
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise DocumentRootError("Configured document root is not a directory")
        return resolved

    def reindex(self) -> IndexingReport:
        previous = self._documents
        current: dict[str, IndexedDocument] = {}
        indexed = reused = skipped = 0
        for root in self._roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.is_symlink() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                try:
                    resolved = path.resolve(strict=True)
                except OSError:
                    skipped += 1
                    continue
                if not _is_inside(resolved, root):
                    skipped += 1
                    continue
                identity_input = f"{root}:{resolved.relative_to(root)}"
                document_id = hashlib.sha256(identity_input.encode("utf-8")).hexdigest()[:24]
                acl_path = resolved.with_suffix(resolved.suffix + ".acl.json")
                try:
                    content = resolved.read_bytes()
                    acl_content = acl_path.read_bytes() if acl_path.is_file() else b""
                except OSError:
                    skipped += 1
                    continue
                # ACL changes must invalidate cached chunks even if the document is unchanged.
                content_hash = hashlib.sha256(content + b"\0" + acl_content).hexdigest()
                previous_document = previous.get(document_id)
                if previous_document and previous_document.content_hash == content_hash:
                    current[document_id] = previous_document
                    reused += 1
                    continue
                roles = self._read_acl(resolved)
                try:
                    chunks = self._extract_chunks(resolved, document_id, roles)
                except (OSError, ValueError, fitz.FileDataError):
                    skipped += 1
                    continue
                current[document_id] = IndexedDocument(
                    document_id=document_id,
                    content_hash=content_hash,
                    filename=resolved.name,
                    allowed_roles=roles,
                    chunks=tuple(chunks),
                )
                indexed += 1
        self._documents = current  # Removing absent files makes stale documents unreachable.
        return IndexingReport(indexed, reused, skipped)

    @staticmethod
    def _read_acl(path: Path) -> frozenset[str]:
        """Read an administrator-managed adjacent ACL; missing/invalid ACL denies retrieval."""
        acl_path = path.with_suffix(path.suffix + ".acl.json")
        try:
            content = json.loads(acl_path.read_text(encoding="utf-8"))
            roles = content["allowed_roles"]
        except (OSError, ValueError, KeyError, TypeError):
            return frozenset()
        if not isinstance(roles, list) or not all(isinstance(role, str) and role for role in roles):
            return frozenset()
        return frozenset(roles)

    def _extract_chunks(self, path: Path, document_id: str, roles: frozenset[str]) -> list[DocumentChunk]:
        if path.suffix.lower() == ".pdf":
            with fitz.open(path) as pdf:
                pages = [(page.number + 1, page.get_text("text")) for page in pdf]
        else:
            pages = [(None, path.read_text(encoding="utf-8", errors="replace"))]
        chunks: list[DocumentChunk] = []
        for page, content in pages:
            for part in self._split(content):
                chunks.append(DocumentChunk(document_id, path.name, page, part, roles))
        return chunks

    def _split(self, content: str) -> list[str]:
        normalized = " ".join(content.split())
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self._chunk_size, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = end - self._chunk_overlap
        return chunks

    def search(self, query: str, identity: Identity, limit: int = 5) -> list[SearchResult]:
        query_tokens = _tokens(query)
        if not query_tokens or "documents:search" not in identity.permissions:
            return []
        matches: list[SearchResult] = []
        for document in self._documents.values():
            if not document.allowed_roles.intersection(identity.roles):
                continue
            for chunk in document.chunks:
                score = len(query_tokens.intersection(_tokens(chunk.content)))
                if score:
                    matches.append(
                        SearchResult(chunk.content, SourceCitation(chunk.document_id, chunk.filename, chunk.page), score)
                    )
        return sorted(matches, key=lambda item: (-item.score, item.citation.document_id))[:limit]
