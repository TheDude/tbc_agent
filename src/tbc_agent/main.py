"""
Startup / Wiring — entrypoint for the chat agent.

Config        — reads and validates configuration from environment variables.
create_agent  — instantiates all concrete blocks and wires them into an Orchestrator.
main          — validates config, builds the agent, and starts the run loop.

Environment variables:
    MODEL                (optional) pydantic-ai model string; default xai:grok-4-1-fast-reasoning
    LANGFUSE_ENABLED     (optional) "true" to enable observability; default off
    LANGFUSE_SECRET_KEY  (optional) Langfuse secret key
    LANGFUSE_PUBLIC_KEY  (optional) Langfuse public key
    LANGFUSE_HOST        (optional) Langfuse host; defaults to cloud
    SYSTEM_MESSAGE       (optional) Override the default system prompt fallback
    MAX_TURNS            (optional) Conversation history window size; default 40
"""

import os
import warnings
from dataclasses import dataclass

from langfuse import Langfuse

from tbc_agent.conversation_state import ConversationState
from tbc_agent.input_events import CliProducer, InputProducer
from tbc_agent.llm_interface import DEFAULT_MODEL, create_llm_agent
from tbc_agent.observability import LangfuseObservability
from tbc_agent.orchestrator import NoOpObservability, ObservabilityClient, Orchestrator
from tbc_agent.output_channels import CliChannel, OutputChannel
from tbc_agent.prompt_registry import DEFAULT_PROMPTS, DEFAULT_SYSTEM_PROMPT, PromptRegistry
from tbc_agent.tool_loader import discover_tools

DEFAULT_MAX_TURNS = 40


@dataclass
class Config:
    """Validated agent configuration."""

    model: str = DEFAULT_MODEL
    langfuse_enabled: bool = False
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    default_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_turns: int = DEFAULT_MAX_TURNS

    @classmethod
    def from_env(cls) -> "Config":
        """Build Config from environment variables."""
        langfuse_enabled = os.environ.get("LANGFUSE_ENABLED", "").lower() == "true"

        return cls(
            model=os.environ.get("MODEL", DEFAULT_MODEL),
            langfuse_enabled=langfuse_enabled,
            langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
            langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
            langfuse_host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            default_system_prompt=os.environ.get("SYSTEM_MESSAGE", DEFAULT_SYSTEM_PROMPT),
            max_turns=int(os.environ.get("MAX_TURNS", str(DEFAULT_MAX_TURNS))),
        )


def _create_observability(config: Config) -> ObservabilityClient | None:
    """Build observability client, falling back to None on failure."""
    if not config.langfuse_enabled:
        return None

    try:
        client = Langfuse(
            secret_key=config.langfuse_secret_key,
            public_key=config.langfuse_public_key,
            host=config.langfuse_host,
        )
        return LangfuseObservability(client)
    except Exception as exc:
        warnings.warn(
            f"Langfuse observability could not be initialised ({exc}). "
            "Continuing without tracing.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None


def create_agent(
    config: Config,
    *,
    producer_override: InputProducer | None = None,
    channel_override: OutputChannel | None = None,
) -> Orchestrator:
    """Instantiate and wire all concrete blocks into an Orchestrator.

    Override parameters allow test doubles to be injected without modifying
    the agent's internal logic.
    """
    producer = producer_override or CliProducer()
    channel = channel_override or CliChannel()
    state = ConversationState(max_turns=config.max_turns)
    observability = _create_observability(config)
    registry = PromptRegistry(
        prompts=DEFAULT_PROMPTS,
        default=config.default_system_prompt,
    )
    tools = discover_tools()
    agent = create_llm_agent(config.model, registry, tools=tools)

    return Orchestrator(
        producer=producer,
        agent=agent,
        channel=channel,
        state=state,
        observability=observability,
    )


def main() -> None:
    """Entrypoint: load config, build the agent, run the loop."""
    local_provider = OpenAIProvider(base_url="http://100.122.51.110:11434/v1", api_key="ollama on foundation")
    local_model = OpenAIChatModel("qwen3.5-4b-12k", provider=local_provider)

    config = Config.from_env()
    config.model = local_model
    
    agent = create_agent(config)
    print("Chat agent ready. Type 'exit' or press Ctrl-D to quit.\n")
    agent.run()


if __name__ == "__main__":
    main()
