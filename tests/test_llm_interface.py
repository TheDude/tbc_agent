"""
Tests for Block 2: LLM Interface abstraction and xAI/Grok implementation.
All tests follow T2.1–T2.12 from the design plan.
No real API calls are made — all HTTP is mocked via respx.
"""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from tbc_agent.llm_interface import (
    GrokInterface,
    LlmError,
    LlmResponse,
    MessageRecord,
)

XAI_URL = "https://api.x.ai/v1/chat/completions"

MESSAGES = [
    MessageRecord(role="system", text="You are a helpful assistant."),
    MessageRecord(role="user", text="Hello"),
]


def make_success_response(
    reply: str = "Hi there!",
    model: str = "grok-4-1-fast-reasoning",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    reasoning_tokens: int = 0,
) -> dict:
    return {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "completion_tokens_details": {
                "reasoning_tokens": reasoning_tokens,
            },
        },
    }


# ---------------------------------------------------------------------------
# T2.1 – T2.3: Contract
# ---------------------------------------------------------------------------

class TestLlmInterfaceContract:
    @respx.mock
    def test_T2_1_accepts_message_list_returns_response(self):
        """T2.1: call() accepts a list of MessageRecords and returns LlmResponse or LlmError."""
        respx.post(XAI_URL).mock(
            return_value=httpx.Response(200, json=make_success_response())
        )
        iface = GrokInterface(api_key="test-key")
        result = iface.call(MESSAGES)

        assert isinstance(result, (LlmResponse, LlmError))

    @respx.mock
    def test_T2_2_response_record_has_required_fields(self):
        """T2.2: LlmResponse contains reply_text, usage, and model_id."""
        respx.post(XAI_URL).mock(
            return_value=httpx.Response(200, json=make_success_response())
        )
        iface = GrokInterface(api_key="test-key")
        result = iface.call(MESSAGES)

        assert isinstance(result, LlmResponse)
        assert hasattr(result, "reply_text")
        assert hasattr(result, "usage")
        assert hasattr(result, "model_id")

    @respx.mock
    def test_T2_3_model_parameters_forwarded(self):
        """T2.3: temperature and max_tokens appear in the outgoing request body."""
        route = respx.post(XAI_URL).mock(
            return_value=httpx.Response(200, json=make_success_response())
        )
        iface = GrokInterface(api_key="test-key")
        iface.call(MESSAGES, temperature=0.3, max_tokens=512)

        body = json.loads(route.calls[0].request.content)
        assert body["temperature"] == 0.3
        assert body["max_tokens"] == 512


# ---------------------------------------------------------------------------
# T2.4 – T2.6: Success path
# ---------------------------------------------------------------------------

class TestGrokSuccessPath:
    @respx.mock
    def test_T2_4_successful_request_returns_nonempty_reply(self):
        """T2.4: A well-formed request returns an LlmResponse with non-empty reply_text."""
        respx.post(XAI_URL).mock(
            return_value=httpx.Response(200, json=make_success_response(reply="Hello back!"))
        )
        iface = GrokInterface(api_key="test-key")
        result = iface.call(MESSAGES)

        assert isinstance(result, LlmResponse)
        assert result.reply_text == "Hello back!"

    @respx.mock
    def test_T2_5_usage_distinguishes_reasoning_and_visible_tokens(self):
        """T2.5: Usage reports both billed completion_tokens and reasoning_tokens separately."""
        respx.post(XAI_URL).mock(
            return_value=httpx.Response(
                200,
                json=make_success_response(
                    completion_tokens=100,
                    reasoning_tokens=80,
                ),
            )
        )
        iface = GrokInterface(api_key="test-key")
        result = iface.call(MESSAGES)

        assert isinstance(result, LlmResponse)
        assert result.usage.completion_tokens == 100
        assert result.usage.reasoning_tokens == 80
        assert result.usage.visible_completion_tokens == 20  # 100 - 80

    @respx.mock
    def test_T2_6_model_id_matches_serving_model(self):
        """T2.6: model_id in the response matches the model field from the API response."""
        respx.post(XAI_URL).mock(
            return_value=httpx.Response(
                200,
                json=make_success_response(model="grok-4-1-fast-reasoning"),
            )
        )
        iface = GrokInterface(api_key="test-key")
        result = iface.call(MESSAGES)

        assert isinstance(result, LlmResponse)
        assert result.model_id == "grok-4-1-fast-reasoning"


# ---------------------------------------------------------------------------
# T2.7 – T2.11: Retry behaviour
# ---------------------------------------------------------------------------

class TestGrokRetryBehavior:
    @respx.mock
    def test_T2_7_429_triggers_retry(self):
        """T2.7: A 429 response triggers a retry rather than an immediate error."""
        respx.post(XAI_URL).mock(
            side_effect=[
                httpx.Response(429, json={"error": "rate limited"}),
                httpx.Response(200, json=make_success_response()),
            ]
        )
        iface = GrokInterface(api_key="test-key")
        with patch("tbc_agent.llm_interface.time.sleep"):
            result = iface.call(MESSAGES)

        assert isinstance(result, LlmResponse)

    @respx.mock
    def test_T2_8_5xx_triggers_retry(self):
        """T2.8: A 5xx response triggers a retry."""
        respx.post(XAI_URL).mock(
            side_effect=[
                httpx.Response(503, json={"error": "service unavailable"}),
                httpx.Response(200, json=make_success_response()),
            ]
        )
        iface = GrokInterface(api_key="test-key")
        with patch("tbc_agent.llm_interface.time.sleep"):
            result = iface.call(MESSAGES)

        assert isinstance(result, LlmResponse)

    @respx.mock
    def test_T2_9_non_429_4xx_returns_error_immediately(self):
        """T2.9: A 4xx other than 429 returns LlmError immediately without retrying."""
        route = respx.post(XAI_URL).mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        iface = GrokInterface(api_key="bad-key")
        result = iface.call(MESSAGES)

        assert isinstance(result, LlmError)
        assert route.call_count == 1  # no retries

    @respx.mock
    def test_T2_10_retries_use_exponential_backoff(self):
        """T2.10: Sleep durations increase between retry attempts."""
        respx.post(XAI_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(429),
                httpx.Response(200, json=make_success_response()),
            ]
        )
        iface = GrokInterface(api_key="test-key")
        sleep_calls = []
        with patch("tbc_agent.llm_interface.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            iface.call(MESSAGES)

        assert len(sleep_calls) == 2
        assert sleep_calls[1] > sleep_calls[0]

    @respx.mock
    def test_T2_11_error_signal_after_max_retries(self):
        """T2.11: After 3 failed attempts, LlmError is returned (not an exception)."""
        respx.post(XAI_URL).mock(
            return_value=httpx.Response(503, json={"error": "down"})
        )
        iface = GrokInterface(api_key="test-key")
        with patch("tbc_agent.llm_interface.time.sleep"):
            result = iface.call(MESSAGES)

        assert isinstance(result, LlmError)


# ---------------------------------------------------------------------------
# T2.12: Timeout
# ---------------------------------------------------------------------------

class TestGrokTimeout:
    @respx.mock
    def test_T2_12_timeout_returns_error_signal(self):
        """T2.12: A request that times out returns LlmError, not an exception."""
        respx.post(XAI_URL).mock(side_effect=httpx.TimeoutException("timed out"))
        iface = GrokInterface(api_key="test-key")
        with patch("tbc_agent.llm_interface.time.sleep"):
            result = iface.call(MESSAGES)

        assert isinstance(result, LlmError)
