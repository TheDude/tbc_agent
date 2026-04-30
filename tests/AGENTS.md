Tests Directory Guide
=====================

Overview
--------
The `tests/` tree mirrors the five architectural blocks plus supporting packages. Root-level modules exercise orchestration, state management, input/output channels, tool discovery, and startup wiring. Subpackages group domain-specific suites:

* `tests/tools/` covers individual tool plugins (Google Drive, current_time, etc.).
* `tests/auth/` validates the shared OAuth2/keyring infrastructure.
* Integration fixtures (real LLM, end-to-end loops) live alongside unit suites for easy discovery.

Most files start with a descriptive docstring that cites design-plan tasks (e.g., `T1.1–T1.11`) so requirement coverage is explicit.

Structure & Naming
------------------
* Each feature area uses `Test<Class>` containers with pytest-style `test_*` methods. Method names echo the requirement IDs recorded in docstrings for traceability.
* Helpers (e.g., `make_agent`, `FakeProducer`, `CapturingChannel`) live inside the test file that needs them to avoid hidden dependencies.
* Autouse fixtures set up deterministic environments (for example, `InMemoryKeyring` in `tests/auth/test_credential_store.py`). Prefer fixtures over ad-hoc global state.

Pytest Practices
----------------
* Use `monkeypatch` to isolate environment variables and external interactions. Tests clean up with `monkeypatch.delenv(..., raising=False)` to avoid leaking state.
* When faking the LLM, rely on `pydantic_ai.models.function.FunctionModel` with scripted replies or recorded call lists.
* Capture I/O with `io.StringIO` to assert on CLI producer/channel behavior without touching real stdin/stdout.
* Integration boundaries are marked with `@pytest.mark.integration`; `pyproject.toml` excludes them by default via `addopts = -m "not integration"`.
* Slow or external tests must declare additional markers (`@pytest.mark.google_drive`, etc.) so they can be filtered.
* Real network use is opt-in: `tests/test_real_llm_integration.py` guards execution with `pytest.mark.skipif` and requires `XAI_API_KEY`.

Authentication Test Notes
-------------------------
* OAuth tests replace keyring operations with an in-memory backend via fixtures to avoid polluting the host OS keychain.
* Device-flow logic is validated through stubbed Authlib sessions (`DummySession` classes) that simulate polling, refresh failures, and token persistence.
* When interacting with Google credential wrappers, tests verify refresh callbacks by mutating dummy tokens and ensuring keyring state stays in sync.

Tool Test Expectations
----------------------
* Tool modules are exercised via their exported `Tool` wrappers, not by importing internal functions directly.
* Google Drive suites confirm the OAuth-first, service-account fallback order. They use monkeypatched `build()` calls so no live Google API traffic occurs.
* Tests should return strings and assert serialized JSON structures rather than raw Python objects, matching production contracts.

Running the Suite
-----------------
Always invoke pytest through `bws` so environment secrets resolve correctly:

```
bws run -- uv run pytest           # full suite (excludes integration by default)
bws run -- uv run pytest tests/tools/   # tool-only subset
bws run -- uv run pytest -m integration # opt-in integration/real LLM tests
```

Extending the Tests
-------------------
* Introduce new requirement IDs (T*-style) in docstrings if you add major coverage areas.
* Prefer explicit assertions over truthy checks (e.g., `assert event.payload == "hello"`).
* Keep tests deterministic; use helper factories to script time-sensitive values (`datetime.now(tz=timezone.utc)`) only when comparing ranges.
* Never read `.env` files or rely on host keyring state. Use fixtures, monkeypatches, or in-memory doubles instead.
