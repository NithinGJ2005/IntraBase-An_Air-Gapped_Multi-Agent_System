"""Security Verification: Production Configuration and Air-Gap Invariants."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Environment, Settings


def prod_baseline(**overrides) -> dict:
    baseline = {
        "app_env": "production",
        "secret_key": "x" * 32,
        "debug": False,
        "enable_development_auth": False,
        "auth_mode": "oidc",
        "oidc_issuer": "https://idp.internal.org/auth",
        "oidc_jwks_url": "https://idp.internal.org/auth/.well-known/jwks.json",
        "audit_log_path": Path("/var/log/app/audit.jsonl"),
        "llm_enabled": True,
        "llm_base_url": "http://llm-service:8000/v1",
        "llm_allowed_hosts": ["llm-service"],
        "llm_internal_only": True,
        "database_read_only": True,
    }
    baseline.update(overrides)
    return baseline


def test_production_accepts_valid_hardening_config():
    """Verify compliant production configuration loads without error."""
    cfg = Settings(_env_file=None, **prod_baseline())
    assert cfg.app_env is Environment.PRODUCTION
    assert cfg.enable_development_auth is False
    assert cfg.llm_internal_only is True


def test_production_rejects_debug_mode():
    with pytest.raises(ValidationError, match="DEBUG must be false in production"):
        Settings(_env_file=None, **prod_baseline(debug=True))


def test_production_rejects_development_auth():
    with pytest.raises(ValidationError, match="ENABLE_DEVELOPMENT_AUTH must be false in production"):
        Settings(_env_file=None, **prod_baseline(enable_development_auth=True))


def test_production_rejects_non_https_oidc():
    with pytest.raises(ValidationError, match="OIDC endpoints must use HTTPS"):
        Settings(_env_file=None, **prod_baseline(oidc_issuer="http://insecure-idp.org"))


def test_production_rejects_database_write_mode():
    with pytest.raises(ValidationError, match="DATABASE_READ_ONLY must remain true"):
        Settings(_env_file=None, **prod_baseline(database_read_only=False))


def test_production_rejects_external_llm_mode():
    with pytest.raises(ValidationError, match="LLM_INTERNAL_ONLY must remain true"):
        Settings(_env_file=None, **prod_baseline(llm_internal_only=False))


def test_production_rejects_unapproved_llm_host():
    with pytest.raises(ValidationError, match="LLM_BASE_URL host must be listed in LLM_ALLOWED_HOSTS"):
        Settings(_env_file=None, **prod_baseline(llm_allowed_hosts=["different-host"]))
