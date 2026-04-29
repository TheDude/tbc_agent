"""Keyring-backed credential store for OAuth tokens."""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass
from typing import Optional

import keyring


@dataclass
class CredentialStore:
    """Persist OAuth token dictionaries using the system keyring."""

    service_name: str = "tbc-agent"

    def _scopes_key(self, scopes: tuple[str, ...]) -> str:
        """Return deterministic short hash for a scope set."""
        normalized = "\n".join(sorted(scopes))
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return digest[:12]

    def _entry_name(self, provider_id: str, scopes: tuple[str, ...]) -> str:
        suffix = self._scopes_key(scopes)
        return f"{provider_id}:{suffix}"

    def load(self, provider_id: str, scopes: tuple[str, ...]) -> Optional[dict]:
        username = self._entry_name(provider_id, scopes)
        raw = keyring.get_password(self.service_name, username)
        if raw is None:
            return None
        try:
            token_data = json.loads(raw)
        except json.JSONDecodeError:
            # Corrupted entry; remove and return None
            self.delete(provider_id, scopes)
            return None
        return token_data

    def save(self, provider_id: str, scopes: tuple[str, ...], token_data: dict) -> None:
        username = self._entry_name(provider_id, scopes)
        payload = json.dumps(token_data)
        keyring.set_password(self.service_name, username, payload)

    def delete(self, provider_id: str, scopes: tuple[str, ...]) -> None:
        username = self._entry_name(provider_id, scopes)
        try:
            keyring.delete_password(self.service_name, username)
        except keyring.errors.PasswordDeleteError:
            pass


def is_token_expired(token: dict, *, leeway: int = 60) -> bool:
    """Return True if token is expired (unix timestamps) within a leeway."""
    expires_at = token.get("expires_at")
    if expires_at is None:
        return False
    return expires_at <= time.time() + leeway
