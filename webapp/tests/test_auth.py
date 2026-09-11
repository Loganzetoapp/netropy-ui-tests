"""Tests for the optional login gate that protects the dashboard once it's
shared beyond localhost. Run with:
    pytest --confcutdir=webapp webapp/tests/test_auth.py -v
"""
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapp.app import (
    BasicAuthMiddleware,
    _check_basic_auth,
    _is_loopback_host,
    _validate_sharing_config,
)


def _basic_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def test_is_loopback_host():
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("192.168.1.50")


def test_check_basic_auth_accepts_correct_credentials():
    assert _check_basic_auth(_basic_header("alice", "hunter2"), "alice", "hunter2")


def test_check_basic_auth_rejects_wrong_password():
    assert not _check_basic_auth(_basic_header("alice", "wrong"), "alice", "hunter2")


def test_check_basic_auth_rejects_wrong_user():
    assert not _check_basic_auth(_basic_header("mallory", "hunter2"), "alice", "hunter2")


def test_check_basic_auth_rejects_missing_header():
    assert not _check_basic_auth(None, "alice", "hunter2")


def test_check_basic_auth_rejects_non_basic_scheme():
    assert not _check_basic_auth("Bearer sometoken", "alice", "hunter2")


def test_check_basic_auth_rejects_malformed_base64():
    assert not _check_basic_auth("Basic not-valid-base64!!!", "alice", "hunter2")


def test_validate_sharing_config_allows_loopback_without_credentials():
    _validate_sharing_config("127.0.0.1", None, None)  # must not raise


def test_validate_sharing_config_allows_non_loopback_with_credentials():
    _validate_sharing_config("0.0.0.0", "alice", "hunter2")  # must not raise


def test_validate_sharing_config_refuses_non_loopback_without_credentials():
    with pytest.raises(SystemExit):
        _validate_sharing_config("0.0.0.0", None, None)


def test_validate_sharing_config_refuses_non_loopback_with_only_user():
    with pytest.raises(SystemExit):
        _validate_sharing_config("0.0.0.0", "alice", None)


def _protected_test_app() -> FastAPI:
    """A standalone app with the middleware wired in — deliberately not
    webapp.app's own module-level `app`, so this never mutates the shared
    singleton other test files import via `TestClient(app_module.app)`."""
    app = FastAPI()

    @app.get("/secret")
    def secret():
        return {"ok": True}

    app.add_middleware(BasicAuthMiddleware, user="alice", password="hunter2")
    return app


def test_middleware_blocks_unauthenticated_request():
    client = TestClient(_protected_test_app())
    resp = client.get("/secret")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Basic")


def test_middleware_allows_correct_credentials():
    client = TestClient(_protected_test_app())
    resp = client.get("/secret", headers={"Authorization": _basic_header("alice", "hunter2")})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_middleware_rejects_wrong_credentials():
    client = TestClient(_protected_test_app())
    resp = client.get("/secret", headers={"Authorization": _basic_header("alice", "wrong")})
    assert resp.status_code == 401
