"""T3.20 – Manual validation of the live Google OAuth device flow.

This test exercises the real Authlib device-authorization loop against Google.
It requires valid OAuth client credentials and human interaction to approve
the device during the flow. Tokens are persisted to the configured OS keyring
(via the `keyring` library). Use `python -m keyring delete tbc-agent
<entry>` or Google Account security settings to revoke tokens after testing.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Tuple

import pytest

from tbc_agent.auth.credential_store import CredentialStore
from tbc_agent.auth.oauth_client import (
    AuthlibOauthClient,
    OauthAuthorizationDeclined,
    OauthConfigMissing,
    OauthRefreshFailed,
)

GOOGLE_DEFAULT_SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive.readonly",
)


@pytest.mark.manual
@pytest.mark.google_drive
def test_live_device_flow_requires_user_interaction(capsys):
    """Perform the Google device flow and persist tokens to the real keyring."""

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        pytest.skip(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set for manual device-flow test."
        )

    if os.getenv("CI"):
        pytest.skip("Manual OAuth device-flow test is skipped in CI environments.")

    scopes_env = os.getenv("GOOGLE_OAUTH_SCOPES")
    scopes: Tuple[str, ...]
    if scopes_env:
        scopes = tuple(scope.strip() for scope in scopes_env.split(" ") if scope.strip())
    else:
        scopes = GOOGLE_DEFAULT_SCOPES

    client = AuthlibOauthClient(
        provider_id="google",
        scopes=scopes,
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
    )

    banner = (
        "\n".join(
            [
                "================ MANUAL OAUTH DEVICE FLOW ================",
                "You are about to initiate the real Google OAuth device authorization flow.",
                "A browser URL and code will be printed below.",
                "Open the URL in your browser, log into the Google account to authorize,",
                "and then return here to continue.",
                "------------------------------------------------------------",
            ]
        )
    )
    print(banner, file=sys.stderr)

    try:
        token = client.ensure_token()
    except OauthConfigMissing as exc:
        pytest.fail(f"OAuth configuration missing: {exc}")
    except OauthAuthorizationDeclined as exc:
        pytest.fail(f"Device authorization declined: {exc}")
    except OauthRefreshFailed as exc:
        pytest.fail(f"Token refresh failed unexpectedly: {exc}")

    captured = capsys.readouterr()
    assert "Visit" in captured.err or "Complete OAuth2 Device Flow" in captured.err

    assert token.get("access_token"), "No access token returned from device flow"
    assert token.get("refresh_token"), "No refresh token returned from device flow"

    store = CredentialStore()
    stored = store.load("google", scopes)
    assert stored is not None, "Token was not persisted to keyring"
    assert stored.get("access_token"), "Persisted token missing access_token"

    before = time.time()
    refreshed = client.ensure_token()
    after = time.time()
    assert refreshed.get("access_token"), "Refresh did not return access_token"

    duration = after - before
    assert duration < 2, "Refresh should not require a second manual device interaction"

    print(
        "\n".join(
            [
                "------------------------------------------------------------",
                "Manual OAuth device flow completed successfully.",
                "Tokens are stored in the system keyring under service 'tbc-agent'.",
                "Run 'python -m keyring delete tbc-agent <entry>' to remove them,",
                "or revoke the app in Google Account security settings.",
                "============================================================",
            ]
        ),
        file=sys.stderr,
    )
