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
    gd_search,
    gd_read_metadata,
    gd_read_file,
)

pytestmark = [pytest.mark.integration, pytest.mark.google_drive]


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    """Skip tests if credentials not configured."""
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if not key_file:
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_KEY_FILE not set")


TEST_DOC_NAME = "Copy of Dawn"
TEST_SHEET_NAME = "Copy of Finnegan Upgrades"
TEST_JUNK_FOLDER_NAME = "junk_folder"
TEST_PDF_NAME = "Copy of Guest Last.pdf"
TEST_TEXT_FILE_NAME = "text.txt"


@pytest.fixture(scope="module")
def doc_file_id():
    """Get file ID for test Google Doc."""
    result = gd_search(f'name = "{TEST_DOC_NAME}"')
    data = json.loads(result)
    files = data.get("files", [])
    if not files:
        pytest.skip(f"Test document '{TEST_DOC_NAME}' not found")
    return files[0]["id"]


@pytest.fixture(scope="module")
def sheet_file_id():
    """Get file ID for test Google Sheet."""
    result = gd_search(f'name = "{TEST_SHEET_NAME}"')
    data = json.loads(result)
    files = data.get("files", [])
    if not files:
        pytest.skip(f"Test sheet '{TEST_SHEET_NAME}' not found")
    return files[0]["id"]


@pytest.fixture(scope="module")
def text_file_id():
    """Get file ID for test text file."""
    result = gd_search(f'name = "{TEST_TEXT_FILE_NAME}"')
    data = json.loads(result)
    files = data.get("files", [])
    if not files:
        pytest.skip(f"Test text file '{TEST_TEXT_FILE_NAME}' not found")
    return files[0]["id"]


@pytest.fixture(scope="module")
def pdf_file_id():
    """Get file ID for test PDF file."""
    result = gd_search(f'name = "{TEST_PDF_NAME}"')
    data = json.loads(result)
    files = data.get("files", [])
    if not files:
        pytest.skip(f"Test PDF '{TEST_PDF_NAME}' not found")
    return files[0]["id"]


class TestGdSearchIntegration:
    """Integration tests for gd_search."""
    
    def test_search_doc_by_name(self, doc_file_id):
        result = gd_search(f'name = "{TEST_DOC_NAME}"')
        data = json.loads(result)
        
        assert "files" in data
        assert len(data["files"]) >= 1
        assert any(f["name"] == TEST_DOC_NAME for f in data["files"])
    
    def test_search_sheet_by_name(self, sheet_file_id):
        result = gd_search(f'name = "{TEST_SHEET_NAME}"')
        data = json.loads(result)
        
        assert "files" in data
        assert len(data["files"]) >= 1
        assert any(f["name"] == TEST_SHEET_NAME for f in data["files"])
    
    def test_search_docs_by_mime_type(self):
        result = gd_search('mimeType = "application/vnd.google-apps.document"')
        data = json.loads(result)
        
        assert "files" in data
        assert len(data["files"]) >= 1
    
    def test_search_sheets_by_mime_type(self):
        result = gd_search('mimeType = "application/vnd.google-apps.spreadsheet"')
        data = json.loads(result)
        
        assert "files" in data
        assert len(data["files"]) >= 1
    
    def test_search_in_folder(self):
        folder_result = gd_search(
            f'name = "{TEST_JUNK_FOLDER_NAME}" and '
            'mimeType = "application/vnd.google-apps.folder"'
        )
        folder_data = json.loads(folder_result)
        
        if not folder_data.get("files"):
            pytest.skip("junk_folder not found")
        
        folder_id = folder_data["files"][0]["id"]
        result = gd_search(f"'{folder_id}' in parents")
        data = json.loads(result)
        
        assert "files" in data
        assert len(data["files"]) >= 2
    
    def test_search_nonexistent(self):
        result = gd_search('name = "nonexistent_file_xyz123"')
        data = json.loads(result)
        
        assert "files" in data
        assert len(data["files"]) == 0


class TestGdReadMetadataIntegration:
    """Integration tests for gd_read_metadata."""
    
    def test_read_doc_metadata(self, doc_file_id):
        result = gd_read_metadata(doc_file_id)
        data = json.loads(result)
        
        assert data["id"] == doc_file_id
        assert data["name"] == TEST_DOC_NAME
        assert data["mimeType"] == "application/vnd.google-apps.document"
        assert "createdTime" in data
        assert "modifiedTime" in data
    
    def test_read_sheet_metadata(self, sheet_file_id):
        result = gd_read_metadata(sheet_file_id)
        data = json.loads(result)
        
        assert data["id"] == sheet_file_id
        assert data["name"] == TEST_SHEET_NAME
        assert data["mimeType"] == "application/vnd.google-apps.spreadsheet"
    
    def test_read_text_file_metadata(self, text_file_id):
        result = gd_read_metadata(text_file_id)
        data = json.loads(result)
        
        assert data["id"] == text_file_id
        assert data["name"] == TEST_TEXT_FILE_NAME
        assert data["mimeType"] == "text/plain"
    
    def test_read_pdf_metadata(self, pdf_file_id):
        result = gd_read_metadata(pdf_file_id)
        data = json.loads(result)
        
        assert data["id"] == pdf_file_id
        assert data["name"] == TEST_PDF_NAME
        assert "application/pdf" in data["mimeType"]
    
    def test_read_nonexistent_metadata(self):
        result = gd_read_metadata("nonexistent_file_id_12345")
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "file_not_found"


class TestGdReadFileIntegration:
    """Integration tests for gd_read_file."""
    
    def test_read_doc(self, doc_file_id):
        result = gd_read_file(doc_file_id)
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_read_sheet(self, sheet_file_id):
        result = gd_read_file(sheet_file_id)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "," in result
    
    def test_read_text_file(self, text_file_id):
        result = gd_read_file(text_file_id)
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_read_pdf(self, pdf_file_id):
        result = gd_read_file(pdf_file_id)
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_read_nonexistent_file(self):
        result = gd_read_file("nonexistent_file_id_12345")
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "file_not_found"
