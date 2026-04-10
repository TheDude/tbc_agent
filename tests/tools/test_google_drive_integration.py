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
    gd_get_file,
)

@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    """Check if credentials are configured. Raise AssertionError if not."""
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE"):
        raise AssertionError(
            "GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable is not set. "
            "Integration tests require credentials to run."
        )

TEST_FOLDER_NAME = "tbc_agent_test"
TEST_DOC_NAME = "Copy of Dawn"
TEST_SHEET_NAME = "Copy of Finnegan Upgrades"
TEST_JUNK_FOLDER_NAME = "junk_folder"
TEST_PDF_NAME = "Copy of Guest Last.pdf"
TEST_TEXT_FILE_NAME = "text.txt"