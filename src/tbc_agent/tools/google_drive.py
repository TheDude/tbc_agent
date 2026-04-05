"""
Tool: google_drive — search, inspect, and read files from Google Drive.

Requires the GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable to point to
a Google service account JSON key file. The service account must have been
granted access (read) to the Drive files it needs to reach.
"""

import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from pydantic_ai import Tool

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

_EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

_MAX_FILE_SIZE_BYTES = 512_000   # 500 KB pre-download guard
_MAX_CONTENT_CHARS = 100_000     # post-download truncation

_drive_service = None


def _get_drive_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if not key_file:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable is not set. "
            "Provide the path to a service account JSON key file."
        )

    credentials = service_account.Credentials.from_service_account_file(
        key_file, scopes=_SCOPES
    )
    _drive_service = build("drive", "v3", credentials=credentials)
    return _drive_service


def _reset_drive_service():
    global _drive_service
    _drive_service = None


def search_drive_files(query: str, folder_id: str = "") -> str:
    """Search for files in Google Drive by name, or list files in a specific folder."""
    try:
        service = _get_drive_service()
    except RuntimeError as exc:
        return str(exc)

    parts = ["trashed = false"]
    if query:
        safe_query = query.replace("'", "\\'")
        parts.append(f"name contains '{safe_query}'")
    if folder_id:
        safe_folder = folder_id.replace("'", "\\'")
        parts.append(f"'{safe_folder}' in parents")

    q = " and ".join(parts)

    try:
        response = (
            service.files()
            .list(
                q=q,
                fields="files(id, name, mimeType, modifiedTime)",
                pageSize=20,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        return f"Google Drive API error: {exc}"

    files = response.get("files", [])
    if not files:
        return "No files found matching the query."
    return json.dumps(files, indent=2)


def get_drive_file_metadata(file_id: str) -> str:
    """Get metadata for a Google Drive file including name, MIME type, size, and modified date."""
    try:
        service = _get_drive_service()
    except RuntimeError as exc:
        return str(exc)

    try:
        metadata = (
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, modifiedTime, size, createdTime, owners, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            return f"File not found: {file_id}"
        return f"Google Drive API error: {exc}"

    return json.dumps(metadata, indent=2)


def download_drive_file_content(file_id: str) -> str:
    """Download the text content of a Google Drive file. Google Docs are exported as plain text, Sheets as CSV."""
    try:
        service = _get_drive_service()
    except RuntimeError as exc:
        return str(exc)

    try:
        metadata = (
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, size",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            return f"File not found: {file_id}"
        return f"Google Drive API error: {exc}"

    mime_type = metadata.get("mimeType", "")
    name = metadata.get("name", file_id)

    # Google Workspace files must be exported
    if mime_type in _EXPORT_MIME_MAP:
        export_mime = _EXPORT_MIME_MAP[mime_type]
        try:
            data = (
                service.files()
                .export(fileId=file_id, mimeType=export_mime)
                .execute()
            )
        except HttpError as exc:
            return f"Google Drive API error: {exc}"
        content = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + f"\n\n[Truncated: content exceeded {_MAX_CONTENT_CHARS} characters]"
        return content

    # Binary files — refuse rather than dump raw bytes
    is_text = (
        mime_type.startswith("text/")
        or mime_type in ("application/json", "application/xml", "application/javascript")
    )
    if not is_text:
        return (
            f"Cannot display binary file '{name}' ({mime_type}). "
            "Use get_drive_file_metadata to inspect it."
        )

    # Size guard for regular files
    size = int(metadata.get("size") or 0)
    if size > _MAX_FILE_SIZE_BYTES:
        return (
            f"File '{name}' is {size} bytes, which exceeds the {_MAX_FILE_SIZE_BYTES}-byte limit. "
            "Consider accessing a specific section instead."
        )

    try:
        data = service.files().get_media(fileId=file_id).execute()
    except HttpError as exc:
        return f"Google Drive API error: {exc}"

    content = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
    if len(content) > _MAX_CONTENT_CHARS:
        content = content[:_MAX_CONTENT_CHARS] + f"\n\n[Truncated: content exceeded {_MAX_CONTENT_CHARS} characters]"
    return content


tools = [
    Tool(search_drive_files),
    Tool(get_drive_file_metadata),
    Tool(download_drive_file_content),
]
