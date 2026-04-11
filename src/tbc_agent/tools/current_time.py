"""
Tool: current_time — returns the current date and time in UTC.

This tool provides the current date and time in ISO-8601 format in the UTC timezone.
It requires no dependencies or environment variables and performs pure logic.

Example return value: "2026-04-10T18:30:45.123456+00:00"
"""

from datetime import datetime, timezone

from pydantic_ai import Tool


def get_current_time() -> str:
    """Get the current date and time in UTC ISO-8601 format."""
    return datetime.now(tz=timezone.utc).isoformat()


tools = [Tool(get_current_time)]