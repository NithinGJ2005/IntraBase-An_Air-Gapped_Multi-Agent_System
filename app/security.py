"""FastAPI dependencies that enforce identity and permissions on the server."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from app.audit import AuditSink, new_event
from app.auth.service import AuthenticationFailure, Identity, bearer_token


class AuthorizationFailure(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


def current_identity(request: Request) -> Identity:
    try:
        identity = request.app.state.authenticator.authenticate(bearer_token(request))
    except AuthenticationFailure as error:
        request.app.state.audit_sink.record(
            new_event("authentication", "denied", request.state.request_id, resource=request.url.path)
        )
        raise AuthorizationFailure(401, "Authentication required") from error
    request.app.state.audit_sink.record(
        new_event("authentication", "allowed", request.state.request_id, identity.subject, request.url.path)
    )
    return identity


def require_permission(permission: str) -> Callable[[Request], Identity]:
    def dependency(request: Request) -> Identity:
        identity = current_identity(request)
        decision = "allowed" if permission in identity.permissions else "denied"
        request.app.state.audit_sink.record(
            new_event(
                "authorization",
                decision,
                request.state.request_id,
                identity.subject,
                f"{request.url.path}:{permission}",
            )
        )
        if decision == "denied":
            raise AuthorizationFailure(403, "Permission denied")
        return identity

    return dependency
