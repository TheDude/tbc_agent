"""
Tests for Phase 7: Startup / Wiring.
All tests follow T6.1–T6.5 from the design plan.
"""

from unittest.mock import MagicMock, patch

import pytest

from tbc_agent.llm_interface import LlmInterface
from tbc_agent.main import Config, create_agent
from tbc_agent.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# T6.1: Valid config produces a runnable Orchestrator
# ---------------------------------------------------------------------------

class TestValidConfig:
    def test_T6_1_valid_config_creates_orchestrator(self):
        """T6.1: create_agent returns a wired Orchestrator given valid config."""
        config = Config(xai_api_key="test-key")
        agent = create_agent(config)

        assert isinstance(agent, Orchestrator)


# ---------------------------------------------------------------------------
# T6.2: Missing API key fails fast
# ---------------------------------------------------------------------------

class TestMissingApiKey:
    def test_T6_2_missing_api_key_raises_before_loop(self, monkeypatch):
        """T6.2: Config.from_env() raises ValueError when XAI_API_KEY is absent."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="XAI_API_KEY"):
            Config.from_env()

    def test_T6_2b_empty_api_key_also_raises(self, monkeypatch):
        """T6.2: An empty XAI_API_KEY is treated the same as absent."""
        monkeypatch.setenv("XAI_API_KEY", "")

        with pytest.raises(ValueError, match="XAI_API_KEY"):
            Config.from_env()


# ---------------------------------------------------------------------------
# T6.3: Langfuse disabled — starts without any Langfuse connection
# ---------------------------------------------------------------------------

class TestLangfuseDisabled:
    def test_T6_3_langfuse_off_no_connection_attempted(self):
        """T6.3: When langfuse_enabled=False, no Langfuse client is created."""
        config = Config(xai_api_key="test-key", langfuse_enabled=False)

        # If Langfuse were imported and instantiated, this mock would catch it
        with patch("tbc_agent.main.Langfuse") as mock_langfuse:
            agent = create_agent(config)
            mock_langfuse.assert_not_called()

        assert isinstance(agent, Orchestrator)


# ---------------------------------------------------------------------------
# T6.4: Langfuse enabled but unreachable — warns and continues
# ---------------------------------------------------------------------------

class TestLangfuseUnreachable:
    def test_T6_4_langfuse_unreachable_agent_still_starts(self):
        """T6.4: When Langfuse raises on init, create_agent warns and falls back to no-op."""
        config = Config(
            xai_api_key="test-key",
            langfuse_enabled=True,
            langfuse_secret_key="sk-fake",
            langfuse_public_key="pk-fake",
        )

        with patch("tbc_agent.main.Langfuse", side_effect=Exception("connection refused")):
            agent = create_agent(config)  # must not raise

        assert isinstance(agent, Orchestrator)

    def test_T6_4b_langfuse_unreachable_observability_is_noop(self):
        """T6.4: After Langfuse failure, observability is silently disabled (no tracing errors)."""
        from tbc_agent.input_events import ShutdownSignal
        from tbc_agent.output_channels import ResponseRecord
        from tbc_agent.llm_interface import LlmResponse, UsageRecord

        config = Config(
            xai_api_key="test-key",
            langfuse_enabled=True,
            langfuse_secret_key="sk-fake",
            langfuse_public_key="pk-fake",
        )

        fake_llm = MagicMock(spec=LlmInterface)
        fake_llm.call.return_value = LlmResponse(
            reply_text="hello",
            usage=UsageRecord(
                prompt_tokens=5, completion_tokens=5,
                reasoning_tokens=0, total_tokens=10,
            ),
            model_id="grok-4-1-fast-reasoning",
        )

        with patch("tbc_agent.main.Langfuse", side_effect=Exception("connection refused")):
            agent = create_agent(config, llm_override=fake_llm)

        # Running a single cycle must not raise even with broken observability
        from io import StringIO
        from tbc_agent.input_events import CliProducer
        from tbc_agent.output_channels import CliChannel
        from tbc_agent.conversation_state import ConversationState
        from tbc_agent.orchestrator import Orchestrator

        agent2 = Orchestrator(
            producer=CliProducer(stream=StringIO("hi\nexit\n")),
            llm=fake_llm,
            channel=CliChannel(stream=StringIO()),
            state=ConversationState(),
            system_message="You are a helpful assistant.",
            observability=agent._obs,
        )
        agent2.run()  # must not raise


# ---------------------------------------------------------------------------
# T6.5: Test doubles can be substituted via overrides
# ---------------------------------------------------------------------------

class TestSubstitution:
    def test_T6_5_llm_override_is_used(self):
        """T6.5: An llm_override passed to create_agent is wired into the Orchestrator."""
        config = Config(xai_api_key="test-key")
        mock_llm = MagicMock(spec=LlmInterface)

        agent = create_agent(config, llm_override=mock_llm)

        assert agent._llm is mock_llm
