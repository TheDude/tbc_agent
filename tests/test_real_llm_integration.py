"""
Real LLM integration test using the default xai:grok model.

This test makes actual API calls to the xAI service and requires
the XAI_API_KEY environment variable to be set.
"""

import os
import io

import pytest

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, SystemPromptPart, TextPart, UserPromptPart

from tbc_agent.conversation_state import ConversationState
from tbc_agent.input_events import CliProducer
from tbc_agent.llm_interface import create_llm_agent, DEFAULT_MODEL
from tbc_agent.orchestrator import Orchestrator
from tbc_agent.output_channels import CliChannel
from tbc_agent.prompt_registry import PromptRegistry


def make_agent_with_real_model(stdin_text: str, state: ConversationState | None = None) -> tuple[Orchestrator, io.StringIO]:
    """Wire up a complete agent with scripted stdin and a captured stdout stream using the real model."""
    stdout = io.StringIO()
    registry = PromptRegistry(default="You are a helpful assistant. Be concise in your responses.")
    
    # Use the real model from DEFAULT_MODEL
    agent = create_llm_agent(DEFAULT_MODEL, registry)
    
    return Orchestrator(
        producer=CliProducer(stream=io.StringIO(stdin_text)),
        agent=agent,
        channel=CliChannel(stream=stdout),
        state=state or ConversationState(),
    ), stdout


@pytest.mark.skipif(
    not os.environ.get("XAI_API_KEY"),
    reason="XAI_API_KEY environment variable not set - skipping real LLM integration test"
)
@pytest.mark.integration
class TestRealLlmIntegration:
    """Integration tests with the real xAI Grok model."""
    
    def test_simple_query_real_llm(self):
        breakpoint()
        """Test that the agent can get a response from the real LLM."""
        agent, stdout = make_agent_with_real_model("Say 'hello' in exactly one word.\nexit\n")
        agent.run()
        
        output = stdout.getvalue().strip()
        # Should contain a response (not empty)
        assert output != "", f"Expected non-empty output, got: '{output}'"
        # Should contain something like "hello" (case insensitive)
        assert "hello" in output.lower(), f"Expected 'hello' in response, got: '{output}'"
    
    def test_conversation_history_preserved_real_llm(self):
        """Test that conversation history is preserved across turns with real LLM."""
        state = ConversationState()
        agent, stdout = make_agent_with_real_model(
            "My name is Alice.\n"
            "What is my name?\n"
            "exit\n",
            state=state
        )
        agent.run()
        
        output = stdout.getvalue().strip()
        # Should remember the name from the first turn
        assert "Alice" in output, f"Expected 'Alice' in response when asked for name, got: '{output}'"
        
        # Check that history was updated
        history = state.history()
        # Should have at least 2 exchanges (request+response) * 2 turns = 4 messages
        assert len(history) >= 4, f"Expected at least 4 messages in history, got {len(history)}"