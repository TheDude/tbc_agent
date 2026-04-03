"""
Block 5: Agent Loop / Orchestrator.

Orchestrator coordinates the full chat cycle:
  1. Wait for an input event
  2. Call the LLM via pydantic-ai Agent (system prompt resolved by source)
  3. Deliver the response (or an error message) via the output channel
  4. Update conversation state on success
  5. Repeat until ShutdownSignal

ObservabilityClient defines the hooks for optional tracing.
NoOpObservability is used when observability is disabled (None passed to Orchestrator).
"""

from abc import ABC, abstractmethod

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from tbc_agent.conversation_state import ConversationState
from tbc_agent.input_events import EventRecord, InputProducer, ShutdownSignal
from tbc_agent.llm_interface import LlmError, LlmResponse, UsageRecord
from tbc_agent.output_channels import OutputChannel, ResponseRecord

ERROR_REPLY = "I was unable to get a response, please try again."


class ObservabilityClient(ABC):
    """Hook points called by the orchestrator at key cycle stages."""

    @abstractmethod
    def on_cycle_start(self, event: EventRecord) -> None: ...

    @abstractmethod
    def on_llm_call(self, messages: list[ModelMessage]) -> None: ...

    @abstractmethod
    def on_llm_response(self, response: LlmResponse | LlmError) -> None: ...

    @abstractmethod
    def on_cycle_end(self) -> None: ...


class NoOpObservability(ObservabilityClient):
    """Used when observability is toggled off. All methods are no-ops."""

    def on_cycle_start(self, event: EventRecord) -> None:
        pass

    def on_llm_call(self, messages: list[ModelMessage]) -> None:
        pass

    def on_llm_response(self, response: LlmResponse | LlmError) -> None:
        pass

    def on_cycle_end(self) -> None:
        pass


class Orchestrator:
    """Coordinates the chat agent cycle.

    Args:
        producer:      Source of input events.
        agent:         pydantic-ai Agent configured with a dynamic system prompt.
        channel:       Output channel to deliver responses through.
        state:         Conversation history store.
        observability: Optional observability client. Pass None to disable tracing.
    """

    def __init__(
        self,
        producer: InputProducer,
        agent: Agent[str, str],
        channel: OutputChannel,
        state: ConversationState,
        observability: ObservabilityClient | None = None,
    ) -> None:
        self._producer = producer
        self._agent = agent
        self._channel = channel
        self._state = state
        self._obs = observability if observability is not None else NoOpObservability()

    def run(self) -> None:
        """Run the agent loop until a ShutdownSignal is received."""
        while True:
            event = self._producer.next_event()

            if isinstance(event, ShutdownSignal):
                break

            self._obs.on_cycle_start(event)

            result = self._call_llm(event.payload, event.source)

            if isinstance(result, LlmError):
                self._obs.on_llm_response(result)
                self._channel.deliver(ResponseRecord(reply_text=ERROR_REPLY))
                self._obs.on_cycle_end()
                continue

            response, new_messages = result
            self._obs.on_llm_call(new_messages)
            self._obs.on_llm_response(response)

            self._channel.deliver(ResponseRecord(reply_text=response.reply_text))
            self._state.extend(new_messages)

            self._obs.on_cycle_end()

    def _call_llm(
        self, user_prompt: str, source: str
    ) -> tuple[LlmResponse, list[ModelMessage]] | LlmError:
        """Call the pydantic-ai Agent and translate the result.

        Returns a (LlmResponse, new_messages) tuple on success, or LlmError on
        any failure. Never raises.
        """
        try:
            result = self._agent.run_sync(
                user_prompt,
                deps=source,
                message_history=self._state.history(),
            )
            usage = result.usage()
            response = LlmResponse(
                reply_text=result.output,
                usage=UsageRecord(
                    prompt_tokens=usage.input_tokens or 0,
                    completion_tokens=usage.output_tokens or 0,
                    reasoning_tokens=0,
                    total_tokens=usage.total_tokens or 0,
                ),
                model_id=str(self._agent.model),
            )
            return response, result.new_messages()
        except Exception as exc:
            return LlmError(reason=str(exc))
