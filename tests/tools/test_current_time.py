"""
Tests for the current_time tool.
"""

from datetime import datetime, timezone

from tbc_agent.tools.current_time import get_current_time, tools


def test_returns_iso_format():
    result = get_current_time()
    # Should parse without error
    parsed = datetime.fromisoformat(result)
    assert isinstance(parsed, datetime)


def test_returns_utc():
    result = get_current_time()
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_tool_list_exposed():
    assert isinstance(tools, list)
    assert len(tools) == 1


def test_tool_name():
    assert tools[0].name == "get_current_time"


def test_tool_has_description():
    assert tools[0].description
    assert "time" in tools[0].description.lower()
