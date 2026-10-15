# Document Retrieval Guide

## Configuration and access policy

Set `DOCUMENT_ROOTS` to a JSON list of administrator-approved internal directories. The indexer resolves each root and indexes only PDF, TXT, Markdown, and `.markdown` files inside it. Symbolic links are skipped and files resolving outside an approved root are rejected.

Each indexed file needs an adjacent administrator-managed ACL, for example `benefits.pdf.acl.json`:

```json
{"allowed_roles":["employee"]}
```

Missing or malformed ACL files deny retrieval. Roles come from verified authentication claims and the server-side mapping; client input does not control document access.

## Current retrieval behavior

The initial implementation hashes files, reuses unchanged indexed chunks during re-indexing, removes deleted files, extracts PDF pages with PyMuPDF, chunks text with configurable overlap, and ranks lexical token matches. Authorization filtering occurs before any content is returned. Citations expose only filename, safe document ID, and PDF page number—not absolute paths.

Embedding retrieval is intentionally deferred. Model and embedding assets must be pre-staged internally and must never download during application startup.
