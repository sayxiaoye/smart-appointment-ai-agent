"""登录 cookie 和认证路由。"""

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["SKIP_SYSTEM_INIT"] = "1"


@pytest.fixture
def client():
    import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_env_example_has_placeholder_session_secret():
    text = Path(".env.example").read_text(encoding="utf-8")
    secret_lines = [line for line in text.splitlines() if line.startswith("SESSION_SECRET=")]
    assert secret_lines == ["SESSION_SECRET=replace_with_a_long_random_string"]


def test_app_refuses_to_start_without_session_secret(monkeypatch):
    import app as app_module
    from config.session_secret import SESSION_SECRET_PLACEHOLDER, require_session_secret

    monkeypatch.setenv("SESSION_SECRET", SESSION_SECRET_PLACEHOLDER)
    with pytest.raises(RuntimeError):
        require_session_secret()

    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setattr(app_module, "load_dotenv", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError):
        app_module.create_app()


def test_register_login_wrong_password_and_logout(client):
    username = "cookie-" + uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={"username": username, "password": "long-enough", "display_name": "小林"},
    )
    assert registered.status_code == 200
    assert registered.json()["username"] == username
    assert registered.json()["display_name"] == "小林"

    me = client.get("/api/auth/me")
    assert me.json()["authenticated"] is True
    assert me.json()["display_name"] == "小林"
    assert "password" not in me.text

    client.post("/api/auth/logout")
    logged_out = client.get("/api/auth/me")
    assert logged_out.json() == {"authenticated": False}
    assert "display_name" not in logged_out.json()

    wrong = client.post(
        "/api/auth/login",
        json={"username": username, "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert client.get("/api/auth/me").json()["authenticated"] is False

    again = client.post(
        "/api/auth/login",
        json={"username": username, "password": "long-enough"},
    )
    assert again.status_code == 200
    assert client.get("/api/auth/me").json()["display_name"] == "小林"

    duplicate = client.post(
        "/api/auth/register",
        json={"username": username, "password": "long-enough", "display_name": "另一个"},
    )
    assert duplicate.status_code == 409
