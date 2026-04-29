from __future__ import annotations

import json

import pytest

from tbc_agent.tools.google_drive import _get_drive_service, _reset_drive_service


class DummyService:
    def __init__(self, name):
        self.name = name


@pytest.fixture(autouse=True)
def reset_drive():
    _reset_drive_service()
    yield
    _reset_drive_service()


def test_oauth_success(monkeypatch):
    service = DummyService("oauth")
    monkeypatch.setattr("tbc_agent.tools.google_drive.get_google_drive_credentials", lambda: "creds")
    monkeypatch.setattr("tbc_agent.tools.google_drive.build", lambda *args, **kwargs: service)

    result = _get_drive_service()
    assert result is service


def test_fallback_to_service_account(monkeypatch):
    service = DummyService("service-account")
    monkeypatch.setattr("tbc_agent.tools.google_drive.get_google_drive_credentials", lambda: (_ for _ in ()).throw(RuntimeError("oauth fail")))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", json.dumps({"type": "service_account"}))

    monkeypatch.setattr(
        "tbc_agent.tools.google_drive.service_account.Credentials.from_service_account_info",
        classmethod(lambda cls, info, scopes: "svc-creds"),
    )
    monkeypatch.setattr("tbc_agent.tools.google_drive.build", lambda *args, **kwargs: service)

    result = _get_drive_service()
    assert result is service


def test_both_methods_fail(monkeypatch):
    monkeypatch.setattr("tbc_agent.tools.google_drive.get_google_drive_credentials", lambda: (_ for _ in ()).throw(RuntimeError("oauth fail")))
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", raising=False)

    with pytest.raises(RuntimeError):
        _get_drive_service()
