# Tools Directory — AGENTS.md

## Overview

This directory contains **tool plugins** that extend the agent's capabilities. Each `.py` file (excluding `__init__.py` and `_`-prefixed files) is a self-contained tool that the agent framework automatically discovers and exposes to the LLM.

Tools follow a simple contract:
- Export a **`tools` list** containing `pydantic_ai.Tool` instances
- Each tool function returns a `str` (the tool's response)

## Development Security and Safety
- Environment variables contain the user's private secrets. Respecting this privacy is *critical* to maintaining safety and security.
- **ALWAYS** respect the user's privacy.
- **NEVER** read any .env files 
- **NEVER** examine any environment variables.

## Tool File Structure

```python
"""
Tool: <tool_name> — brief description of what this tool does.

Optional longer description, including any environment variables or
dependencies required.
"""

from pydantic_ai import Tool

def my_function(arg1: str, arg2: int) -> str:
    """Description of what this function does."""
    # ... implementation ...
    return result

tools = [Tool(my_function)]
```

### Key Rules

| Rule | Reason |
|------|--------|
| One `.py` file per tool | Keeps tools independent and deployable separately |
| Export `tools` list at module level | Tool discovery scans for this attribute |
| Use `pydantic_ai.Tool` wrapper | Required by the agent framework |
| Use type hints on all functions | Required by project standard |
| Return `str` from tool functions | Contract: all tools return string responses |

## Tool Discovery

`tool_loader.discover_tools()` in `src/tbc_agent/tool_loader.py` handles discovery:
1. Scans `tools/` for `*.py` files
2. Skips `__init__.py` and files starting with `_`
3. Imports each module and collects the `tools` list
4. Returns a flat list of `pydantic_ai.Tool` instances

## Testing Tools

Tests live in `tests/tools/test_<tool_name>.py`.

## Coding Standards (from parent AGENTS.md)

- **Type hints required** on all function signatures
- **Return errors as strings**, not exceptions (caller handles gracefully)
- **Keep tools independent** — a tool should not import from other project modules

## Environment Variables in Tools

## Examples

| Tool File | Complexity | Notes |
|-----------|------------|-------|
| `current_time.py` | Simple | One function, no deps, pure logic 

## Commands

- Run tool tests: `bws run -- uv run pytest tests/tools/`
- Run all tests: `bws run -- uv run pytest`