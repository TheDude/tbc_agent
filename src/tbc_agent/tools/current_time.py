"""
Tool: current_time — returns the current date and time in UTC.
"""

from datetime import datetime, timezone

from pydantic_ai import Tool


def get_current_time() -> str:
    """Get the current date and time in UTC ISO-8601 format."""
    return datetime.now(tz=timezone.utc).isoformat()


tools = [Tool(get_current_time)]
