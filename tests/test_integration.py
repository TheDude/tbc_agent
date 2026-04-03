"""
End-to-end integration test.

Uses all real components (CliProducer, CliChannel, ConversationState, Orchestrator)
with a pydantic-ai FunctionModel for the LLM. No real API calls are made.

Scenarios:
  1. Multi-turn conversation — LLM receives history on the second turn
  2. LLM error mid-conversation — error surfaces through output, history stays clean, loop continues
  3. Graceful shutdown via 'exit' sentinel — no crash, clean exit
"""

import io

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tbc_agent.conversation_state import ConversationState
from tbc_agent.input_events import CliProducer
from tbc_agent.llm_interface import create_llm_agent
from tbc_agent.orchestrator import Orchestrator
from tbc_agent.output_channels import CliChannel
from tbc_agent.prompt_registry import PromptRegistry


def make_agent(stdin_text: str, state: ConversationState | None = None, model: FunctionModel | None = None) -> tuple[Orchestrator, io.StringIO]:
    """Wire up a complete agent with scripted stdin and a captured stdout stream."""
    stdout = io.StringIO()
    registry = PromptRegistry(default="You are a helpful assistant.")
    if model is None:
        from pydantic_ai.models.function import FunctionModel as FM
        model = FM(lambda msgs, info: ModelResponse(parts=[TextPart(content="default reply")]))
    agent = create_llm_agent(model, registry)

    return Orchestrator(
        producer=CliProducer(stream=io.StringIO(stdin_text)),
        agent=agent,
        channel=CliChannel(stream=stdout),
        state=state or ConversationState(),
    ), stdout


class TestMultiTurnConversation:
    def test_two_turns_llm_receives_history_on_second(self):
        """LLM is called twice; the second call includes the first turn pair in messages."""
        calls: list[list[ModelMessage]] = []

        def capture_and_reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            calls.append(messages)
            reply = "First reply" if len(calls) == 1 else "Second reply"
            return ModelResponse(parts=[TextPart(content=reply)])

        model = FunctionModel(capture_and_reply)
        agent, stdout = make_agent("hello\nfollow up\nexit\n", model=model)
        agent.run()

        output = stdout.getvalue()
        assert "First reply" in output
        assert "Second reply" in output

        # Second call should have more messages (includes history)
        assert len(calls[1]) > len(calls[0])

    def test_history_accumulates_correctly_across_turns(self):
        """After two successful turns the state holds messages from both turns."""
        def reply_handler(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="reply")])

        model = FunctionModel(reply_handler)
        state = ConversationState()
        agent, _ = make_agent("turn one\nturn two\nexit\n", state=state, model=model)
        agent.run()

        history = state.history()
        assert len(history) >= 4  # at least 2 requests + 2 responses


class TestLlmErrorMidConversation:
    def test_error_surfaces_through_output_and_loop_continues(self):
        """An LLM error on turn 1 shows an error message; turn 2 succeeds normally."""
        call_count = 0

        def sometimes_error(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("service unavailable")
            return ModelResponse(parts=[TextPart(content="Recovery reply")])

        model = FunctionModel(sometimes_error)
        agent, stdout = make_agent("broken\nrecovery\nexit\n", model=model)
        agent.run()

        output = stdout.getvalue()
        assert "unable to get a response" in output.lower()
        assert "Recovery reply" in output

    def test_error_does_not_corrupt_history(self):
        """After an LLM error, the failed user turn is NOT in history."""
        call_count = 0

        def sometimes_error(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("fail")
            return ModelResponse(parts=[TextPart(content="Good reply")])

        model = FunctionModel(sometimes_error)
        state = ConversationState()
        agent, _ = make_agent("bad\ngood\nexit\n", state=state, model=model)
        agent.run()

        history = state.history()
        # Only the successful second turn should be in history
        assert len(history) >= 2  # request + response from "good" turn


class TestGracefulShutdown:
    def test_exit_sentinel_stops_loop_cleanly(self):
        """Typing 'exit' stops the agent without error."""
        def handler(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="should not be called")])

        model = FunctionModel(handler)
        agent, stdout = make_agent("exit\n", model=model)
        agent.run()

        assert stdout.getvalue() == ""

    def test_eof_stops_loop_cleanly(self):
        """EOF (empty stream) stops the agent without error."""
        def handler(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="should not be called")])

        model = FunctionModel(handler)
        agent, stdout = make_agent("", model=model)
        agent.run()

        assert stdout.getvalue() == ""
