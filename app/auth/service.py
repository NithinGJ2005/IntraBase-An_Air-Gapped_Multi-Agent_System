"""Verified-token authentication and deny-by-default authorization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from fastapi import Request

from app.config import AuthMode, Settings


class AuthenticationFailure(Exception):
    """Raised when no valid, verified identity can be established."""


@dataclass(frozen=True)
class Identity:
    subject: str
    roles: frozenset[str]
    permissions: frozenset[str]


class Authenticator(Protocol):
    def authenticate(self, token: str) -> Identity: ...


def _string_set(value: Any) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return frozenset()
    return frozenset(value)


def _identity_from_claims(claims: dict[str, Any], settings: Settings) -> Identity:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthenticationFailure("Token subject is missing")
    roles = _string_set(claims.get("roles", []))
    permissions = frozenset(
        permission for role in roles for permission in settings.role_permission_map.get(role, [])
    )
    return Identity(subject=subject, roles=roles, permissions=permissions)


class DevelopmentTokenAuthenticator:
    """Development-only HS256 adapter, never permitted in production settings."""

    def __init__(self, settings: Settings) -> None:
        if settings.dev_auth_signing_key is None:
            raise RuntimeError("Development authentication key is not configured")
        self._key = settings.dev_auth_signing_key.get_secret_value()
        self._audience = settings.auth_audience
        self._settings = settings

    def authenticate(self, token: str) -> Identity:
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=["HS256"],
                audience=self._audience,
                options={"require": ["exp", "sub", "aud"]},
            )
        except jwt.PyJWTError as error:
            raise AuthenticationFailure("Invalid development token") from error
        return _identity_from_claims(claims, self._settings)


class OIDCAuthenticator:
    """OIDC adapter that validates signed tokens against the configured internal IdP."""

    def __init__(self, settings: Settings) -> None:
        if not all((settings.oidc_issuer, settings.oidc_jwks_url)):
            raise RuntimeError("OIDC settings are incomplete")
        self._issuer = settings.oidc_issuer
        self._audience = settings.auth_audience
        self._jwks_client = jwt.PyJWKClient(settings.oidc_jwks_url)
        self._settings = settings

    def authenticate(self, token: str) -> Identity:
        try:
            key = self._jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as error:
            raise AuthenticationFailure("Invalid OIDC token") from error
        return _identity_from_claims(claims, self._settings)


def build_authenticator(settings: Settings) -> Authenticator:
    if settings.auth_mode is AuthMode.DEVELOPMENT:
        return DevelopmentTokenAuthenticator(settings)
    return OIDCAuthenticator(settings)


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationFailure("Bearer token is required")
    return token
