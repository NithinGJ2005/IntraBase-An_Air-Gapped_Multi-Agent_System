import json
from types import SimpleNamespace

from app.config import Settings
from app.main import create_app, safe_error_response


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key="a" * 32,
        dev_auth_signing_key="b" * 32,
        enable_development_auth=True,
    )
    return TestClient(create_app(settings))


def complete(coroutine):
    """Execute coroutines that intentionally contain no await points."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Health handlers must not perform asynchronous I/O")


def route(app, path):
    return next(item.endpoint for item in app.routes if item.path == path)


def request(request_id: str):
    return SimpleNamespace(state=SimpleNamespace(request_id=request_id))


def test_liveness_includes_request_id():
    app = create_app(make_settings())
    response = complete(route(app, "/health/live")(request("request-123")))
    assert response.status == "alive"
    assert response.request_id == "request-123"


def test_readiness_when_started():
    app = create_app(make_settings())
    app.state.ready = True
    response = complete(route(app, "/health/ready")(request("request-123")))
    assert response.status == "ready"


def test_unhandled_errors_are_safe():
    response = safe_error_response(500, "internal_error", "An unexpected error occurred.", "request-123")
    assert response.status_code == 500
    payload = json.loads(response.body)
    assert payload["error"] == "internal_error"
    assert "password" not in response.body.decode()
