"""OAuth provider registry for tbc_agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class OAuthProvider:
    provider_id: str
    authorization_endpoint: str
    token_endpoint: str
    device_authorization_endpoint: str
    default_scopes: tuple[str, ...]


_PROVIDERS: Dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        provider_id="google",
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        device_authorization_endpoint="https://oauth2.googleapis.com/device/code",
        default_scopes=("https://www.googleapis.com/auth/drive.readonly",),
    ),
}


def get_provider(provider_id: str) -> OAuthProvider:
    """Return provider metadata or raise ValueError if missing."""

    try:
        return _PROVIDERS[provider_id]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unknown OAuth provider: {provider_id}") from exc
