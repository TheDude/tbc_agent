## Project Architecture

This is a modular chat agent built with **pydantic-ai**. The architecture follows a clean separation of concerns with five core blocks plus supporting infrastructure.

### Core Blocks

| Block | Module | Responsibility |
|-------|--------|----------------|
| 1 | `input_events.py` | Input event abstraction (`EventRecord`, `ShutdownSignal`, `InputProducer`, `CliProducer`) |
| 2 | `llm_interface.py` | LLM interface types (`UsageRecord`, `LlmResponse`, `LlmError`) and agent factory |
| 3 | `output_channels.py` | Output channel abstraction (`ResponseRecord`, `DeliveryOutcome`, `OutputChannel`, `CliChannel`) |
| 4 | `conversation_state.py` | In-memory conversation history with configurable sliding window |
| 5 | `orchestrator.py` | Coordinates the full chat cycle (input → LLM → output → state update) |

### Supporting Infrastructure

| Module | Responsibility |
|--------|----------------|
| `tool_loader.py` | Filesystem-based tool discovery — scans `tools/` for `.py` files and collects `pydantic_ai.Tool` instances |
| `prompt_registry.py` | Maps event sources to system prompts with fallback default |
| `observability.py` | Langfuse implementation of `ObservabilityClient` — one trace per cycle, span for LLM call |
| `main.py` | Startup/wiring — `Config` from env vars, `create_agent()` factory, `main()` entrypoint |

### Key Architectural Patterns

- **Plugin-based tools**: Tools are discovered from `src/tbc_agent/tools/` at runtime. Each `.py` file exports a `tools` list of `pydantic_ai.Tool` instances.
- **Extensible I/O**: Abstract base classes (`InputProducer`, `OutputChannel`) allow swapping implementations (CLI, web, messaging platforms).
- **Sliding window state**: `ConversationState` maintains bounded history (default 40 turns) using `collections.deque(maxlen=...)`.
- **Optional observability**: Langfuse tracing is toggled via `LANGFUSE_ENABLED`; failures are silently swallowed to avoid affecting agent behavior.
- **Dynamic system prompts**: `PromptRegistry` resolves source-specific prompts at call time via `RunContext.deps`.
- **Error handling**: LLM errors return `LlmError` objects instead of raising — caller inspects and handles gracefully.
- **OAuth-first integrations**: Shared Authlib + keyring OAuth2 helpers live in `src/tbc_agent/auth/`. Tools request credentials via provider-specific helpers (e.g., Google Drive) which store tokens in the OS keyring and fall back to legacy auth when needed.

### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `xai:grok-4-1-fast-reasoning` | pydantic-ai model string |
| `LANGFUSE_ENABLED` | `false` | Enable Langfuse observability |
| `LANGFUSE_SECRET_KEY` | — | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse public key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host URL |
| `SYSTEM_MESSAGE` | (built-in default) | Override default system prompt |
| `MAX_TURNS` | `40` | Conversation history window size |

### Commands

```bash
# Run the agent
bws run -- python -m tbc_agent.main

# Run all tests
bws run -- uv run pytest

# Run tool tests only
bws run -- uv run pytest tests/tools/
```

---

## Tool Development

For details on developing agent tools, see **[src/tbc_agent/tools/AGENTS.md](./src/tbc_agent/tools/AGENTS.md)**.

Key points:
- One `.py` file per tool in `src/tbc_agent/tools/`
- Export `tools = [Tool(function), ...]` at module level
- All tool functions must have type hints and return `str`
- Tools should be independent (no imports from other project modules)
- Tests live in `tests/tools/test_<tool_name>.py`

---

## Development Security and Safety

These rules protect the developer's secrets from leaking into an AI agent's context when the AI is acting as a developer working on this codebase. They govern how *you*, the AI agent, should behave when modifying or examining this code, not how the compiled software operates.

When you are acting as a developer AI (e.g., reading code, making changes, debugging):
- **NEVER** read any `.env` files or environment variables. Secrets are injected at runtime by `bws` when the software runs; you as the developer AI must never inspect them during development.
- **ALWAYS** respect the developer's privacy. Never examine, log, or echo secrets that may appear in code comments, configuration files, or documentation.
- **Only use `bws run` to execute commands** when testing your changes. The `bws` tool injects credentials; do not invoke it with other subcommands or attempt to obtain credentials through other means.

These rules do NOT apply to the software itself when it is running as an agent. The software may read environment variables (e.g., for Langfuse configuration or Google Drive credentials) as part of its normal operation when executed via `bws run`. This restriction is solely for AI agents acting in a developer role during code modification and review.