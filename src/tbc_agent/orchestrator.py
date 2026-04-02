"""
Block 5: Agent Loop / Orchestrator.

Orchestrator coordinates the full chat cycle:
  1. Wait for an input event
  2. Read conversation history
  3. Assemble prompt: [system message] + [history] + [current user turn]
  4. Call the LLM
  5. Deliver the response (or an error message) via the output channel
  6. Update conversation state on success
  7. Repeat until ShutdownSignal

ObservabilityClient defines the hooks for optional tracing.
NoOpObservability is used when observability is disabled (None passed to Orchestrator).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from tbc_agent.conversation_state import ConversationState, TurnRecord
from tbc_agent.input_events import EventRecord, InputProducer, ShutdownSignal
from tbc_agent.llm_interface import LlmError, LlmInterface, LlmResponse, MessageRecord
from tbc_agent.output_channels import OutputChannel, ResponseRecord

ERROR_REPLY = "I was unable to get a response, please try again."


class ObservabilityClient(ABC):
    """Hook points called by the orchestrator at key cycle stages."""

    @abstractmethod
    def on_cycle_start(self, event: EventRecord) -> None: ...

    @abstractmethod
    def on_prompt_assembled(self, messages: list[MessageRecord]) -> None: ...

    @abstractmethod
    def on_llm_response(self, response: LlmResponse | LlmError) -> None: ...

    @abstractmethod
    def on_cycle_end(self) -> None: ...


class NoOpObservability(ObservabilityClient):
    """Used when observability is toggled off. All methods are no-ops."""

    def on_cycle_start(self, event: EventRecord) -> None:
        pass

    def on_prompt_assembled(self, messages: list[MessageRecord]) -> None:
        pass

    def on_llm_response(self, response: LlmResponse | LlmError) -> None:
        pass

    def on_cycle_end(self) -> None:
        pass


class Orchestrator:
    """Coordinates the chat agent cycle.

    Args:
        producer:       Source of input events.
        llm:            LLM implementation to call.
        channel:        Output channel to deliver responses through.
        state:          Conversation history store.
        system_message: The system prompt sent at the start of every LLM call.
        observability:  Optional observability client. Pass None to disable tracing.
    """

    def __init__(
        self,
        producer: InputProducer,
        llm: LlmInterface,
        channel: OutputChannel,
        state: ConversationState,
        system_message: str,
        observability: ObservabilityClient | None = None,
    ) -> None:
        self._producer = producer
        self._llm = llm
        self._channel = channel
        self._state = state
        self._system_message = system_message
        self._obs = observability if observability is not None else NoOpObservability()

    def run(self) -> None:
        """Run the agent loop until a ShutdownSignal is received."""
        while True:
            event = self._producer.next_event()

            if isinstance(event, ShutdownSignal):
                break

            self._obs.on_cycle_start(event)

            messages = self._assemble_prompt(event.payload)
            self._obs.on_prompt_assembled(messages)

            response = self._llm.call(messages)
            self._obs.on_llm_response(response)

            if isinstance(response, LlmError):
                self._channel.deliver(ResponseRecord(reply_text=ERROR_REPLY))
                self._obs.on_cycle_end()
                continue

            self._channel.deliver(ResponseRecord(reply_text=response.reply_text))

            now = datetime.now(tz=timezone.utc)
            self._state.append(TurnRecord(role="user", text=event.payload, timestamp=now))
            self._state.append(TurnRecord(role="assistant", text=response.reply_text, timestamp=now))

            self._obs.on_cycle_end()

    def _assemble_prompt(self, user_text: str) -> list[MessageRecord]:
        """Build the message list: system message + history + current user turn."""
        messages: list[MessageRecord] = [
            MessageRecord(role="system", text=self._system_message)
        ]
        for turn in self._state.history():
            messages.append(MessageRecord(role=turn.role, text=turn.text))
        messages.append(MessageRecord(role="user", text=user_text))
        return messages
