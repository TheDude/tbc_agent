# AGENTS.md

## Project Overview
This is a CLI chat agent built on Python 3.12+ using pydantic-ai as the orchestration framework. It coordinates functional blocks (input, LLM interface, output, conversation state, orchestrator) wired together via dependency injection. The agent supports tool-augmented responses via a filesystem-based plugin system and optional Langfuse observability tracing.

## Tech Stack & Versions
- Language: Python 3.12+
- Package manager: uv
- LLM framework: pydantic-ai
- Observability: Langfuse (optional)
- External APIs: Google Drive API (google-api-python-client)
- Testing: pytest + pytest-asyncio
- Build: hatchling

## Key Commands
- Install dependencies: `uv sync --extra dev`
- Run the agent: `bws run -- uv run python -m tbc_agent.main`
- Run tests: `bws run -- uv run pytest`
- Run tests with verbose output: `bws run -- uv run pytest -v`

## Project Structure
- `src/tbc_agent/` — Core source code
  - `main.py` — Entry point, Config, and wiring
  - `orchestrator.py` — Agent loop / cycle coordinator
  - `llm_interface.py` — pydantic-ai Agent factory and response types
  - `input_events.py` — Input abstraction (EventRecord, CliProducer)
  - `output_channels.py` — Output abstraction (ResponseRecord, CliChannel)
  - `conversation_state.py` — In-memory sliding-window message history
  - `prompt_registry.py` — Source-to-system-prompt mapping
  - `observability.py` — Langfuse tracing implementation
  - `tool_loader.py` — Filesystem-based tool discovery
  - `tools/` — Tool implementations (current_time, google_drive)
- `tests/` — Test suite mirroring source structure
  - `tools/` — Tool-specific tests

See `README.md` for detailed architecture and `tbc_agent_design_context.md` for design rationale.

## Development Security and Safety
- Environment variables contain the user's private secrets. Respecting this privacy is *critical* to maintaining safety and security.
- **ALWAYS** respect the user's privacy.
- **NEVER** read any .env files 
- **NEVER** examine any environment variables.

## Coding Standards & Rules
- **Always** use type hints on all function signatures and class attributes.
- Keep all blocks independent and testable via dependency injection.
- Return errors as values (`LlmError`) rather than raising exceptions across block boundaries.

## Testing Expectations
- All new code must have corresponding tests.
- Unit tests use test doubles (FakeProducer, FunctionModel, CapturingChannel) to isolate the block under test.
- Integration tests (`test_integration.py`) use real components with a `FunctionModel` to simulate the LLM.
- Tool tests mock `_get_drive_service` to avoid real API calls.
- Run `uv run pytest` before committing changes.


## Architecture Notes
- **Five-block design**: Input (EventRecord) → Orchestrator → LLM (Agent) → Output (ResponseRecord), with State and Observability as supporting blocks.
- **Error handling**: `LlmError` is returned as a value; the orchestrator delivers an error reply and continues the loop.
- **Tool discovery**: `tool_loader.discover_tools()` scans `src/tbc_agent/tools/` for `.py` files (excluding `__init__.py` and `_`-prefixed) that expose a `tools` list.
- **Observability**: Optional Langfuse tracing via `LangfuseObservability`. Pass `None` to the Orchestrator to disable.
- **Conversation history**: Bounded to `max_turns` messages (not turns), stored in-memory only.

## Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `XAI_API_KEY` | Yes | xAI API key |
| `MODEL` | No | pydantic-ai model string (default: `xai:grok-4-1-fast-reasoning`) |
| `SYSTEM_MESSAGE` | No | Override default system prompt |
| `MAX_TURNS` | No | Conversation history window size (default: 40) |
| `LANGFUSE_ENABLED` | No | `"true"` to enable tracing |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse public key |
| `LANGFUSE_HOST` | No | Langfuse host URL |
| `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` | No (tools) | Service account JSON for Drive tools |
