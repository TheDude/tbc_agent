"""
Tests for the google_drive tool.

All tests mock _get_drive_service so no real credentials or network calls are needed.
"""

import json
import os
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from tbc_agent.tools.google_drive import (
    gd_search,
    gd_read_metadata,
    gd_read_file,
    tools,
    _reset_drive_service,
)

pytestmark = [pytest.mark.google_drive]


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
    assert names == {"gd_search", "gd_read_metadata", "gd_read_file"}


def test_tools_have_descriptions():
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"


# ---------------------------------------------------------------------------
# gd_search tests
# ---------------------------------------------------------------------------

def test_gd_search_basic_query(mock_drive):
    mock_files = mock_drive.files()
    mock_list = mock_files.list.return_value
    mock_list.execute.return_value = {
        "files": [
            {
                "id": "file123",
                "name": "Test Doc",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2024-01-15T10:30:00.000Z",
                "owners": [{"emailAddress": "user@example.com"}]
            }
        ]
    }
    
    result = gd_search('name contains "Test"')
    data = json.loads(result)
    
    assert "files" in data
    assert len(data["files"]) == 1
    assert data["files"][0]["name"] == "Test Doc"
    mock_files.list.assert_called_once()


def test_gd_search_empty_results(mock_drive):
    mock_files = mock_drive.files()
    mock_list = mock_files.list.return_value
    mock_list.execute.return_value = {"files": []}
    
    result = gd_search('name contains "nonexistent"')
    data = json.loads(result)
    
    assert "files" in data
    assert len(data["files"]) == 0


def test_gd_search_http_error(mock_drive):
    mock_files = mock_drive.files()
    mock_list = mock_files.list.return_value
    mock_list.execute.side_effect = _make_http_error(400, "Invalid query")
    
    result = gd_search('invalid query')
    data = json.loads(result)
    
    assert "error" in data
    assert data["error"] == "search_failed"
    assert "status" in data


def test_gd_search_unexpected_error(mock_drive):
    mock_files = mock_drive.files()
    mock_list = mock_files.list.return_value
    mock_list.execute.side_effect = RuntimeError("Unexpected failure")
    
    result = gd_search('name contains "test"')
    data = json.loads(result)
    
    assert "error" in data
    assert data["error"] == "unexpected_error"


# ---------------------------------------------------------------------------
# gd_read_metadata tests
# ---------------------------------------------------------------------------

def test_gd_read_metadata_success(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.return_value = {
        "id": "file123",
        "name": "Test File",
        "mimeType": "application/vnd.google-apps.document",
        "size": 12345,
        "createdTime": "2024-01-01T00:00:00.000Z",
        "modifiedTime": "2024-01-15T10:30:00.000Z",
        "owners": [{"emailAddress": "user@example.com"}],
        "shared": True,
        "webViewLink": "https://drive.google.com/file/d/file123/view",
        "capabilities": {"canEdit": True, "canShare": True}
    }
    
    result = gd_read_metadata("file123")
    data = json.loads(result)
    
    assert data["id"] == "file123"
    assert data["name"] == "Test File"
    assert data["size"] == 12345
    mock_files.get.assert_called_once()


def test_gd_read_metadata_file_not_found(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.side_effect = _make_http_error(404, "File not found")
    
    result = gd_read_metadata("nonexistent123")
    data = json.loads(result)
    
    assert data["error"] == "file_not_found"
    assert data["status"] == 404


def test_gd_read_metadata_permission_denied(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.side_effect = _make_http_error(403, "Permission denied")
    
    result = gd_read_metadata("file123")
    data = json.loads(result)
    
    assert data["error"] == "permission_denied"
    assert data["status"] == 403


def test_gd_read_metadata_other_http_error(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.side_effect = _make_http_error(500, "Server error")
    
    result = gd_read_metadata("file123")
    data = json.loads(result)
    
    assert data["error"] == "metadata_fetch_failed"
    assert data["status"] == 500


# ---------------------------------------------------------------------------
# gd_read_file tests
# ---------------------------------------------------------------------------

def _mock_downloader_factory(content: bytes):
    """Helper to create a mock downloader that writes content to temp file."""
    def mock_downloader_side_effect(temp_file, request):
        temp_file.write(content)
        return MagicMock(next_chunk=lambda: (None, True))
    return mock_downloader_side_effect


def test_gd_read_file_plain_text(mock_drive):
    mock_files = mock_drive.files()
    
    mock_metadata = mock_files.get.return_value
    mock_metadata.execute.return_value = {
        "id": "file123",
        "name": "test.txt",
        "mimeType": "text/plain"
    }
    
    import tbc_agent.tools.google_drive as gd_module
    mock_downloader = MagicMock(side_effect=_mock_downloader_factory(b"Test file content"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gd_module, "MediaIoBaseDownload", mock_downloader)
    
    try:
        result = gd_read_file("file123")
        assert result == "Test file content"
    finally:
        monkeypatch.undo()


def test_gd_read_file_google_doc(mock_drive):
    mock_files = mock_drive.files()
    
    mock_metadata = mock_files.get.return_value
    mock_metadata.execute.return_value = {
        "id": "doc123",
        "name": "Test Doc",
        "mimeType": "application/vnd.google-apps.document"
    }
    
    import tbc_agent.tools.google_drive as gd_module
    mock_downloader = MagicMock(side_effect=_mock_downloader_factory(b"Google Doc content"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gd_module, "MediaIoBaseDownload", mock_downloader)
    
    try:
        result = gd_read_file("doc123")
        assert result == "Google Doc content"
        mock_files.export_media.assert_called_once()
    finally:
        monkeypatch.undo()


def test_gd_read_file_google_sheet(mock_drive):
    mock_files = mock_drive.files()
    
    mock_metadata = mock_files.get.return_value
    mock_metadata.execute.return_value = {
        "id": "sheet123",
        "name": "Test Sheet",
        "mimeType": "application/vnd.google-apps.spreadsheet"
    }
    
    import tbc_agent.tools.google_drive as gd_module
    mock_downloader = MagicMock(side_effect=_mock_downloader_factory(b"col1,col2\nval1,val2"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gd_module, "MediaIoBaseDownload", mock_downloader)
    
    try:
        result = gd_read_file("sheet123")
        assert result == "col1,col2\nval1,val2"
        mock_files.export_media.assert_called_once()
    finally:
        monkeypatch.undo()


def test_gd_read_file_temp_cleanup_on_error(mock_drive):
    mock_files = mock_drive.files()
    
    mock_metadata = mock_files.get.return_value
    mock_metadata.execute.return_value = {
        "id": "file123",
        "name": "test.txt",
        "mimeType": "text/plain"
    }
    
    import tbc_agent.tools.google_drive as gd_module
    
    mock_downloader = MagicMock(side_effect=_mock_downloader_factory(b"content"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gd_module, "MediaIoBaseDownload", mock_downloader)
    
    temp_files_created = []
    original_temp = gd_module.tempfile.NamedTemporaryFile
    
    def track_temp_file(*args, **kwargs):
        result = original_temp(*args, **kwargs)
        temp_files_created.append(result.name)
        return result
    
    monkeypatch.setattr(gd_module.tempfile, "NamedTemporaryFile", track_temp_file)
    
    try:
        result = gd_read_file("file123")
        assert result == "content"
    finally:
        monkeypatch.undo()
    
    for temp_file in temp_files_created:
        assert not os.path.exists(temp_file), f"Temp file {temp_file} was not cleaned up"


def test_gd_read_file_file_not_found(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.side_effect = _make_http_error(404, "File not found")
    
    result = gd_read_file("nonexistent123")
    data = json.loads(result)
    
    assert data["error"] == "file_not_found"
    assert data["status"] == 404


def test_gd_read_file_permission_denied(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.side_effect = _make_http_error(403, "Permission denied")
    
    result = gd_read_file("file123")
    data = json.loads(result)
    
    assert data["error"] == "permission_denied"
    assert data["status"] == 403


def test_gd_read_file_encoding_error(mock_drive):
    mock_files = mock_drive.files()
    
    mock_metadata = mock_files.get.return_value
    mock_metadata.execute.return_value = {
        "id": "file123",
        "name": "binary.bin",
        "mimeType": "application/octet-stream"
    }
    
    import tbc_agent.tools.google_drive as gd_module
    mock_downloader = MagicMock(side_effect=_mock_downloader_factory(b"\x80\x81\x82"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gd_module, "MediaIoBaseDownload", mock_downloader)
    
    try:
        result = gd_read_file("file123")
        data = json.loads(result)
        assert data["error"] == "encoding_error"
    finally:
        monkeypatch.undo()


def test_gd_read_file_unexpected_error(mock_drive):
    mock_files = mock_drive.files()
    mock_get = mock_files.get.return_value
    mock_get.execute.side_effect = RuntimeError("Unexpected failure")
    
    result = gd_read_file("file123")
    data = json.loads(result)
    
    assert data["error"] == "unexpected_error"
