"""
Block 2: LLM Interface abstraction and xAI/Grok implementation.

MessageRecord  — a single message in the prompt (role + text).
UsageRecord    — token counts from the API response, including reasoning tokens.
LlmResponse    — successful response from the LLM.
LlmError       — returned when the call fails after retries (never raises).
LlmInterface   — abstract base.
GrokInterface  — concrete implementation targeting xAI's grok-4-1-fast-reasoning.

Retry policy: up to MAX_RETRIES attempts on 429 or 5xx, with exponential backoff.
Other 4xx errors are returned as LlmError immediately (no retry).
Timeouts are returned as LlmError immediately.
"""

import time
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel, computed_field

XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4-1-fast-reasoning"
MAX_RETRIES = 3
BASE_BACKOFF = 1.0  # seconds; doubles each attempt


class MessageRecord(BaseModel):
    """A single message in a prompt sequence."""

    role: str  # "system", "user", or "assistant"
    text: str


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


class LlmInterface(ABC):
    """Abstract base for all LLM implementations."""

    @abstractmethod
    def call(
        self,
        messages: list[MessageRecord],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LlmResponse | LlmError:
        """Send a message list to the LLM and return a response or error signal."""


class GrokInterface(LlmInterface):
    """Calls xAI's grok-4-1-fast-reasoning via the OpenAI-compatible chat completions API.

    Retries on 429 and 5xx with exponential backoff (up to MAX_RETRIES attempts).
    Returns LlmError on persistent failure, 4xx (non-429), or timeout.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def call(
        self,
        messages: list[MessageRecord],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LlmResponse | LlmError:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.text} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_error: str = "unknown error"

        for attempt in range(MAX_RETRIES):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(XAI_API_URL, json=payload, headers=headers)

                if response.status_code == 200:
                    return self._parse_response(response)

                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(BASE_BACKOFF * (2 ** attempt))
                    continue

                # Non-retryable 4xx
                return LlmError(reason=f"HTTP {response.status_code}: {response.text}")

            except httpx.TimeoutException as exc:
                return LlmError(reason=f"Request timed out: {exc}")

        return LlmError(reason=f"Failed after {MAX_RETRIES} attempts: {last_error}")

    @staticmethod
    def _parse_response(response: httpx.Response) -> LlmResponse:
        data = response.json()
        choice = data["choices"][0]
        reply_text = choice["message"]["content"]

        raw_usage = data.get("usage", {})
        details = raw_usage.get("completion_tokens_details", {})
        reasoning_tokens = details.get("reasoning_tokens", 0)

        usage = UsageRecord(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            reasoning_tokens=reasoning_tokens,
            total_tokens=raw_usage.get("total_tokens", 0),
        )

        return LlmResponse(
            reply_text=reply_text,
            usage=usage,
            model_id=data.get("model", DEFAULT_MODEL),
        )
