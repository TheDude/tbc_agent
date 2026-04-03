"""
Tests for Block 2: LLM Interface — Agent factory and response types.

Tests verify the create_llm_agent factory, UsageRecord, LlmResponse, and LlmError.
"""

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, SystemPromptPart, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tbc_agent.llm_interface import (
    LlmError,
    LlmResponse,
    UsageRecord,
    create_llm_agent,
)
from tbc_agent.prompt_registry import PromptRegistry


# ---------------------------------------------------------------------------
# UsageRecord
# ---------------------------------------------------------------------------

class TestUsageRecord:
    def test_visible_completion_tokens_computed(self):
        """visible_completion_tokens = completion_tokens - reasoning_tokens."""
        usage = UsageRecord(
            prompt_tokens=10,
            completion_tokens=100,
            reasoning_tokens=80,
            total_tokens=110,
        )
        assert usage.visible_completion_tokens == 20

    def test_visible_completion_tokens_zero_reasoning(self):
        """When reasoning_tokens is 0, visible equals completion."""
        usage = UsageRecord(
            prompt_tokens=10,
            completion_tokens=50,
            reasoning_tokens=0,
            total_tokens=60,
        )
        assert usage.visible_completion_tokens == 50


# ---------------------------------------------------------------------------
# LlmResponse / LlmError
# ---------------------------------------------------------------------------

class TestLlmResponse:
    def test_response_has_required_fields(self):
        usage = UsageRecord(prompt_tokens=5, completion_tokens=5, reasoning_tokens=0, total_tokens=10)
        resp = LlmResponse(reply_text="hello", usage=usage, model_id="test-model")
        assert resp.reply_text == "hello"
        assert resp.model_id == "test-model"


class TestLlmError:
    def test_error_has_reason(self):
        err = LlmError(reason="something broke")
        assert err.reason == "something broke"

    def test_error_repr(self):
        err = LlmError(reason="timeout")
        assert "timeout" in repr(err)


# ---------------------------------------------------------------------------
# create_llm_agent factory
# ---------------------------------------------------------------------------

class TestCreateLlmAgent:
    def test_creates_agent_instance(self):
        """Factory returns a pydantic-ai Agent."""
        registry = PromptRegistry(default="test prompt")
        model = FunctionModel(lambda msgs, info: ModelResponse(parts=[TextPart(content="ok")]))
        agent = create_llm_agent(model, registry)
        assert isinstance(agent, Agent)

    def test_dynamic_system_prompt_resolves_per_source(self):
        """The Agent's system prompt resolves via the registry for different sources."""
        captured_messages: list[list[ModelMessage]] = []

        def capture(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            captured_messages.append(messages)
            return ModelResponse(parts=[TextPart(content="ok")])

        registry = PromptRegistry(
            prompts={"cli": "CLI prompt", "webhook": "Webhook prompt"},
            default="default",
        )
        model = FunctionModel(capture)
        agent = create_llm_agent(model, registry)

        # Call with "webhook" source as deps
        agent.run_sync("hello", deps="webhook")

        messages = captured_messages[0]
        req = messages[0]
        assert isinstance(req, ModelRequest)
        system_parts = [p for p in req.parts if isinstance(p, SystemPromptPart)]
        assert any(p.content == "Webhook prompt" for p in system_parts)

    def test_tools_registered_on_agent(self):
        """Tools passed to create_llm_agent are available to the agent."""
        from pydantic_ai import Tool

        tool_calls: list[str] = []

        def my_test_tool() -> str:
            """A test tool."""
            tool_calls.append("called")
            return "tool_result"

        tool_info: list[AgentInfo] = []

        def model_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            tool_info.append(info)
            return ModelResponse(parts=[TextPart(content="done")])

        registry = PromptRegistry(default="test")
        model = FunctionModel(model_func)
        agent = create_llm_agent(model, registry, tools=[Tool(my_test_tool)])
        agent.run_sync("hello", deps="cli")

        assert any(t.name == "my_test_tool" for t in tool_info[0].function_tools)
