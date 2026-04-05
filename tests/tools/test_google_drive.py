"""
Tests for the google_drive tool.

All tests mock _get_drive_service so no real credentials or network calls are needed.
"""

import json
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from tbc_agent.tools.google_drive import (
    download_drive_file_content,
    get_drive_file_metadata,
    search_drive_files,
    tools,
    _reset_drive_service,
)


def _make_http_error(status: int, reason: str = "") -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    return HttpError(resp=resp, content=reason.encode())


@pytest.fixture(autouse=True)
def mock_drive(monkeypatch):
    """Replace _get_drive_service with a mock for every test."""
    mock_service = MagicMock()
    monkeypatch.setattr(
        "tbc_agent.tools.google_drive._get_drive_service",
        lambda: mock_service,
    )
    yield mock_service
    _reset_drive_service()


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_tool_list_exposed():
    assert isinstance(tools, list)
    assert len(tools) == 3


def test_tool_names():
    names = {t.name for t in tools}
    assert names == {"search_drive_files", "get_drive_file_metadata", "download_drive_file_content"}


def test_tools_have_descriptions():
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"


# ---------------------------------------------------------------------------
# search_drive_files
# ---------------------------------------------------------------------------

def test_search_by_name(mock_drive):
    mock_drive.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "abc", "name": "report.txt", "mimeType": "text/plain", "modifiedTime": "2024-01-01"}]
    }
    result = search_drive_files("report")
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "report.txt"
    call_kwargs = mock_drive.files.return_value.list.call_args.kwargs
    assert "name contains 'report'" in call_kwargs["q"]


def test_search_in_folder(mock_drive):
    mock_drive.files.return_value.list.return_value.execute.return_value = {"files": []}
    search_drive_files("", folder_id="folder123")
    call_kwargs = mock_drive.files.return_value.list.call_args.kwargs
    assert "'folder123' in parents" in call_kwargs["q"]


def test_search_combines_query_and_folder(mock_drive):
    mock_drive.files.return_value.list.return_value.execute.return_value = {"files": []}
    search_drive_files("notes", folder_id="folder456")
    call_kwargs = mock_drive.files.return_value.list.call_args.kwargs
    assert "name contains 'notes'" in call_kwargs["q"]
    assert "'folder456' in parents" in call_kwargs["q"]


def test_search_no_results(mock_drive):
    mock_drive.files.return_value.list.return_value.execute.return_value = {"files": []}
    result = search_drive_files("nonexistent")
    assert "no files found" in result.lower()


def test_search_api_error(mock_drive):
    mock_drive.files.return_value.list.return_value.execute.side_effect = _make_http_error(500, "Server Error")
    result = search_drive_files("anything")
    assert isinstance(result, str)
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# get_drive_file_metadata
# ---------------------------------------------------------------------------

def test_get_metadata_success(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "name": "doc.txt",
        "mimeType": "text/plain",
        "modifiedTime": "2024-06-01T12:00:00Z",
        "size": "1024",
    }
    result = get_drive_file_metadata("abc")
    parsed = json.loads(result)
    assert parsed["name"] == "doc.txt"
    assert parsed["size"] == "1024"


def test_get_metadata_not_found(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.side_effect = _make_http_error(404, "Not Found")
    result = get_drive_file_metadata("missing-id")
    assert "not found" in result.lower()
    assert "missing-id" in result


# ---------------------------------------------------------------------------
# download_drive_file_content
# ---------------------------------------------------------------------------

def test_download_google_doc(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "id": "doc1",
        "name": "My Doc",
        "mimeType": "application/vnd.google-apps.document",
    }
    mock_drive.files.return_value.export.return_value.execute.return_value = b"Hello world"
    result = download_drive_file_content("doc1")
    assert result == "Hello world"
    call_kwargs = mock_drive.files.return_value.export.call_args.kwargs
    assert call_kwargs["mimeType"] == "text/plain"


def test_download_google_sheet_as_csv(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "id": "sheet1",
        "name": "My Sheet",
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    mock_drive.files.return_value.export.return_value.execute.return_value = b"a,b\n1,2"
    result = download_drive_file_content("sheet1")
    assert "a,b" in result
    call_kwargs = mock_drive.files.return_value.export.call_args.kwargs
    assert call_kwargs["mimeType"] == "text/csv"


def test_download_plain_text_file(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "id": "txt1",
        "name": "notes.txt",
        "mimeType": "text/plain",
        "size": "11",
    }
    mock_drive.files.return_value.get_media.return_value.execute.return_value = b"file content"
    result = download_drive_file_content("txt1")
    assert result == "file content"


def test_download_binary_file_rejected(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "id": "pdf1",
        "name": "report.pdf",
        "mimeType": "application/pdf",
        "size": "50000",
    }
    result = download_drive_file_content("pdf1")
    assert "cannot display" in result.lower() or "binary" in result.lower()


def test_download_large_file_truncated(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "id": "big1",
        "name": "big.txt",
        "mimeType": "text/plain",
        "size": str(600_000),
    }
    result = download_drive_file_content("big1")
    assert "limit" in result.lower() or "exceeds" in result.lower()


def test_download_api_error(mock_drive):
    mock_drive.files.return_value.get.return_value.execute.side_effect = _make_http_error(403, "Forbidden")
    result = download_drive_file_content("file1")
    assert isinstance(result, str)
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# Auth / lazy-init
# ---------------------------------------------------------------------------

def test_import_without_env_var():
    # Module has already been imported above without credentials — no exception
    import tbc_agent.tools.google_drive  # noqa: F401


def test_missing_env_var_on_call(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", raising=False)
    # Override the autouse fixture for this test — bypass the mock
    monkeypatch.setattr(
        "tbc_agent.tools.google_drive._get_drive_service",
        lambda: (_ for _ in ()).throw(
            RuntimeError("GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable is not set.")
        ),
    )
    result = search_drive_files("anything")
    assert "GOOGLE_SERVICE_ACCOUNT_KEY_FILE" in result
