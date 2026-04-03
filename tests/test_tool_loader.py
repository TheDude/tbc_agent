"""
Tests for the tool loader — filesystem-based tool discovery.
"""

import warnings

import pytest
from pydantic_ai import Tool

from tbc_agent.tool_loader import discover_tools


def _write_tool_module(path, content: str) -> None:
    path.write_text(content)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_discovers_tools_from_directory(tmp_path):
    _write_tool_module(
        tmp_path / "my_tool.py",
        """
from pydantic_ai import Tool

def my_func() -> str:
    \"\"\"A test tool.\"\"\"
    return "hello"

tools = [Tool(my_func)]
""",
    )
    result = discover_tools(tmp_path)
    assert len(result) == 1
    assert result[0].name == "my_func"


def test_multiple_files_aggregated(tmp_path):
    _write_tool_module(
        tmp_path / "tool_a.py",
        """
from pydantic_ai import Tool
def func_a() -> str:
    \"\"\"Tool A.\"\"\"
    return "a"
tools = [Tool(func_a)]
""",
    )
    _write_tool_module(
        tmp_path / "tool_b.py",
        """
from pydantic_ai import Tool
def func_b() -> str:
    \"\"\"Tool B.\"\"\"
    return "b"
tools = [Tool(func_b)]
""",
    )
    result = discover_tools(tmp_path)
    names = {t.name for t in result}
    assert names == {"func_a", "func_b"}


def test_empty_directory_returns_empty_list(tmp_path):
    assert discover_tools(tmp_path) == []


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------


def test_skips_init_file(tmp_path):
    _write_tool_module(
        tmp_path / "__init__.py",
        """
from pydantic_ai import Tool
def init_func() -> str:
    \"\"\"Should be skipped.\"\"\"
    return "x"
tools = [Tool(init_func)]
""",
    )
    assert discover_tools(tmp_path) == []


def test_skips_underscore_prefixed_files(tmp_path):
    _write_tool_module(
        tmp_path / "_helper.py",
        """
from pydantic_ai import Tool
def helper_func() -> str:
    \"\"\"Should be skipped.\"\"\"
    return "x"
tools = [Tool(helper_func)]
""",
    )
    assert discover_tools(tmp_path) == []


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_skips_module_without_tools_attribute(tmp_path):
    _write_tool_module(tmp_path / "no_tools.py", "x = 42\n")
    assert discover_tools(tmp_path) == []


def test_skips_module_with_import_error(tmp_path):
    _write_tool_module(
        tmp_path / "broken.py",
        "import this_module_does_not_exist_ever\n",
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = discover_tools(tmp_path)
    assert result == []
    assert any("broken" in str(warning.message).lower() for warning in w)


def test_non_list_tools_attribute_skipped(tmp_path):
    """A module with tools = None should be skipped without crashing."""
    _write_tool_module(tmp_path / "bad_attr.py", "tools = None\n")
    assert discover_tools(tmp_path) == []
