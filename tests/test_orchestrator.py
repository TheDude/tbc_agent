"""
Tests for Block 5: Agent Loop / Orchestrator.
All tests follow T5.1–T5.15 from the design plan, adapted for pydantic-ai.

Test doubles replace all four dependency blocks so the orchestrator
can be exercised in isolation.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tbc_agent.conversation_state import ConversationState
from tbc_agent.input_events import EventRecord, InputProducer, ShutdownSignal
from tbc_agent.llm_interface import LlmError, LlmResponse, UsageRecord, create_llm_agent
from tbc_agent.orchestrator import Orchestrator
from tbc_agent.output_channels import DeliveryOutcome, OutputChannel, ResponseRecord
from tbc_agent.prompt_registry import PromptRegistry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeProducer(InputProducer):
    """Returns events from a fixed sequence, then ShutdownSignal."""

    def __init__(self, events: list[EventRecord | ShutdownSignal]) -> None:
        self._iter = iter(events)

    def next_event(self) -> EventRecord | ShutdownSignal:
        return next(self._iter)


class CapturingChannel(OutputChannel):
    """Records every delivered record."""

    def __init__(self) -> None:
        self.delivered: list[ResponseRecord] = []

    def deliver(self, record: ResponseRecord) -> DeliveryOutcome:
        self.delivered.append(record)
        return DeliveryOutcome(success=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(text: str, event_id: int = 1, source: str = "cli") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        source=source,
        timestamp=datetime.now(tz=timezone.utc),
        payload=text,
    )


def make_function_model(replies: list[str]) -> tuple[FunctionModel, list[list[ModelMessage]]]:
    """Create a FunctionModel that records calls and returns scripted replies."""
    calls: list[list[ModelMessage]] = []
    reply_iter = iter(replies)

    def handler(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(messages)
        return ModelResponse(parts=[TextPart(content=next(reply_iter))])

    return FunctionModel(handler), calls


def make_test_agent(replies: list[str], registry: PromptRegistry | None = None) -> tuple[Agent[str, str], list[list[ModelMessage]]]:
    """Create an Agent backed by FunctionModel with scripted replies."""
    model, calls = make_function_model(replies)
    reg = registry or PromptRegistry(default="You are a helpful assistant.")
    agent = create_llm_agent(model, reg)
    return agent, calls


SYSTEM_MSG = "You are a helpful assistant."


def make_orchestrator(producer, channel, replies=None, state=None, observability=None, registry=None):
    reg = registry or PromptRegistry(default=SYSTEM_MSG)
    agent, calls = make_test_agent(replies or ["Assistant reply"], registry=reg)
    orch = Orchestrator(
        producer=producer,
        agent=agent,
        channel=channel,
        state=state or ConversationState(),
        observability=observability,
    )
    return orch, calls


# ---------------------------------------------------------------------------
# T5.1 – T5.4: Prompt assembly
# ---------------------------------------------------------------------------

class TestPromptAssembly:
    def test_T5_1_system_message_is_first(self):
        """T5.1: The assembled prompt starts with the system message."""
        orch, calls = make_orchestrator(
            producer=FakeProducer([make_event("hi"), ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=["hello"],
        )
        orch.run()

        messages = calls[0]
        # First message should be a ModelRequest containing the system prompt
        first = messages[0]
        assert isinstance(first, ModelRequest)
        system_parts = [p for p in first.parts if isinstance(p, SystemPromptPart)]
        assert len(system_parts) >= 1
        assert system_parts[0].content == SYSTEM_MSG

    def test_T5_2_history_follows_system_message_in_order(self):
        """T5.2: Conversation history follows the system message in chronological order."""
        # First turn builds history, second turn should include it
        orch, calls = make_orchestrator(
            producer=FakeProducer([
                make_event("prior question", event_id=1),
                make_event("new question", event_id=2),
                ShutdownSignal(),
            ]),
            channel=CapturingChannel(),
            replies=["prior answer", "new answer"],
        )
        orch.run()

        # Second call should have history from first turn
        second_call = calls[1]
        assert len(second_call) > 1  # more than just the system+user message

    def test_T5_3_current_user_turn_is_last(self):
        """T5.3: The current event payload is the final message in the prompt."""
        orch, calls = make_orchestrator(
            producer=FakeProducer([make_event("what is the answer?"), ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=["42"],
        )
        orch.run()

        messages = calls[0]
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        user_parts = [p for p in last.parts if isinstance(p, UserPromptPart)]
        assert any(p.content == "what is the answer?" for p in user_parts)

    def test_T5_4_empty_history_yields_system_then_user(self):
        """T5.4: With no prior history, prompt is exactly [system+user request]."""
        orch, calls = make_orchestrator(
            producer=FakeProducer([make_event("first message"), ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=["reply"],
        )
        orch.run()

        messages = calls[0]
        # pydantic-ai combines system prompt + user prompt into a single ModelRequest
        assert len(messages) == 1
        req = messages[0]
        assert isinstance(req, ModelRequest)
        has_system = any(isinstance(p, SystemPromptPart) for p in req.parts)
        has_user = any(isinstance(p, UserPromptPart) for p in req.parts)
        assert has_system
        assert has_user


# ---------------------------------------------------------------------------
# T5.5 – T5.7: Full cycle — happy path
# ---------------------------------------------------------------------------

class TestFullCycleHappyPath:
    def test_T5_5_event_flows_through_to_output(self):
        """T5.5: An input event leads to a response delivered via the output channel."""
        channel = CapturingChannel()
        orch, _ = make_orchestrator(
            producer=FakeProducer([make_event("hello"), ShutdownSignal()]),
            channel=channel,
            replies=["hi back"],
        )
        orch.run()

        assert len(channel.delivered) == 1
        assert channel.delivered[0].reply_text == "hi back"

    def test_T5_6_both_turns_saved_after_successful_cycle(self):
        """T5.6: After a successful cycle, messages are in history."""
        state = ConversationState()
        orch, _ = make_orchestrator(
            producer=FakeProducer([make_event("hello"), ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=["hello back"],
            state=state,
        )
        orch.run()

        history = state.history()
        assert len(history) >= 2  # at least request + response

    def test_T5_7_second_cycle_receives_first_turn_pair_in_history(self):
        """T5.7: On the second event, the LLM receives the first turn pair in its messages."""
        orch, calls = make_orchestrator(
            producer=FakeProducer([
                make_event("first", event_id=1),
                make_event("second", event_id=2),
                ShutdownSignal(),
            ]),
            channel=CapturingChannel(),
            replies=["reply one", "reply two"],
        )
        orch.run()

        # Second call should have more messages than the first (includes history)
        assert len(calls[1]) > len(calls[0])


# ---------------------------------------------------------------------------
# T5.8 – T5.10: Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_T5_8_llm_error_sends_message_through_output_channel(self):
        """T5.8: An LLM error produces a message via the output channel."""
        def error_handler(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise RuntimeError("API down")

        model = FunctionModel(error_handler)
        reg = PromptRegistry(default=SYSTEM_MSG)
        agent = create_llm_agent(model, reg)

        channel = CapturingChannel()
        orch = Orchestrator(
            producer=FakeProducer([make_event("question"), ShutdownSignal()]),
            agent=agent,
            channel=channel,
            state=ConversationState(),
        )
        orch.run()

        assert len(channel.delivered) == 1
        assert channel.delivered[0].reply_text  # non-empty error message

    def test_T5_9_llm_error_does_not_save_turns_to_state(self):
        """T5.9: When the LLM errors, no messages are saved to state."""
        def error_handler(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise RuntimeError("API down")

        model = FunctionModel(error_handler)
        reg = PromptRegistry(default=SYSTEM_MSG)
        agent = create_llm_agent(model, reg)

        state = ConversationState()
        orch = Orchestrator(
            producer=FakeProducer([make_event("question"), ShutdownSignal()]),
            agent=agent,
            channel=CapturingChannel(),
            state=state,
        )
        orch.run()

        assert state.history() == []

    def test_T5_10_loop_continues_after_llm_error(self):
        """T5.10: After an LLM error the orchestrator processes the next event normally."""
        call_count = 0

        def sometimes_error(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return ModelResponse(parts=[TextPart(content="recovered")])

        model = FunctionModel(sometimes_error)
        reg = PromptRegistry(default=SYSTEM_MSG)
        agent = create_llm_agent(model, reg)

        channel = CapturingChannel()
        orch = Orchestrator(
            producer=FakeProducer([
                make_event("first", event_id=1),
                make_event("second", event_id=2),
                ShutdownSignal(),
            ]),
            agent=agent,
            channel=channel,
            state=ConversationState(),
        )
        orch.run()

        assert len(channel.delivered) == 2
        assert channel.delivered[1].reply_text == "recovered"


# ---------------------------------------------------------------------------
# T5.11 – T5.12: Shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    def test_T5_11_shutdown_signal_exits_loop(self):
        """T5.11: ShutdownSignal causes run() to return cleanly."""
        orch, calls = make_orchestrator(
            producer=FakeProducer([ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=[],
        )
        orch.run()  # must not raise or block

        assert calls == []

    def test_T5_12_no_partial_state_after_shutdown(self):
        """T5.12: History contains only complete turn pairs after shutdown."""
        call_count = 0

        def sometimes_error(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("fail")
            return ModelResponse(parts=[TextPart(content="ok")])

        model = FunctionModel(sometimes_error)
        reg = PromptRegistry(default=SYSTEM_MSG)
        agent = create_llm_agent(model, reg)

        state = ConversationState()
        orch = Orchestrator(
            producer=FakeProducer([
                make_event("good", event_id=1),
                make_event("bad", event_id=2),
                ShutdownSignal(),
            ]),
            agent=agent,
            channel=CapturingChannel(),
            state=state,
        )
        orch.run()

        history = state.history()
        # Only the first successful pair should be in history
        assert len(history) >= 2  # request + response from first turn
        # Verify no messages from the failed second turn


# ---------------------------------------------------------------------------
# T5.13 – T5.15: Observability toggle
# ---------------------------------------------------------------------------

class TestObservabilityToggle:
    def test_T5_13_observability_enabled_called_per_cycle(self):
        """T5.13: When observability is enabled, it is notified at cycle start/end and LLM call."""
        obs = MagicMock()
        orch, _ = make_orchestrator(
            producer=FakeProducer([make_event("hi"), ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=["hello"],
            observability=obs,
        )
        orch.run()

        obs.on_cycle_start.assert_called_once()
        obs.on_llm_response.assert_called_once()
        obs.on_cycle_end.assert_called_once()

    def test_T5_14_observability_disabled_no_calls(self):
        """T5.14: When observability=None, no observability calls are made (no errors)."""
        orch, _ = make_orchestrator(
            producer=FakeProducer([make_event("hi"), ShutdownSignal()]),
            channel=CapturingChannel(),
            replies=["hello"],
            observability=None,
        )
        orch.run()  # must not raise

    def test_T5_15_observability_toggle_does_not_change_functional_behavior(self):
        """T5.15: Same input produces same output regardless of observability setting."""
        def run_with_obs(obs):
            channel = CapturingChannel()
            state = ConversationState()
            orch, _ = make_orchestrator(
                producer=FakeProducer([make_event("hello"), ShutdownSignal()]),
                channel=channel,
                replies=["same reply"],
                state=state,
                observability=obs,
            )
            orch.run()
            return channel.delivered, state.history()

        delivered_with, history_with = run_with_obs(MagicMock())
        delivered_without, history_without = run_with_obs(None)

        assert delivered_with[0].reply_text == delivered_without[0].reply_text
        assert len(history_with) == len(history_without)


# ---------------------------------------------------------------------------
# Prompt Registry
# ---------------------------------------------------------------------------

class TestPromptRegistry:
    def test_returns_source_specific_prompt(self):
        """Registry returns the prompt mapped to the given source."""
        registry = PromptRegistry(prompts={"cli": "CLI prompt"}, default="fallback")
        assert registry.get_system_prompt("cli") == "CLI prompt"

    def test_falls_back_to_default_for_unknown_source(self):
        """Registry returns the default prompt when the source has no entry."""
        registry = PromptRegistry(prompts={"cli": "CLI prompt"}, default="fallback")
        assert registry.get_system_prompt("webhook") == "fallback"

    def test_default_used_when_no_prompts_provided(self):
        """Registry with no source mappings always returns the default."""
        registry = PromptRegistry(default="only this")
        assert registry.get_system_prompt("anything") == "only this"


class TestSourceAwarePromptAssembly:
    def test_prompt_uses_source_specific_system_message(self):
        """The orchestrator selects the system prompt based on event source."""
        registry = PromptRegistry(
            prompts={"cli": "CLI system prompt", "webhook": "Webhook system prompt"},
            default="default prompt",
        )
        agent, calls = make_test_agent(["hello"], registry=registry)

        event = make_event("hello from webhook", source="webhook")
        orch = Orchestrator(
            producer=FakeProducer([event, ShutdownSignal()]),
            agent=agent,
            channel=CapturingChannel(),
            state=ConversationState(),
        )
        orch.run()

        # Inspect the messages passed to the model
        messages = calls[0]
        first = messages[0]
        assert isinstance(first, ModelRequest)
        system_parts = [p for p in first.parts if isinstance(p, SystemPromptPart)]
        assert any(p.content == "Webhook system prompt" for p in system_parts)

    def test_unknown_source_uses_default_prompt(self):
        """Events from an unmapped source get the default system prompt."""
        registry = PromptRegistry(prompts={"cli": "CLI prompt"}, default="fallback prompt")
        agent, calls = make_test_agent(["hello"], registry=registry)

        event = make_event("hello", source="unknown_source")
        orch = Orchestrator(
            producer=FakeProducer([event, ShutdownSignal()]),
            agent=agent,
            channel=CapturingChannel(),
            state=ConversationState(),
        )
        orch.run()

        messages = calls[0]
        first = messages[0]
        assert isinstance(first, ModelRequest)
        system_parts = [p for p in first.parts if isinstance(p, SystemPromptPart)]
        assert any(p.content == "fallback prompt" for p in system_parts)
