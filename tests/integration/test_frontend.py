from starlette.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_frontend_index_and_static_assets():
    settings = Settings(
        _env_file=None,
        app_env="test",
        secret_key="z" * 32,
        dev_auth_signing_key="k" * 32,
        enable_development_auth=True,
    )
    app = create_app(settings)
    client = TestClient(app)

    # Root endpoint serves the React HTML shell
    response = client.get("/")
    assert response.status_code == 200
    assert "Enterprise Intranet Assistant" in response.text
    assert '<div id="root">' in response.text

    # Static CSS and JS files are served
    css_res = client.get("/static/styles.css")
    assert css_res.status_code == 200
    assert "--bg-primary" in css_res.text

    js_res = client.get("/static/app.js")
    assert js_res.status_code == 200
    assert "Enterprise Intranet Assistant" in js_res.text
