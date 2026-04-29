from __future__ import annotations

import time
from typing import Dict, Tuple

import pytest

from tbc_agent.auth.oauth_client import (
    AuthlibOauthClient,
    CredentialStore,
    OauthAuthorizationDeclined,
    OauthConfigMissing,
    OauthRefreshFailed,
)


class DummyStore(CredentialStore):
    def __init__(self) -> None:
        super().__init__(service_name="tbc-agent-test")
        self._data: Dict[Tuple[str, Tuple[str, ...]], dict] = {}

    def load(self, provider_id: str, scopes: tuple[str, ...]) -> dict | None:
        return self._data.get((provider_id, scopes))

    def save(self, provider_id: str, scopes: tuple[str, ...], token_data: dict) -> None:
        self._data[(provider_id, scopes)] = token_data

    def delete(self, provider_id: str, scopes: tuple[str, ...]) -> None:
        self._data.pop((provider_id, scopes), None)


class DummySession:
    def __init__(self, *, refresh_result: dict | Exception | None = None, token_result: dict | Exception | None = None):
        self.refresh_result = refresh_result
        self.token_result = token_result
        self.device_called = False

    def device_authorization(self, endpoint: str) -> dict:
        self.device_called = True
        # Minimal response for device flow
        return {
            "device_code": "device-code",
            "user_code": "USER-CODE",
            "verification_uri": "https://example.com/verify",
            "interval": 0,
            "expires_in": 10,
        }

    def refresh_token(self, token_endpoint: str, refresh_token: str | None = None):
        if isinstance(self.refresh_result, Exception):
            raise self.refresh_result
        if self.refresh_result is None:
            raise RuntimeError("refresh called unexpectedly")
        return self.refresh_result

    def fetch_token(self, token_endpoint: str, grant_type: str, device_code: str, timeout: int):
        if isinstance(self.token_result, Exception):
            raise self.token_result
        if self.token_result is None:
            raise RuntimeError("fetch_token called unexpectedly")
        return self.token_result


@pytest.fixture(autouse=True)
def oauth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    yield
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)


def test_missing_environment_variables(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)

    client = AuthlibOauthClient(
        provider_id="google",
        scopes=("scope",),
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        credential_store=DummyStore(),
    )

    with pytest.raises(OauthConfigMissing):
        client.ensure_token()


def test_returns_existing_token(monkeypatch):
    store = DummyStore()
    token = {"access_token": "abc", "expires_at": time.time() + 3600}
    store.save("google", ("scope",), token)

    session = DummySession()
    monkeypatch.setattr(AuthlibOauthClient, "_create_session", lambda self, cid, secret: session)

    client = AuthlibOauthClient(
        provider_id="google",
        scopes=("scope",),
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        credential_store=store,
    )

    assert client.ensure_token() == token
    assert not session.device_called


def test_refreshes_expired_token(monkeypatch):
    store = DummyStore()
    old = {"access_token": "old", "refresh_token": "refresh", "expires_at": time.time() - 1}
    store.save("google", ("scope",), old)

    refreshed = {"access_token": "new", "refresh_token": "refresh", "expires_at": time.time() + 3600}
    session = DummySession(refresh_result=refreshed)
    monkeypatch.setattr(AuthlibOauthClient, "_create_session", lambda self, cid, secret: session)

    client = AuthlibOauthClient(
        provider_id="google",
        scopes=("scope",),
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        credential_store=store,
    )

    assert client.ensure_token() == refreshed
    assert store.load("google", ("scope",)) == refreshed


def test_refresh_failure_triggers_reauth(monkeypatch):
    store = DummyStore()
    old = {"access_token": "old", "refresh_token": "refresh", "expires_at": time.time() - 1}
    store.save("google", ("scope",), old)

    session = DummySession(refresh_result=RuntimeError("bad refresh"))
    monkeypatch.setattr(AuthlibOauthClient, "_create_session", lambda self, cid, secret: session)

    client = AuthlibOauthClient(
        provider_id="google",
        scopes=("scope",),
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        credential_store=store,
    )

    with pytest.raises(OauthRefreshFailed):
        client.ensure_token()
    assert store.load("google", ("scope",)) is None


def test_device_flow_saves_token(monkeypatch):
    store = DummyStore()
    session = DummySession(token_result={"access_token": "device", "expires_at": time.time() + 3600})
    monkeypatch.setattr(AuthlibOauthClient, "_create_session", lambda self, cid, secret: session)

    # Speed up polling by bypassing sleep; ensure fetch_token is called once
    def fetch_token(token_endpoint, grant_type, device_code, timeout):
        return session.token_result

    session.fetch_token = fetch_token  # type: ignore
    monkeypatch.setattr(time, "sleep", lambda _: None)

    client = AuthlibOauthClient(
        provider_id="google",
        scopes=("scope",),
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        credential_store=store,
    )

    token = client.ensure_token()
    assert token["access_token"] == "device"
    assert store.load("google", ("scope",)) == token
