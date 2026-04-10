"""
Tests for the google_drive tool.

All tests mock _get_drive_service so no real credentials or network calls are needed.
"""

import json
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from tbc_agent.tools.google_drive import (
    gd_search,
    gd_read_metadata,
    gd_get_file,
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
    assert names == {"gd_search", "gd_read_metadata", "gd_get_file"}


def test_tools_have_descriptions():
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
