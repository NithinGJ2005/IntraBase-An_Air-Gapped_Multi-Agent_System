"""Security Verification: Role and Permission Boundary Defenses."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from app.audit import InMemoryAuditSink
from app.auth.service import AuthenticationFailure, DevelopmentTokenAuthenticator, Identity
from app.config import Settings
from app.documents.service import DocumentIndexer
from app.orchestration.mcp import (
    DocumentSearchMCPTool,
    MCPAuthorizationError,
)


def make_settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "secret_key": "x" * 32,
        "dev_auth_signing_key": "k" * 32,
        "enable_development_auth": True,
        "role_permission_map": {
            "employee": ["chat:use", "documents:search"],
            "analyst": ["chat:use", "database:read"],
            "executive": ["chat:use", "documents:search", "database:read", "admin:diagnostics"],
        },
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_tampered_token_signature_rejected():
    """Verify forged JWT signatures are rejected without granting access."""
    cfg = make_settings()
    auth = DevelopmentTokenAuthenticator(cfg)

    # Valid token signed with correct key
    valid_token = jwt.encode(
        {"sub": "attacker", "roles": ["executive"], "aud": cfg.auth_audience, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        cfg.dev_auth_signing_key.get_secret_value(),
        algorithm="HS256",
    )

    # Token signed with a forged attacker key
    forged_token = jwt.encode(
        {"sub": "attacker", "roles": ["executive"], "aud": cfg.auth_audience, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "wrong_attacker_secret_key_at_least_32_characters_long",
        algorithm="HS256",
    )

    # Valid token succeeds
    identity = auth.authenticate(valid_token)
    assert identity.subject == "attacker"

    # Forged token fails
    with pytest.raises(AuthenticationFailure):
        auth.authenticate(forged_token)


def test_deny_by_default_role_permission_mapping():
    """Verify unmapped or unknown roles obtain zero permissions."""
    cfg = make_settings(role_permission_map={})  # Empty mapping
    auth = DevelopmentTokenAuthenticator(cfg)

    token = jwt.encode(
        {"sub": "employee-1", "roles": ["admin", "superuser", "root"], "aud": cfg.auth_audience, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        cfg.dev_auth_signing_key.get_secret_value(),
        algorithm="HS256",
    )

    identity = auth.authenticate(token)
    # Even though user claims "admin" and "superuser", server map is empty -> 0 permissions
    assert len(identity.permissions) == 0


def test_document_acl_cross_role_isolation(tmp_path: Path):
    """Verify users cannot access documents restricted to other roles."""
    exec_doc = tmp_path / "executive_compensation.txt"
    exec_doc.write_text("Executive bonus and stock option allocations.", encoding="utf-8")
    exec_doc.with_suffix(".txt.acl.json").write_text(
        json.dumps({"allowed_roles": ["executive"]}), encoding="utf-8"
    )

    indexer = DocumentIndexer([tmp_path], 100, 10)
    indexer.reindex()

    # Regular employee with documents:search permission, but role "employee"
    employee_identity = Identity("regular-emp", frozenset({"employee"}), frozenset({"documents:search"}))
    results = indexer.search("bonus", employee_identity)
    assert len(results) == 0

    # Executive identity with role "executive"
    exec_identity = Identity("ceo", frozenset({"executive"}), frozenset({"documents:search"}))
    exec_results = indexer.search("bonus", exec_identity)
    assert len(exec_results) == 1
    assert "bonus" in exec_results[0].content


def test_missing_or_malformed_acl_denies_access_by_default(tmp_path: Path):
    """Verify documents lacking valid ACL files are unreachable by any user."""
    unprotected_doc = tmp_path / "secret.txt"
    unprotected_doc.write_text("Unclassified confidential text", encoding="utf-8")
    # Intentionally omit .acl.json file

    indexer = DocumentIndexer([tmp_path], 100, 10)
    indexer.reindex()

    exec_identity = Identity("ceo", frozenset({"executive"}), frozenset({"documents:search"}))
    results = indexer.search("confidential", exec_identity)
    assert len(results) == 0
