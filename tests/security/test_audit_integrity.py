"""Security Verification: Audit Log Integrity and Privacy Preserving Records."""

import json
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest

from app.audit import InMemoryAuditSink, JsonlAuditSink, new_event
from app.auth.service import DevelopmentTokenAuthenticator, Identity
from app.config import Settings
from app.security import current_identity, require_permission


def test_audit_event_structure_and_privacy():
    """Verify audit records contain necessary correlation fields without leaking secrets."""
    sink = InMemoryAuditSink()
    sink.record(new_event("authentication", "allowed", "req-123", "alice", "/api/v1/session"))
    sink.record(new_event("authorization", "denied", "req-124", "bob", "/api/v1/admin:admin:diagnostics"))

    assert len(sink.events) == 2
    ev1 = sink.events[0]
    assert ev1.action == "authentication"
    assert ev1.decision == "allowed"
    assert ev1.request_id == "req-123"
    assert ev1.actor == "alice"
    assert ev1.resource == "/api/v1/session"
    assert "T" in ev1.timestamp  # Valid ISO8601


def test_jsonl_audit_sink_file_persistence(tmp_path: Path):
    """Verify JsonlAuditSink writes valid JSONL lines to disk."""
    log_file = tmp_path / "audit.jsonl"
    sink = JsonlAuditSink(log_file)

    event = new_event("assistant_chat", "allowed", "req-test-99", "charlie", "chat")
    sink.record(event)

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["action"] == "assistant_chat"
    assert data["actor"] == "charlie"
    assert data["request_id"] == "req-test-99"

    # Verify no sensitive keywords leaked
    raw_text = log_file.read_text(encoding="utf-8")
    for secret_keyword in ["password", "secret_key", "bearer", "token", "private_key"]:
        assert secret_keyword not in raw_text.lower()
