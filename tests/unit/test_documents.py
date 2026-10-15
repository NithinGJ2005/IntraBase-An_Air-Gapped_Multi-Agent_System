import json
from pathlib import Path

import fitz

from app.auth.service import Identity
from app.documents.service import DocumentIndexer


def write_document(root: Path, name: str, text: str, roles: list[str]) -> Path:
    document = root / name
    document.write_text(text, encoding="utf-8")
    document.with_suffix(document.suffix + ".acl.json").write_text(
        json.dumps({"allowed_roles": roles}), encoding="utf-8"
    )
    return document


def identity(*roles: str, permissions: set[str] | None = None) -> Identity:
    effective_permissions = {"documents:search"} if permissions is None else permissions
    return Identity("employee-1", frozenset(roles), frozenset(effective_permissions))


def test_lexical_search_filters_document_acl_and_returns_safe_citation(tmp_path: Path):
    write_document(tmp_path, "benefits.md", "Health benefits include dental cover.", ["employee"])
    write_document(tmp_path, "payroll.txt", "Salary adjustment information.", ["finance"])
    index = DocumentIndexer([tmp_path], 80, 10)
    index.reindex()
    results = index.search("health benefits", identity("employee"))
    assert len(results) == 1
    assert results[0].citation.filename == "benefits.md"
    assert str(tmp_path) not in results[0].content


def test_missing_acl_is_denied_and_deleted_documents_are_removed(tmp_path: Path):
    document = write_document(tmp_path, "policy.txt", "Remote work policy", ["employee"])
    index = DocumentIndexer([tmp_path], 80, 10)
    index.reindex()
    assert index.search("remote work", identity("employee"))
    document.unlink()
    document.with_suffix(document.suffix + ".acl.json").unlink()
    index.reindex()
    assert not index.search("remote work", identity("employee"))


def test_acl_change_invalidates_reused_document(tmp_path: Path):
    document = write_document(tmp_path, "plan.txt", "Confidential roadmap", ["employee"])
    index = DocumentIndexer([tmp_path], 80, 10)
    index.reindex()
    assert index.search("roadmap", identity("employee"))
    document.with_suffix(document.suffix + ".acl.json").write_text(
        json.dumps({"allowed_roles": ["executive"]}), encoding="utf-8"
    )
    report = index.reindex()
    assert report.indexed_documents == 1
    assert not index.search("roadmap", identity("employee"))


def test_unauthorized_or_unpermitted_identity_receives_no_content(tmp_path: Path):
    write_document(tmp_path, "restricted.txt", "Acquisition strategy", ["executive"])
    index = DocumentIndexer([tmp_path], 80, 10)
    index.reindex()
    assert not index.search("acquisition", identity("employee"))
    assert not index.search("acquisition", identity("executive", permissions=set()))


def test_pdf_extraction_includes_page_number(tmp_path: Path):
    document = tmp_path / "guide.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Incident response guide")
    pdf.save(document)
    pdf.close()
    document.with_suffix(".pdf.acl.json").write_text(json.dumps({"allowed_roles": ["employee"]}), encoding="utf-8")
    index = DocumentIndexer([tmp_path], 80, 10)
    index.reindex()
    results = index.search("incident response", identity("employee"))
    assert results[0].citation.page == 1
