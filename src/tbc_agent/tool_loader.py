"""
Tool loader — filesystem-based tool discovery.

discover_tools  scans a directory for tool modules and returns all registered
                pydantic-ai Tool instances. This is the sole authorization
                mechanism: only deploy .py files for tools a customer is
                authorized to use.
"""

import importlib.util
import warnings
from pathlib import Path

from pydantic_ai import Tool


def discover_tools(tools_dir: Path | None = None) -> list[Tool]:
    """Load all tool modules from *tools_dir* and return their Tool instances.

    Each ``.py`` file in *tools_dir* that is not ``__init__.py`` and does not
    start with ``_`` is imported. If the module exposes a ``tools`` attribute
    that is a list, its contents are added to the result.

    Modules that fail to import or lack a ``tools`` attribute are silently
    skipped after emitting a :class:`RuntimeWarning`.

    Args:
        tools_dir: Directory to scan. Defaults to the ``tools`` sub-package
                   next to this file.

    Returns:
        Flat list of :class:`pydantic_ai.Tool` instances collected from all
        discovered modules.
    """
    if tools_dir is None:
        tools_dir = Path(__file__).parent / "tools"

    result: list[Tool] = []

    for path in sorted(tools_dir.glob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("_"):
            continue

        module_name = f"_tbc_tool_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            warnings.warn(
                f"tool_loader: could not create spec for {path.name!r}; skipping.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            warnings.warn(
                f"tool_loader: failed to import {path.name!r} ({exc}); skipping.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue

        tool_list = getattr(module, "tools", None)
        if not isinstance(tool_list, list):
            continue

        result.extend(tool_list)

    return result
