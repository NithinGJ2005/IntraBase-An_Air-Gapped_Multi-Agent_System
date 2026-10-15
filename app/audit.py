"""Minimal, privacy-preserving audit event recording."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    action: str
    decision: str
    request_id: str
    actor: str | None = None
    resource: str | None = None


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Non-persistent sink reserved for tests and local development."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class JsonlAuditSink:
    """Append-only JSONL audit sink; deployment must protect the target directory."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()

    def record(self, event: AuditEvent) -> None:
        line = json.dumps(asdict(event), separators=(",", ":")) + "\n"
        with self._lock, self._path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(line)


def new_event(
    action: str, decision: str, request_id: str, actor: str | None = None, resource: str | None = None
) -> AuditEvent:
    return AuditEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        action=action,
        decision=decision,
        request_id=request_id,
        actor=actor,
        resource=resource,
    )
