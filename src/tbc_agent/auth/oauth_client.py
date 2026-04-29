"""Authlib-based OAuth2 device flow client for tbc_agent."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional

from authlib.integrations.requests_client import OAuth2Session

from tbc_agent.auth.credential_store import CredentialStore, is_token_expired
from tbc_agent.auth.oauth_registry import OAuthProvider, get_provider


class OauthError(RuntimeError):
    """Base class for OAuth-related errors."""


class OauthConfigMissing(OauthError):
    """Raised when required OAuth configuration is absent."""


class OauthAuthorizationDeclined(OauthError):
    """Raised when user declined or failed device authorization."""


class OauthRefreshFailed(OauthError):
    """Raised when refresh could not complete successfully."""


@dataclass
class AuthlibOauthClient:
    provider_id: str
    scopes: tuple[str, ...]
    client_id_env: str
    client_secret_env: str
    credential_store: CredentialStore | None = None

    def __post_init__(self) -> None:
        self.provider: OAuthProvider = get_provider(self.provider_id)
        self.store = self.credential_store or CredentialStore()

    def _env_value(self, name: str) -> str:
        from os import getenv

        value = getenv(name)
        if not value:
            raise OauthConfigMissing(
                f"Environment variable {name} must be set for OAuth provider {self.provider_id}."
            )
        return value

    def _create_session(self, client_id: str, client_secret: str) -> OAuth2Session:
        return OAuth2Session(
            client_id=client_id,
            client_secret=client_secret,
            scope=" ".join(self.scopes),
        )

    def _device_flow(self, session: OAuth2Session) -> Dict:
        metadata = session.device_authorization(self.provider.device_authorization_endpoint)
        user_code = metadata.get("user_code")
        verification_uri = metadata.get("verification_uri")
        verification_uri_complete = metadata.get("verification_uri_complete")
        expires_in = metadata.get("expires_in")
        interval = metadata.get("interval", 5)

        msg_lines = ["Complete OAuth2 Device Flow:"]
        if verification_uri_complete:
            msg_lines.append(f"  Visit: {verification_uri_complete}")
        elif verification_uri and user_code:
            msg_lines.append(f"  Visit: {verification_uri}")
            msg_lines.append(f"  Enter code: {user_code}")
        else:
            msg_lines.append("  Follow Device Flow instructions in browser.")
        if expires_in:
            msg_lines.append(f"  Code expires in {expires_in} seconds.")
        print("\n".join(msg_lines), file=sys.stderr)

        device_code = metadata["device_code"]
        token_endpoint = self.provider.token_endpoint
        start = time.time()

        while True:
            try:
                token = session.fetch_token(
                    token_endpoint,
                    grant_type="urn:ietf:params:oauth:grant-type:device_code",
                    device_code=device_code,
                    timeout=30,
                )
                break
            except Exception as exc:  # pragma: no cover - depends on HTTP errors
                if "authorization_pending" in str(exc) or "slow_down" in str(exc):
                    if "slow_down" in str(exc):
                        interval += 5
                    time.sleep(interval)
                    continue
                if "access_denied" in str(exc):
                    raise OauthAuthorizationDeclined(str(exc)) from exc
                raise

            if expires_in and time.time() - start > expires_in:
                raise OauthAuthorizationDeclined("Device authorization expired before completion")

        return token

    def ensure_token(self) -> Dict:
        client_id = self._env_value(self.client_id_env)
        client_secret = self._env_value(self.client_secret_env)
        session = self._create_session(client_id, client_secret)

        token = self.store.load(self.provider_id, self.scopes)
        if token and not is_token_expired(token):
            return token

        if token and is_token_expired(token):
            try:
                refreshed = session.refresh_token(
                    self.provider.token_endpoint,
                    refresh_token=token.get("refresh_token"),
                )
                self.store.save(self.provider_id, self.scopes, refreshed)
                return refreshed
            except Exception as exc:  # pragma: no cover - network dependent
                self.store.delete(self.provider_id, self.scopes)
                raise OauthRefreshFailed(str(exc)) from exc

        token = self._device_flow(session)
        self.store.save(self.provider_id, self.scopes, token)
        return token
