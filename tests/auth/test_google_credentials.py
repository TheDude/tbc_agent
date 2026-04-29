from __future__ import annotations

import time

import pytest

from tbc_agent.auth.credential_store import CredentialStore
from tbc_agent.auth.google import get_google_drive_credentials
from tbc_agent.auth.oauth_client import AuthlibOauthClient


class DummyClient(AuthlibOauthClient):
    def __init__(self, token):
        self.token = token
        self.ensure_called = 0

    def ensure_token(self):
        self.ensure_called += 1
        return self.token


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    yield
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)


def test_get_drive_credentials(monkeypatch):
    expires_at = time.time() + 3600
    token = {
        "access_token": "abc",
        "refresh_token": "refresh",
        "expires_at": expires_at,
        "client_id": "client",
        "client_secret": "secret",
    }

    dummy = DummyClient(token)
    monkeypatch.setattr("tbc_agent.auth.google.AuthlibOauthClient", lambda **kwargs: dummy)

    creds = get_google_drive_credentials()
    assert creds.token == "abc"
    assert creds.refresh_token == "refresh"
    assert creds.expiry.timestamp() == pytest.approx(expires_at, rel=1e-3)

    dummy.token = {
        "access_token": "new",
        "refresh_token": "refresh",
        "expires_at": expires_at + 3600,
        "client_id": "client",
        "client_secret": "secret",
    }

    creds.refresh(None)
    assert dummy.ensure_called == 2
    assert creds.token == "new"
