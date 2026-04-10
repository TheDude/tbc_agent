"""
Integration tests for google_drive tool.

These tests make real Google Drive API calls against a fixed test folder structure.
Run with: bws run -- uv run pytest -m integration

Test folder structure (tbc_agent_test/):
├── "Copy of Dawn" (Google Doc)
├── "Copy of Finnegan Upgrades" (Google Sheet)
└── junk_folder/
    ├── "Copy of Guest Last.pdf" (PDF)
    └── "text.txt" (Plain text)
"""

import json
import os

import pytest

from tbc_agent.tools.google_drive import (
    download_drive_file_content,
    get_drive_file_metadata,
    search_drive_files,
)


def _check_credentials():
    """Check if credentials are configured. Raise AssertionError if not."""
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE"):
        raise AssertionError(
            "GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable is not set. "
            "Integration tests require credentials to run."
        )


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    """Ensure credentials are configured before running any tests in this module."""
    _check_credentials()

TEST_FOLDER_NAME = "tbc_agent_test"
TEST_DOC_NAME = "Copy of Dawn"
TEST_SHEET_NAME = "Copy of Finnegan Upgrades"
TEST_JUNK_FOLDER_NAME = "junk_folder"
TEST_PDF_NAME = "Copy of Guest Last.pdf"
TEST_TEXT_FILE_NAME = "text.txt"


def _find_file_id_by_name(name: str, folder_id: str = "") -> str | None:
    """Search for a file by name and return its ID, or None if not found."""
    result = search_drive_files(name, folder_id=folder_id)
    if "no files found" in result.lower():
        return None
    try:
        files = json.loads(result)
        if files:
            return files[0]["id"]
    except (json.JSONDecodeError, IndexError):
        pass
    return None


def _find_folder_id_by_name(name: str) -> str | None:
    """Search for a folder by name and return its ID, or None if not found."""
    result = search_drive_files(name)
    if "no files found" in result.lower():
        return None
    files = json.loads(result)
    for f in files:
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            return f["id"]
    return None


def _require_test_folder():
    """Ensure the tbc_agent_test folder exists, raise AssertionError if not."""
    folder_id = _find_folder_id_by_name(TEST_FOLDER_NAME)
    if not folder_id:
        raise AssertionError(
            f"Test folder '{TEST_FOLDER_NAME}' not found in Google Drive. "
            "Ensure the service account has access to the test folder."
        )
    return folder_id


@pytest.mark.integration
@pytest.mark.google_drive
class TestSearchDriveFilesIntegration:
    """Integration tests for search_drive_files function."""

    def test_search_doc_by_name(self):
        """Search for the Google Doc by name."""
        result = search_drive_files(TEST_DOC_NAME)
        assert "no files found" not in result.lower()
        files = json.loads(result)
        assert len(files) >= 1
        assert any(f["name"] == TEST_DOC_NAME for f in files)

    def test_search_sheet_by_name(self):
        """Search for the Google Sheet by name."""
        result = search_drive_files(TEST_SHEET_NAME)
        assert "no files found" not in result.lower()
        files = json.loads(result)
        assert len(files) >= 1
        assert any(f["name"] == TEST_SHEET_NAME for f in files)

    def test_search_junk_folder_by_name(self):
        """Search for the junk_folder by name."""
        result = search_drive_files(TEST_JUNK_FOLDER_NAME)
        assert "no files found" not in result.lower()
        files = json.loads(result)
        assert len(files) >= 1
        folder_ids = [f["id"] for f in files if f.get("mimeType") == "application/vnd.google-apps.folder"]
        assert len(folder_ids) >= 1, "junk_folder should be found as a folder"

    def test_search_text_file_in_junk_folder(self):
        """Search for text.txt within junk_folder."""
        folder_id = _require_test_folder()
        junk_id = _find_folder_id_by_name(TEST_JUNK_FOLDER_NAME)
        if not junk_id:
            pytest.skip(f"Folder '{TEST_JUNK_FOLDER_NAME}' not found")

        result = search_drive_files(TEST_TEXT_FILE_NAME, folder_id=junk_id)
        assert "no files found" not in result.lower()
        files = json.loads(result)
        assert len(files) >= 1
        assert any(f["name"] == TEST_TEXT_FILE_NAME for f in files)

    def test_search_nonexistent_file(self):
        """Search for a file that doesn't exist."""
        result = search_drive_files("nonexistent_file_xyz12345")
        assert "no files found" in result.lower()


@pytest.mark.integration
@pytest.mark.google_drive
class TestGetDriveFileMetadataIntegration:
    """Integration tests for get_drive_file_metadata function."""

    def test_get_metadata_google_doc(self):
        """Get metadata for the Google Doc."""
        file_id = _find_file_id_by_name(TEST_DOC_NAME)
        if not file_id:
            pytest.skip(f"Test doc '{TEST_DOC_NAME}' not found in Google Drive")

        result = get_drive_file_metadata(file_id)
        metadata = json.loads(result)
        assert metadata["name"] == TEST_DOC_NAME
        assert metadata["mimeType"] == "application/vnd.google-apps.document"

    def test_get_metadata_google_sheet(self):
        """Get metadata for the Google Sheet."""
        file_id = _find_file_id_by_name(TEST_SHEET_NAME)
        if not file_id:
            pytest.skip(f"Test sheet '{TEST_SHEET_NAME}' not found in Google Drive")

        result = get_drive_file_metadata(file_id)
        metadata = json.loads(result)
        assert metadata["name"] == TEST_SHEET_NAME
        assert metadata["mimeType"] == "application/vnd.google-apps.spreadsheet"

    def test_get_metadata_pdf(self):
        """Get metadata for the PDF file."""
        junk_id = _find_folder_id_by_name(TEST_JUNK_FOLDER_NAME)
        if not junk_id:
            pytest.skip(f"Folder '{TEST_JUNK_FOLDER_NAME}' not found")

        pdf_id = _find_file_id_by_name(TEST_PDF_NAME, folder_id=junk_id)
        if not pdf_id:
            pytest.skip(f"PDF '{TEST_PDF_NAME}' not found in junk_folder")

        result = get_drive_file_metadata(pdf_id)
        metadata = json.loads(result)
        assert metadata["name"] == TEST_PDF_NAME
        assert metadata["mimeType"] == "application/pdf"

    def test_get_metadata_text_file(self):
        """Get metadata for the plain text file."""
        junk_id = _find_folder_id_by_name(TEST_JUNK_FOLDER_NAME)
        if not junk_id:
            pytest.skip(f"Folder '{TEST_JUNK_FOLDER_NAME}' not found")

        txt_id = _find_file_id_by_name(TEST_TEXT_FILE_NAME, folder_id=junk_id)
        if not txt_id:
            pytest.skip(f"Text file '{TEST_TEXT_FILE_NAME}' not found in junk_folder")

        result = get_drive_file_metadata(txt_id)
        metadata = json.loads(result)
        assert metadata["name"] == TEST_TEXT_FILE_NAME
        assert metadata["mimeType"] == "text/plain"

    def test_get_metadata_nonexistent_file(self):
        """Get metadata for a non-existent file ID."""
        result = get_drive_file_metadata("invalid_file_id_12345")
        assert "not found" in result.lower()
        assert "invalid_file_id_12345" in result


@pytest.mark.integration
@pytest.mark.google_drive
class TestDownloadDriveFileContentIntegration:
    """Integration tests for download_drive_file_content function."""

    def test_download_google_doc(self):
        """Download the Google Doc (exported as plain text)."""
        file_id = _find_file_id_by_name(TEST_DOC_NAME)
        if not file_id:
            pytest.skip(f"Test doc '{TEST_DOC_NAME}' not found in Google Drive")

        content = download_drive_file_content(file_id)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_download_google_sheet(self):
        """Download the Google Sheet (exported as CSV)."""
        file_id = _find_file_id_by_name(TEST_SHEET_NAME)
        if not file_id:
            pytest.skip(f"Test sheet '{TEST_SHEET_NAME}' not found in Google Drive")

        content = download_drive_file_content(file_id)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_download_text_file(self):
        """Download the plain text file."""
        junk_id = _find_folder_id_by_name(TEST_JUNK_FOLDER_NAME)
        if not junk_id:
            pytest.skip(f"Folder '{TEST_JUNK_FOLDER_NAME}' not found")

        txt_id = _find_file_id_by_name(TEST_TEXT_FILE_NAME, folder_id=junk_id)
        if not txt_id:
            pytest.skip(f"Text file '{TEST_TEXT_FILE_NAME}' not found in junk_folder")

        content = download_drive_file_content(txt_id)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_download_pdf_rejected(self):
        """Attempt to download PDF (should be rejected as binary)."""
        junk_id = _find_folder_id_by_name(TEST_JUNK_FOLDER_NAME)
        if not junk_id:
            pytest.skip(f"Folder '{TEST_JUNK_FOLDER_NAME}' not found")

        pdf_id = _find_file_id_by_name(TEST_PDF_NAME, folder_id=junk_id)
        if not pdf_id:
            pytest.skip(f"PDF '{TEST_PDF_NAME}' not found in junk_folder")

        result = download_drive_file_content(pdf_id)
        assert "cannot display" in result.lower() or "binary" in result.lower()

    def test_download_nonexistent_file(self):
        """Attempt to download a non-existent file."""
        result = download_drive_file_content("invalid_file_id_12345")
        assert "not found" in result.lower()
