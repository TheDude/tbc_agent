"""
Block 2: LLM Interface — Agent factory and response types.

UsageRecord    — token counts from the API response.
LlmResponse    — successful response from the LLM.
LlmError       — returned when the call fails (never raises).
create_llm_agent — builds a pydantic-ai Agent wired to a PromptRegistry.
"""

from collections.abc import Sequence

from pydantic import BaseModel, computed_field
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.models import Model

from tbc_agent.prompt_registry import PromptRegistry

DEFAULT_MODEL = "xai:grok-4-1-fast-reasoning"


class UsageRecord(BaseModel):
    """Token usage from an API response.

    completion_tokens includes reasoning_tokens (both are billed).
    visible_completion_tokens is the portion that appears in the reply text.
    """

    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    total_tokens: int

    @computed_field
    @property
    def visible_completion_tokens(self) -> int:
        return self.completion_tokens - self.reasoning_tokens


class LlmResponse(BaseModel):
    """Successful response from the LLM."""

    reply_text: str
    usage: UsageRecord
    model_id: str


class LlmError:
    """Returned when the LLM call fails. Never raises — the caller inspects this."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __repr__(self) -> str:
        return f"LlmError(reason={self.reason!r})"


def create_llm_agent(
    model: str | Model,
    registry: PromptRegistry,
    tools: Sequence[Tool] = (),
) -> Agent[str, str]:
    """Build a pydantic-ai Agent with a dynamic system prompt driven by the registry.

    The Agent's deps type is ``str`` (the event source). At call time, pass
    ``deps=event.source`` so the dynamic system prompt resolves to the
    source-specific prompt from the registry.

    Args:
        model:    pydantic-ai model string (e.g. ``"xai:grok-4-1-fast-reasoning"``)
                  or a Model instance (e.g. ``FunctionModel`` for testing).
        registry: Prompt registry mapping event sources to system prompts.
        tools:    Tool instances to register on the agent. Defaults to empty.
    """
    agent: Agent[str, str] = Agent(
        model, deps_type=str, output_type=str, defer_model_check=True, tools=tools
    )

    @agent.system_prompt
    def _resolve_system_prompt(ctx: RunContext[str]) -> str:
        return registry.get_system_prompt(ctx.deps)

    return agent
