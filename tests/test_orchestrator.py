"""
Tests for Block 5: Agent Loop / Orchestrator.
All tests follow T5.1–T5.15 from the design plan.

Test doubles replace all four dependency blocks so the orchestrator
can be exercised in isolation.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from tbc_agent.conversation_state import ConversationState, TurnRecord
from tbc_agent.input_events import EventRecord, InputProducer, ShutdownSignal
from tbc_agent.llm_interface import LlmError, LlmInterface, LlmResponse, MessageRecord, UsageRecord
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


class CapturingLlm(LlmInterface):
    """Records every call and returns responses from a fixed sequence."""

    def __init__(self, responses: list[LlmResponse | LlmError]) -> None:
        self._responses = iter(responses)
        self.calls: list[list[MessageRecord]] = []

    def call(
        self,
        messages: list[MessageRecord],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LlmResponse | LlmError:
        self.calls.append(messages)
        return next(self._responses)


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

def make_event(text: str, event_id: int = 1) -> EventRecord:
    return EventRecord(
        event_id=event_id,
        source="cli",
        timestamp=datetime.now(tz=timezone.utc),
        payload=text,
    )


def make_response(text: str = "Assistant reply") -> LlmResponse:
    return LlmResponse(
        reply_text=text,
        usage=UsageRecord(
            prompt_tokens=10,
            completion_tokens=20,
            reasoning_tokens=0,
            total_tokens=30,
        ),
        model_id="grok-4-1-fast-reasoning",
    )


SYSTEM_MSG = "You are a helpful assistant."


def make_orchestrator(producer, llm, channel, state=None, observability=None, registry=None):
    return Orchestrator(
        producer=producer,
        llm=llm,
        channel=channel,
        state=state or ConversationState(),
        prompt_registry=registry or PromptRegistry(default=SYSTEM_MSG),
        observability=observability,
    )


# ---------------------------------------------------------------------------
# T5.1 – T5.4: Prompt assembly
# ---------------------------------------------------------------------------

class TestPromptAssembly:
    def test_T5_1_system_message_is_first(self):
        """T5.1: The assembled prompt starts with the system message."""
        llm = CapturingLlm([make_response(), ])
        orch = make_orchestrator(
            producer=FakeProducer([make_event("hi"), ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
        )
        orch.run()

        first_msg = llm.calls[0][0]
        assert first_msg.role == "system"
        assert first_msg.text == SYSTEM_MSG

    def test_T5_2_history_follows_system_message_in_order(self):
        """T5.2: Conversation history follows the system message in chronological order."""
        state = ConversationState()
        state.append(TurnRecord(role="user", text="prior user", timestamp=datetime.now(tz=timezone.utc)))
        state.append(TurnRecord(role="assistant", text="prior assistant", timestamp=datetime.now(tz=timezone.utc)))

        llm = CapturingLlm([make_response()])
        orch = make_orchestrator(
            producer=FakeProducer([make_event("new question"), ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
            state=state,
        )
        orch.run()

        messages = llm.calls[0]
        assert messages[1].role == "user"
        assert messages[1].text == "prior user"
        assert messages[2].role == "assistant"
        assert messages[2].text == "prior assistant"

    def test_T5_3_current_user_turn_is_last(self):
        """T5.3: The current event payload is the final message in the prompt."""
        llm = CapturingLlm([make_response()])
        orch = make_orchestrator(
            producer=FakeProducer([make_event("what is the answer?"), ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
        )
        orch.run()

        last_msg = llm.calls[0][-1]
        assert last_msg.role == "user"
        assert last_msg.text == "what is the answer?"

    def test_T5_4_empty_history_yields_system_then_user(self):
        """T5.4: With no prior history, prompt is exactly [system, user]."""
        llm = CapturingLlm([make_response()])
        orch = make_orchestrator(
            producer=FakeProducer([make_event("first message"), ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
        )
        orch.run()

        messages = llm.calls[0]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"


# ---------------------------------------------------------------------------
# T5.5 – T5.7: Full cycle — happy path
# ---------------------------------------------------------------------------

class TestFullCycleHappyPath:
    def test_T5_5_event_flows_through_to_output(self):
        """T5.5: An input event leads to a response delivered via the output channel."""
        channel = CapturingChannel()
        orch = make_orchestrator(
            producer=FakeProducer([make_event("hello"), ShutdownSignal()]),
            llm=CapturingLlm([make_response("hi back")]),
            channel=channel,
        )
        orch.run()

        assert len(channel.delivered) == 1
        assert channel.delivered[0].reply_text == "hi back"

    def test_T5_6_both_turns_saved_after_successful_cycle(self):
        """T5.6: After a successful cycle, user turn and assistant turn are in history."""
        state = ConversationState()
        orch = make_orchestrator(
            producer=FakeProducer([make_event("hello"), ShutdownSignal()]),
            llm=CapturingLlm([make_response("hello back")]),
            channel=CapturingChannel(),
            state=state,
        )
        orch.run()

        history = state.history()
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].text == "hello"
        assert history[1].role == "assistant"
        assert history[1].text == "hello back"

    def test_T5_7_second_cycle_receives_first_turn_pair_in_history(self):
        """T5.7: On the second event, the LLM receives the first turn pair in its messages."""
        llm = CapturingLlm([make_response("reply one"), make_response("reply two")])
        orch = make_orchestrator(
            producer=FakeProducer([
                make_event("first", event_id=1),
                make_event("second", event_id=2),
                ShutdownSignal(),
            ]),
            llm=llm,
            channel=CapturingChannel(),
        )
        orch.run()

        second_call_messages = llm.calls[1]
        # [system, user:first, assistant:reply one, user:second]
        assert len(second_call_messages) == 4
        assert second_call_messages[1].text == "first"
        assert second_call_messages[2].text == "reply one"
        assert second_call_messages[3].text == "second"


# ---------------------------------------------------------------------------
# T5.8 – T5.10: Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_T5_8_llm_error_sends_message_through_output_channel(self):
        """T5.8: An LLM error produces a message via the output channel, not stderr."""
        channel = CapturingChannel()
        orch = make_orchestrator(
            producer=FakeProducer([make_event("question"), ShutdownSignal()]),
            llm=CapturingLlm([LlmError(reason="API down")]),
            channel=channel,
        )
        orch.run()

        assert len(channel.delivered) == 1
        assert channel.delivered[0].reply_text  # non-empty error message

    def test_T5_9_llm_error_does_not_save_turns_to_state(self):
        """T5.9: When the LLM errors, neither the user turn nor a failed response is saved."""
        state = ConversationState()
        orch = make_orchestrator(
            producer=FakeProducer([make_event("question"), ShutdownSignal()]),
            llm=CapturingLlm([LlmError(reason="API down")]),
            channel=CapturingChannel(),
            state=state,
        )
        orch.run()

        assert state.history() == []

    def test_T5_10_loop_continues_after_llm_error(self):
        """T5.10: After an LLM error the orchestrator processes the next event normally."""
        channel = CapturingChannel()
        llm = CapturingLlm([LlmError(reason="transient"), make_response("recovered")])
        orch = make_orchestrator(
            producer=FakeProducer([
                make_event("first", event_id=1),
                make_event("second", event_id=2),
                ShutdownSignal(),
            ]),
            llm=llm,
            channel=channel,
        )
        orch.run()

        # Two deliveries: error message + successful reply
        assert len(channel.delivered) == 2
        assert channel.delivered[1].reply_text == "recovered"


# ---------------------------------------------------------------------------
# T5.11 – T5.12: Shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    def test_T5_11_shutdown_signal_exits_loop(self):
        """T5.11: ShutdownSignal causes run() to return cleanly."""
        llm = CapturingLlm([])
        orch = make_orchestrator(
            producer=FakeProducer([ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
        )
        orch.run()  # must not raise or block

        assert llm.calls == []  # no LLM calls made

    def test_T5_12_no_partial_state_after_shutdown(self):
        """T5.12: History contains only complete turn pairs after shutdown."""
        state = ConversationState()
        # First event succeeds, second triggers LLM error, then shutdown
        llm = CapturingLlm([make_response("ok"), LlmError("fail")])
        orch = make_orchestrator(
            producer=FakeProducer([
                make_event("good", event_id=1),
                make_event("bad", event_id=2),
                ShutdownSignal(),
            ]),
            llm=llm,
            channel=CapturingChannel(),
            state=state,
        )
        orch.run()

        history = state.history()
        # Only the first successful pair should be in history
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"


# ---------------------------------------------------------------------------
# T5.13 – T5.15: Observability toggle
# ---------------------------------------------------------------------------

class TestObservabilityToggle:
    def test_T5_13_observability_enabled_called_per_cycle(self):
        """T5.13: When observability is enabled, it is notified at cycle start/end and LLM call."""
        obs = MagicMock()
        orch = make_orchestrator(
            producer=FakeProducer([make_event("hi"), ShutdownSignal()]),
            llm=CapturingLlm([make_response()]),
            channel=CapturingChannel(),
            observability=obs,
        )
        orch.run()

        obs.on_cycle_start.assert_called_once()
        obs.on_llm_response.assert_called_once()
        obs.on_cycle_end.assert_called_once()

    def test_T5_14_observability_disabled_no_calls(self):
        """T5.14: When observability=None, no observability calls are made (no errors)."""
        orch = make_orchestrator(
            producer=FakeProducer([make_event("hi"), ShutdownSignal()]),
            llm=CapturingLlm([make_response()]),
            channel=CapturingChannel(),
            observability=None,
        )
        orch.run()  # must not raise

    def test_T5_15_observability_toggle_does_not_change_functional_behavior(self):
        """T5.15: Same input produces same output regardless of observability setting."""
        def run_with_obs(obs):
            channel = CapturingChannel()
            state = ConversationState()
            orch = make_orchestrator(
                producer=FakeProducer([make_event("hello"), ShutdownSignal()]),
                llm=CapturingLlm([make_response("same reply")]),
                channel=channel,
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
        llm = CapturingLlm([make_response()])

        event = EventRecord(
            event_id=1,
            source="webhook",
            timestamp=datetime.now(tz=timezone.utc),
            payload="hello from webhook",
        )
        orch = make_orchestrator(
            producer=FakeProducer([event, ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
            registry=registry,
        )
        orch.run()

        system_msg = llm.calls[0][0]
        assert system_msg.role == "system"
        assert system_msg.text == "Webhook system prompt"

    def test_unknown_source_uses_default_prompt(self):
        """Events from an unmapped source get the default system prompt."""
        registry = PromptRegistry(prompts={"cli": "CLI prompt"}, default="fallback prompt")
        llm = CapturingLlm([make_response()])

        event = EventRecord(
            event_id=1,
            source="unknown_source",
            timestamp=datetime.now(tz=timezone.utc),
            payload="hello",
        )
        orch = make_orchestrator(
            producer=FakeProducer([event, ShutdownSignal()]),
            llm=llm,
            channel=CapturingChannel(),
            registry=registry,
        )
        orch.run()

        assert llm.calls[0][0].text == "fallback prompt"
