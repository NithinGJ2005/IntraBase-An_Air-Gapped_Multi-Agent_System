"""Validated, centralized application configuration."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AuthMode(str, Enum):
    DEVELOPMENT = "development"
    OIDC = "oidc"


ALLOWED_PERMISSIONS = frozenset(
    {"chat:use", "documents:search", "database:read", "admin:diagnostics"}
)


class Settings(BaseSettings):
    """Settings loaded only from environment variables or an explicitly supplied env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "Enterprise Intranet Assistant"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    secret_key: SecretStr = Field(min_length=32)
    enable_development_auth: bool = True
    auth_mode: AuthMode = AuthMode.DEVELOPMENT
    auth_audience: str = Field(default="enterprise-intranet-assistant", min_length=1)
    dev_auth_signing_key: SecretStr | None = None
    oidc_issuer: str | None = None
    oidc_jwks_url: str | None = None
    role_permission_map: dict[str, list[str]] = Field(default_factory=dict)
    audit_log_path: Path | None = None
    audit_retention_days: int = Field(default=365, ge=1)
    database_url: str | None = None
    database_read_only: bool = True
    database_query_timeout_seconds: int = Field(default=10, ge=1, le=300)
    database_max_result_rows: int = Field(default=100, ge=1, le=1000)
    document_roots: list[Path] = Field(default_factory=list)
    document_chunk_size: int = Field(default=800, ge=100, le=5000)
    document_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    llm_enabled: bool = False
    llm_base_url: str | None = None
    llm_allowed_hosts: list[str] = Field(default_factory=list)
    llm_model: str = Field(default="qwen3-4b-pending-license-review", min_length=1)
    llm_max_output_tokens: int = Field(default=512, ge=1, le=4096)
    llm_context_budget_tokens: int = Field(default=4096, ge=256, le=32768)
    llm_request_timeout_seconds: int = Field(default=60, ge=1, le=600)
    llm_max_concurrent_generations: int = Field(default=2, ge=1, le=256)
    llm_max_queue_depth: int = Field(default=10, ge=0, le=10000)
    llm_max_queue_wait_seconds: int = Field(default=30, ge=0, le=600)
    llm_internal_only: bool = True
    orchestration_max_iterations: int = Field(default=3, ge=1, le=10)

    @field_validator("role_permission_map")
    @classmethod
    def validate_role_permission_map(cls, role_map: dict[str, list[str]]) -> dict[str, list[str]]:
        invalid = {permission for values in role_map.values() for permission in values if permission not in ALLOWED_PERMISSIONS}
        if invalid:
            raise ValueError(f"ROLE_PERMISSION_MAP contains unsupported permissions: {sorted(invalid)}")
        return role_map

    @model_validator(mode="after")
    def production_security_invariants(self) -> "Settings":
        if self.app_env is Environment.PRODUCTION:
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.enable_development_auth:
                raise ValueError("ENABLE_DEVELOPMENT_AUTH must be false in production")
            if self.auth_mode is not AuthMode.OIDC:
                raise ValueError("AUTH_MODE must be oidc in production")
            if not all((self.oidc_issuer, self.oidc_jwks_url, self.audit_log_path)):
                raise ValueError("OIDC_ISSUER, OIDC_JWKS_URL, and AUDIT_LOG_PATH are required in production")
            if not self.oidc_issuer.startswith("https://") or not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("OIDC endpoints must use HTTPS in production")
            if not self.llm_enabled or not self.llm_base_url:
                raise ValueError("LLM_ENABLED=true and LLM_BASE_URL are required in production")
            if not self.llm_allowed_hosts:
                raise ValueError("LLM_ALLOWED_HOSTS is required in production")
        if self.auth_mode is AuthMode.DEVELOPMENT:
            if not self.enable_development_auth:
                raise ValueError("ENABLE_DEVELOPMENT_AUTH must be true when AUTH_MODE is development")
            if self.dev_auth_signing_key is None:
                raise ValueError("DEV_AUTH_SIGNING_KEY is required for development authentication")
        if not self.database_read_only:
            raise ValueError("DATABASE_READ_ONLY must remain true; write access is not supported")
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP must be smaller than DOCUMENT_CHUNK_SIZE")
        if self.llm_enabled and not self.llm_base_url:
            raise ValueError("LLM_BASE_URL is required when LLM_ENABLED is true")
        if self.llm_enabled:
            hostname = urlsplit(self.llm_base_url).hostname
            allowed_hosts = {host.lower() for host in self.llm_allowed_hosts}
            if not hostname or hostname.lower() not in allowed_hosts:
                raise ValueError("LLM_BASE_URL host must be listed in LLM_ALLOWED_HOSTS")
        if not self.llm_internal_only:
            raise ValueError("LLM_INTERNAL_ONLY must remain true")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings after validation."""
    return Settings()
