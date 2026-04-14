"""
Tests for Startup / Wiring.
"""

from unittest.mock import MagicMock, patch

import pytest

from tbc_agent.main import Config, create_agent
from tbc_agent.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# T6.1: Valid config produces a runnable Orchestrator
# ---------------------------------------------------------------------------

class TestValidConfig:
    def test_T6_1_valid_config_creates_orchestrator(self):
        """T6.1: create_agent returns a wired Orchestrator given valid config."""
        config = Config()
        agent = create_agent(config)

        assert isinstance(agent, Orchestrator)


# ---------------------------------------------------------------------------
# T6.2: Config from env
# ---------------------------------------------------------------------------

class TestConfigFromEnv:
    def test_model_defaults_to_xai_grok(self):
        """Config defaults to xai:grok-4-1-fast-reasoning."""
        config = Config()
        assert config.model == "xai:grok-4-1-fast-reasoning"

    def test_model_from_env(self, monkeypatch):
        """MODEL env var overrides the default."""
        monkeypatch.setenv("MODEL", "openai:gpt-4o")
        config = Config.from_env()
        assert config.model == "openai:gpt-4o"


# ---------------------------------------------------------------------------
# T6.3: Langfuse disabled — starts without any Langfuse connection
# ---------------------------------------------------------------------------

class TestLangfuseDisabled:
    def test_T6_3_langfuse_off_no_connection_attempted(self):
        """T6.3: When langfuse_enabled=False, no Langfuse client is created."""
        config = Config(langfuse_enabled=False)

        with patch("tbc_agent.main.Langfuse") as mock_langfuse:
            agent = create_agent(config)
            mock_langfuse.assert_not_called()

        assert isinstance(agent, Orchestrator)


# ---------------------------------------------------------------------------
# T6.4: Langfuse enabled but unreachable — warns and continues
# ---------------------------------------------------------------------------

class TestLangfuseUnreachable:
    @pytest.mark.filterwarnings("ignore: Langfuse observability")
    def test_T6_4_langfuse_unreachable_agent_still_starts(self):
        """T6.4: When Langfuse raises on init, create_agent warns and falls back to no-op."""
        config = Config(
            langfuse_enabled=True,
            langfuse_secret_key="sk-fake",
            langfuse_public_key="pk-fake",
        )

        with patch("tbc_agent.main.Langfuse", side_effect=Exception("connection refused")):
            agent = create_agent(config)

        assert isinstance(agent, Orchestrator)


# ---------------------------------------------------------------------------
# T6.5: Tool loading is called during wiring
# ---------------------------------------------------------------------------

class TestToolLoading:
    def test_T6_5_create_agent_calls_discover_tools(self):
        """T6.5: create_agent invokes discover_tools to load the tool registry."""
        config = Config()

        with patch("tbc_agent.main.discover_tools", return_value=[]) as mock_discover:
            create_agent(config)

        mock_discover.assert_called_once()
