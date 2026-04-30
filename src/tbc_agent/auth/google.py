"""Google-specific helpers for OAuth2 credentials."""

from __future__ import annotations

import os

from typing import Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from tbc_agent.auth.credential_store import CredentialStore
from tbc_agent.auth.oauth_client import (
    AuthlibOauthClient,
    OauthAuthorizationDeclined,
    OauthConfigMissing,
    OauthRefreshFailed,
)
from tbc_agent.auth.oauth_registry import get_provider

_DRIVE_SCOPES: Tuple[str, ...] = ("https://www.googleapis.com/auth/drive.readonly",)


def _build_credentials(token: dict) -> Credentials:
    provider = get_provider("google")
    creds = Credentials(
        token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_uri=provider.token_endpoint,
        client_id=token.get("client_id"),
        client_secret=token.get("client_secret"),
        scopes=list(_DRIVE_SCOPES),
    )
    # Authlib tokens include expires_in; convert to expiry for google creds
    if "expires_at" in token and hasattr(creds, "expiry"):
        from datetime import datetime, timezone

        creds.expiry = datetime.fromtimestamp(token["expires_at"], tz=timezone.utc)
    return creds


def get_google_drive_credentials(store: CredentialStore | None = None) -> Credentials:
    client = AuthlibOauthClient(
        provider_id="google",
        scopes=_DRIVE_SCOPES,
        client_id_env="GOOGLE_OAUTH_CLIENT_ID",
        client_secret_env="GOOGLE_OAUTH_CLIENT_SECRET",
        credential_store=store,
    )

    token = client.ensure_token()

    creds = _build_credentials(token)

    def refresh(request: Request) -> None:
        refreshed = client.ensure_token()
        new_creds = _build_credentials(refreshed)
        creds.token = new_creds.token
        if new_creds.refresh_token:
            # refresh_token property is read-only; update internal _refresh_token
            creds._refresh_token = new_creds.refresh_token  # type: ignore[attr-defined]
        creds.expiry = new_creds.expiry

    creds.refresh = refresh  # type: ignore[assignment]
    return creds
