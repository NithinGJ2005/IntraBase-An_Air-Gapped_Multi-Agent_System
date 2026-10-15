import pytest
from pydantic import ValidationError

from app.config import Environment, Settings


def values(**overrides):
    baseline = {
        "secret_key": "a" * 32,
        "dev_auth_signing_key": "b" * 32,
        "app_env": "test",
        "enable_development_auth": True,
    }
    baseline.update(overrides)
    return baseline


def test_settings_accepts_test_environment():
    settings = Settings(_env_file=None, **values())
    assert settings.app_env is Environment.TEST


def test_settings_rejects_short_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values(secret_key="short"))


def test_production_rejects_development_auth():
    with pytest.raises(ValidationError, match="ENABLE_DEVELOPMENT_AUTH"):
        Settings(_env_file=None, **values(app_env="production"))


def test_production_rejects_debug():
    with pytest.raises(ValidationError, match="DEBUG"):
        Settings(
            _env_file=None,
            **values(app_env="production", enable_development_auth=False, debug=True),
        )
