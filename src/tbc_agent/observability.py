"""
Langfuse implementation of ObservabilityClient.

LangfuseObservability wraps the Langfuse Python SDK to produce one trace
per orchestrator cycle, with a span covering the LLM call.

If any Langfuse operation fails at runtime it is swallowed silently so that
observability failures never affect the agent's functional behaviour.
"""

from langfuse import Langfuse

from tbc_agent.input_events import EventRecord
from tbc_agent.llm_interface import LlmError, LlmResponse, MessageRecord
from tbc_agent.orchestrator import ObservabilityClient


class LangfuseObservability(ObservabilityClient):
    """Sends traces and spans to a Langfuse backend."""

    def __init__(self, client: Langfuse) -> None:
        self._client = client
        self._trace = None
        self._llm_span = None

    def on_cycle_start(self, event: EventRecord) -> None:
        try:
            self._trace = self._client.trace(
                name="chat-cycle",
                input={"event_id": event.event_id, "source": event.source, "payload": event.payload},
            )
        except Exception:
            self._trace = None

    def on_prompt_assembled(self, messages: list[MessageRecord]) -> None:
        if self._trace is None:
            return
        try:
            self._llm_span = self._trace.span(
                name="llm-call",
                input={"messages": [{"role": m.role, "content": m.text} for m in messages]},
            )
        except Exception:
            self._llm_span = None

    def on_llm_response(self, response: LlmResponse | LlmError) -> None:
        if self._llm_span is None:
            return
        try:
            if isinstance(response, LlmResponse):
                output = {
                    "reply": response.reply_text,
                    "model_id": response.model_id,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "reasoning_tokens": response.usage.reasoning_tokens,
                    },
                }
            else:
                output = {"error": response.reason}
            self._llm_span.end(output=output)
        except Exception:
            pass
        finally:
            self._llm_span = None

    def on_cycle_end(self) -> None:
        if self._trace is None:
            return
        try:
            self._trace.update(output={"status": "complete"})
        except Exception:
            pass
        finally:
            self._trace = None
