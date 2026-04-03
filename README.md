# tbc_agent

A CLI chat agent in Python 3.12+ built on [pydantic-ai](https://ai.pydantic.dev/). Five functional blocks wired together via dependency injection into an `Orchestrator`.

---

## Usage

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management

### Setup

```bash
# Install dependencies
uv sync --extra dev
```

### Configuration

Set environment variables before running:

| Variable | Required | Description |
|---|---|---|
| `XAI_API_KEY` | Yes | xAI API key (read automatically by pydantic-ai's xAI provider) |
| `MODEL` | No | pydantic-ai model string (default: `xai:grok-4-1-fast-reasoning`). Examples: `openai:gpt-4o`, `anthropic:claude-sonnet-4-5` |
| `SYSTEM_MESSAGE` | No | Override the default system prompt fallback for all sources |
| `MAX_TURNS` | No | Conversation history window size (default: 40) |
| `LANGFUSE_ENABLED` | No | `"true"` to enable observability tracing |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse public key |
| `LANGFUSE_HOST` | No | Langfuse host (default: `https://cloud.langfuse.com`) |

### Running

```bash
export XAI_API_KEY="your-key-here"
uv run python -m tbc_agent.main
```

To use a different provider:

```bash
export MODEL="openai:gpt-4o"
export OPENAI_API_KEY="your-key-here"
uv run python -m tbc_agent.main
```

Type messages at the prompt. Type `exit` or press Ctrl-D to quit.

### Running Tests

```bash
uv run --extra dev pytest
```

---

## Implementation Reference

### Entry Point

`src/tbc_agent/main.py`

- `Config.from_env()` — reads env vars
- `create_agent(config)` — instantiates all concrete blocks and wires them; accepts override params for test injection
- `main()` — loads config, builds agent, starts loop

---

### Block 1 — Input (`input_events.py`)

- `InputProducer` (ABC): `next_event() -> EventRecord | ShutdownSignal`
- `CliProducer`: reads from stdin; skips blanks; `ShutdownSignal` on EOF or "exit"
- `EventRecord`: `payload: str`, `source: str`, `timestamp: datetime`

---

### Block 2 — LLM Interface (`llm_interface.py`)

- `create_llm_agent(model, registry) -> Agent[str, str]` — factory that builds a pydantic-ai Agent with a dynamic system prompt driven by the `PromptRegistry`
- Accepts a model string (e.g. `"xai:grok-4-1-fast-reasoning"`) or a `Model` instance (e.g. `FunctionModel` for testing)
- `UsageRecord`: prompt/completion/reasoning/total tokens; `visible_completion_tokens` computed field
- `LlmResponse`: `reply_text`, `usage`, `model_id`
- `LlmError`: `reason: str` — returned by the orchestrator when pydantic-ai raises

---

### Block 3 — Output (`output_channels.py`)

- `OutputChannel` (ABC): `deliver(record: ResponseRecord) -> DeliveryOutcome`
- `CliChannel`: writes reply text to stdout

---

### Block 4 — Conversation State (`conversation_state.py`)

- `ConversationState`: bounded in-memory history of pydantic-ai `ModelMessage` objects using `deque(maxlen=max_turns)`
- `extend(messages)` adds messages; `history()` returns a list snapshot
- Sliding window drops oldest messages when the limit is exceeded

---

### Block 5 — Orchestrator (`orchestrator.py`)

`Orchestrator(producer, agent, channel, state, observability=None)`

**Loop (runs until `ShutdownSignal`):**
1. `producer.next_event()`
2. `agent.run_sync(payload, deps=source, message_history=...)` — pydantic-ai handles system prompt resolution, retry, and response parsing
3. On error: deliver error reply and continue
4. `channel.deliver(response)`
5. `state.extend(new_messages)`

**Observability hooks (`ObservabilityClient` ABC):**
- `on_cycle_start`, `on_llm_call`, `on_llm_response`, `on_cycle_end`
- `NoOpObservability`: used when `observability=None` is passed
- `LangfuseObservability` (`observability.py`): sends one trace + one LLM span per cycle; swallows its own failures

---

### Prompt Registry (`prompt_registry.py`)

- `PromptRegistry`: maps event source strings to system prompts; falls back to a default prompt for unknown sources
- `DEFAULT_SYSTEM_PROMPT`: generic fallback prompt
- `DEFAULT_PROMPTS`: initial source-to-prompt mappings (currently `"cli"`)
- Integrated via pydantic-ai's dynamic `system_prompt` — the Agent receives `event.source` as deps and the registry resolves the prompt

---

### Design Decisions

- **pydantic-ai as core framework**: LLM calls, retry logic, prompt assembly, and provider abstraction are all handled by pydantic-ai's `Agent`
- **`LlmError` as value**: the orchestrator catches pydantic-ai exceptions in `_call_llm` and returns `LlmError` — no exception handling in the main loop
- **Provider switching via model string**: change `MODEL` env var to switch providers (e.g. `openai:gpt-4o`, `anthropic:claude-sonnet-4-5`)
- **Observability is optional**: pass `None` to `Orchestrator`; `NoOpObservability` is substituted automatically
- **Prompt registry**: system prompt selection is source-driven via pydantic-ai deps; the registry owns lookup, pydantic-ai owns assembly

---

### Tests (`tests/`)

Test doubles:
- `FakeProducer`: returns events from a fixed sequence
- `FunctionModel`: pydantic-ai's test model — records calls, returns scripted responses
- `CapturingChannel`: records every delivered record

Full TDD suite covering orchestrator cycles, error paths, observability hooks, prompt registry, conversation state, and startup wiring.
