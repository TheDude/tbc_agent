"""
End-to-end integration test.

Uses all real components (CliProducer, CliChannel, ConversationState, Orchestrator)
with scripted stdin/stdout streams and respx-mocked HTTP for the LLM.
No real API calls are made.

Scenarios:
  1. Multi-turn conversation — LLM receives history on the second turn
  2. LLM error mid-conversation — error surfaces through output, history stays clean, loop continues
  3. Graceful shutdown via 'exit' sentinel — no crash, clean exit
"""

import io
import json

import httpx
import pytest
import respx

from tbc_agent.conversation_state import ConversationState
from tbc_agent.input_events import CliProducer
from tbc_agent.llm_interface import GrokInterface
from tbc_agent.orchestrator import Orchestrator
from tbc_agent.output_channels import CliChannel

XAI_URL = "https://api.x.ai/v1/chat/completions"


def make_api_response(reply: str, model: str = "grok-4-1-fast-reasoning") -> dict:
    return {
        "id": "cmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }


def make_agent(stdin_text: str, state: ConversationState | None = None) -> tuple[Orchestrator, io.StringIO]:
    """Wire up a complete agent with scripted stdin and a captured stdout stream."""
    stdout = io.StringIO()
    return Orchestrator(
        producer=CliProducer(stream=io.StringIO(stdin_text)),
        llm=GrokInterface(api_key="test-key"),
        channel=CliChannel(stream=stdout),
        state=state or ConversationState(),
        system_message="You are a helpful assistant.",
    ), stdout


class TestMultiTurnConversation:
    @respx.mock
    def test_two_turns_llm_receives_history_on_second(self):
        """LLM is called twice; the second call includes the first turn pair in messages."""
        calls: list[dict] = []

        def capture_and_reply(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            reply = "First reply" if len(calls) == 1 else "Second reply"
            return httpx.Response(200, json=make_api_response(reply))

        respx.post(XAI_URL).mock(side_effect=capture_and_reply)

        agent, stdout = make_agent("hello\nfollow up\nexit\n")
        agent.run()

        output = stdout.getvalue()
        assert "First reply" in output
        assert "Second reply" in output

        # Second call should carry the first turn pair in history
        second_messages = calls[1]["messages"]
        roles = [m["role"] for m in second_messages]
        # [system, user(hello), assistant(First reply), user(follow up)]
        assert roles == ["system", "user", "assistant", "user"]
        assert second_messages[1]["content"] == "hello"
        assert second_messages[2]["content"] == "First reply"
        assert second_messages[3]["content"] == "follow up"

    @respx.mock
    def test_history_accumulates_correctly_across_turns(self):
        """After two successful turns the state holds exactly four turns."""
        respx.post(XAI_URL).mock(
            side_effect=[
                httpx.Response(200, json=make_api_response("Reply A")),
                httpx.Response(200, json=make_api_response("Reply B")),
            ]
        )
        state = ConversationState()
        agent, _ = make_agent("turn one\nturn two\nexit\n", state=state)
        agent.run()

        history = state.history()
        assert len(history) == 4
        assert history[0].role == "user" and history[0].text == "turn one"
        assert history[1].role == "assistant" and history[1].text == "Reply A"
        assert history[2].role == "user" and history[2].text == "turn two"
        assert history[3].role == "assistant" and history[3].text == "Reply B"


class TestLlmErrorMidConversation:
    @respx.mock
    def test_error_surfaces_through_output_and_loop_continues(self):
        """An LLM error on turn 1 shows an error message; turn 2 succeeds normally."""
        respx.post(XAI_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(503),  # exhaust retries on first user message
                httpx.Response(200, json=make_api_response("Recovery reply")),
            ]
        )
        from unittest.mock import patch
        agent, stdout = make_agent("broken\nrecovery\nexit\n")
        with patch("tbc_agent.llm_interface.time.sleep"):
            agent.run()

        output = stdout.getvalue()
        assert "unable to get a response" in output.lower()
        assert "Recovery reply" in output

    @respx.mock
    def test_error_does_not_corrupt_history(self):
        """After an LLM error, the failed user turn is NOT in history."""
        respx.post(XAI_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json=make_api_response("Good reply")),
            ]
        )
        state = ConversationState()
        from unittest.mock import patch
        agent, _ = make_agent("bad\ngood\nexit\n", state=state)
        with patch("tbc_agent.llm_interface.time.sleep"):
            agent.run()

        history = state.history()
        # Only the successful second turn should be in history
        assert len(history) == 2
        assert history[0].text == "good"
        assert history[1].text == "Good reply"


class TestGracefulShutdown:
    @respx.mock
    def test_exit_sentinel_stops_loop_cleanly(self):
        """Typing 'exit' stops the agent without error."""
        agent, stdout = make_agent("exit\n")
        agent.run()  # must not raise or block

        assert stdout.getvalue() == ""  # nothing delivered

    @respx.mock
    def test_eof_stops_loop_cleanly(self):
        """EOF (empty stream) stops the agent without error."""
        agent, stdout = make_agent("")
        agent.run()  # must not raise or block

        assert stdout.getvalue() == ""
