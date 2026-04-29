from __future__ import annotations

import json
from typing import Dict, Optional

import keyring
import pytest

from tbc_agent.auth.credential_store import CredentialStore, is_token_expired


class InMemoryKeyring:
    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    def get_password(self, service: str, username: str) -> Optional[str]:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)

    def reset(self) -> None:
        self._store.clear()


@pytest.fixture(autouse=True)
def setup_keyring(monkeypatch):
    backend = InMemoryKeyring()

    def get_password(service: str, username: str) -> Optional[str]:
        return backend.get_password(service, username)

    def set_password(service: str, username: str, password: str) -> None:
        backend.set_password(service, username, password)

    def delete_password(service: str, username: str) -> None:
        backend.delete_password(service, username)

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", set_password)
    monkeypatch.setattr(keyring, "delete_password", delete_password)

    yield
    backend.reset()


def test_save_load_delete_roundtrip():
    store = CredentialStore(service_name="tbc-agent-test")
    scopes = ("scope1", "scope2")
    token = {"access_token": "abc", "expires_at": 1234567890}

    assert store.load("google", scopes) is None

    store.save("google", scopes, token)
    loaded = store.load("google", scopes)
    assert loaded == token

    store.delete("google", scopes)
    assert store.load("google", scopes) is None


def test_corrupted_json_is_removed():
    store = CredentialStore(service_name="tbc-agent-test")
    scopes = ("scope1",)
    entry = store._entry_name("google", scopes)
    keyring.set_password("tbc-agent-test", entry, "not-json")

    assert store.load("google", scopes) is None
    assert keyring.get_password("tbc-agent-test", entry) is None


def test_is_token_expired():
    past_token = {"expires_at": 0}
    future_token = {"expires_at": 9999999999}

    assert is_token_expired(past_token)
    assert not is_token_expired(future_token)
