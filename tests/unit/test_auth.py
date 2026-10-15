from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest

from app.audit import InMemoryAuditSink
from app.auth.service import AuthenticationFailure, DevelopmentTokenAuthenticator
from app.config import Settings
from app.security import AuthorizationFailure, current_identity, require_permission


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key="a" * 32,
        dev_auth_signing_key="b" * 32,
        role_permission_map={"employee": ["chat:use", "documents:search"], "admin": ["admin:diagnostics"]},
    )


def token(subject: str, roles: list[str], expires_in_minutes: int = 5) -> str:
    configured = settings()
    return jwt.encode(
        {
            "sub": subject,
            "roles": roles,
            "aud": configured.auth_audience,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
        },
        configured.dev_auth_signing_key.get_secret_value(),
        algorithm="HS256",
    )


def request(bearer: str | None, configured: Settings | None = None):
    configured = configured or settings()
    app = SimpleNamespace(
        state=SimpleNamespace(
            authenticator=DevelopmentTokenAuthenticator(configured), audit_sink=InMemoryAuditSink()
        )
    )
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return SimpleNamespace(
        app=app,
        headers=headers,
        state=SimpleNamespace(request_id="request-123"),
        url=SimpleNamespace(path="/api/v1/session"),
    )


def test_verified_token_maps_server_side_role_permissions():
    identity = DevelopmentTokenAuthenticator(settings()).authenticate(token("employee-1", ["employee"]))
    assert identity.subject == "employee-1"
    assert identity.permissions == frozenset({"chat:use", "documents:search"})


def test_expired_token_is_rejected():
    with pytest.raises(AuthenticationFailure):
        DevelopmentTokenAuthenticator(settings()).authenticate(token("employee-1", ["employee"], -1))


def test_missing_token_is_audited_and_rejected():
    request_without_token = request(None)
    with pytest.raises(AuthorizationFailure) as error:
        current_identity(request_without_token)
    assert error.value.status_code == 401
    event = request_without_token.app.state.audit_sink.events[0]
    assert event.action == "authentication"
    assert event.decision == "denied"


def test_permission_boundary_is_audited_and_enforced():
    employee_request = request(token("employee-1", ["employee"]))
    with pytest.raises(AuthorizationFailure) as error:
        require_permission("database:read")(employee_request)
    assert error.value.status_code == 403
    assert employee_request.app.state.audit_sink.events[-1].decision == "denied"
