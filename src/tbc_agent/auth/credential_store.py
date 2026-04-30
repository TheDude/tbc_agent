"""Bitwarden-backed credential store for OAuth tokens."""

from __future__ import annotations

import json
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Optional

from bitwarden_sdk import BitwardenClient
from bitwarden_sdk.identity import IdentityClient
from bitwarden_sdk.generated import Item

_CLIENT: Optional[BitwardenClient] = None


def _get_client() -> BitwardenClient:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    access_token = os.environ.get("BWS_ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError("BWS_ACCESS_TOKEN environment variable is required for Bitwarden access.")

    client = BitwardenClient(access_token)
    _CLIENT = client
    return client


@dataclass
class CredentialStore:
    """Persist OAuth token dictionaries using Bitwarden secure notes."""

    item_id: str

    def _scopes_key(self, scopes: tuple[str, ...]) -> str:
        normalized = "\n".join(sorted(scopes))
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return digest[:12]

    def _entry_key(self, provider_id: str, scopes: tuple[str, ...]) -> str:
        suffix = self._scopes_key(scopes)
        return f"{provider_id}:{suffix}"

    def _fetch_item(self) -> Item:
        client = _get_client()
        identity = IdentityClient(client)
        response = identity.items().get(self.item_id)
        if response.data is None:
            raise RuntimeError(f"Bitwarden item {self.item_id} not found")
        return response.data

    def load(self, provider_id: str, scopes: tuple[str, ...]) -> Optional[dict]:
        key = self._entry_key(provider_id, scopes)
        item = self._fetch_item()
        if item.fields:
            for field in item.fields:
                if field.name == key and field.value:
                    try:
                        return json.loads(field.value)
                    except json.JSONDecodeError:
                        return None
        if item.notes and key in item.notes:
            try:
                return json.loads(item.notes)
            except json.JSONDecodeError:
                return None
        return None

    def save(self, provider_id: str, scopes: tuple[str, ...], token_data: dict) -> None:
        key = self._entry_key(provider_id, scopes)
        item = self._fetch_item()
        payload = json.dumps(token_data)

        updated = False
        if item.fields:
            for field in item.fields:
                if field.name == key:
                    field.value = payload
                    updated = True
                    break
        if not updated:
            from bitwarden_sdk.generated import ItemField, ItemFieldType

            field = ItemField(name=key, value=payload, type=ItemFieldType.Text)
            if item.fields:
                item.fields.append(field)
            else:
                item.fields = [field]

        client = _get_client()
        identity = IdentityClient(client)
        identity.items().put(self.item_id, item)

    def delete(self, provider_id: str, scopes: tuple[str, ...]) -> None:
        key = self._entry_key(provider_id, scopes)
        item = self._fetch_item()
        if item.fields:
            item.fields = [field for field in item.fields if field.name != key]
            client = _get_client()
            identity = IdentityClient(client)
            identity.items().put(self.item_id, item)


def is_token_expired(token: dict, *, leeway: int = 60) -> bool:
    expires_at = token.get("expires_at")
    if expires_at is None:
        return False
    return expires_at <= time.time() + leeway
