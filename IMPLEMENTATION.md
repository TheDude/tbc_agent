# tbc_agent — Implementation Reference

A CLI chat agent in Python 3.12+. Five functional blocks wired together via dependency injection into an `Orchestrator`.

---

## Entry Point

`src/tbc_agent/main.py`

- `Config.from_env()` — reads env vars; requires `XAI_API_KEY`
- `create_agent(config)` — instantiates all concrete blocks and wires them; accepts override params for test injection
- `main()` — loads config, builds agent, starts loop

**Optional env vars:** `LANGFUSE_ENABLED`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST`, `SYSTEM_MESSAGE`, `MAX_TURNS` (default 40)

---

## Block 1 — Input (`input_events.py`)

- `InputProducer` (ABC): `next_event() -> EventRecord | ShutdownSignal`
- `CliProducer`: reads from stdin; skips blanks; `ShutdownSignal` on EOF or "exit"
- `EventRecord`: `payload: str`, `source: str`, `timestamp: datetime`
- **More implementations planned**

---

## Block 2 — LLM Interface (`llm_interface.py`)

- `LlmInterface` (ABC): `call(messages, *, temperature, max_tokens) -> LlmResponse | LlmError`
- `GrokInterface`: calls xAI's `grok-4-1-fast-reasoning` via OpenAI-compatible API; retries on 429/5xx with exponential backoff (up to 3 attempts); **never raises** — returns `LlmError` on failure
- `MessageRecord`: `role: str`, `text: str`
- `UsageRecord`: prompt/completion/reasoning/total tokens; `visible_completion_tokens` computed field
- `LlmResponse`: `reply_text`, `usage`, `model_id`
- `LlmError`: `reason: str`

---

## Block 3 — Output (`output_channels.py`)

- `OutputChannel` (ABC): `deliver(record: ResponseRecord) -> DeliveryOutcome`
- `CliChannel`: writes reply text to stdout
- **More implementations planned**

---

## Block 4 — Conversation State (`conversation_state.py`)

- `ConversationState`: bounded in-memory history using `deque(maxlen=max_turns)`
- `TurnRecord`: `role: str`, `text: str`, `timestamp: datetime`; roles must be `"user"` or `"assistant"` (system message is orchestrator config, not stored here)
- `history()` returns a list snapshot; `append()` adds a turn

---

## Block 5 — Orchestrator (`orchestrator.py`)

`Orchestrator(producer, llm, channel, state, system_message, observability=None)`

**Loop (runs until `ShutdownSignal`):**
1. `producer.next_event()`
2. Assemble prompt: system message + history + current user turn
3. `llm.call(messages)` → on `LlmError`: deliver error reply and continue
4. `channel.deliver(response)`
5. Append user + assistant turns to state

**Observability hooks (`ObservabilityClient` ABC):**
- `on_cycle_start`, `on_prompt_assembled`, `on_llm_response`, `on_cycle_end`
- `NoOpObservability`: used when `observability=None` is passed
- `LangfuseObservability` (`observability.py`): sends one trace + one LLM span per cycle; swallows its own failures

---

## Design Decisions

- **ABCs over `Protocol`**: runtime safety at instantiation without requiring mypy; appropriate given planned additional implementations
- **`LlmError` as value**: caller does `isinstance(response, LlmError)` — no exception handling in the loop
- **Observability is optional**: pass `None` to `Orchestrator`; `NoOpObservability` is substituted automatically
- **`create_agent()` override params**: allow test doubles to be injected without patching

---

## Tests (`tests/`)

Test doubles (all implement the relevant ABCs):
- `FakeProducer`: returns events from a fixed sequence
- `CapturingLlm`: records every call; returns responses from a fixed sequence
- `CapturingChannel`: records every delivered record

Full TDD suite covering orchestrator cycles, error paths, retry logic, observability hooks, and state management.
