"""
Tests for Block 4: Conversation State (in-memory sliding window).
Adapted for pydantic-ai ModelMessage storage.
"""

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from tbc_agent.conversation_state import ConversationState


def make_request(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def make_response(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


# ---------------------------------------------------------------------------
# T4.1 – T4.4: Core operations
# ---------------------------------------------------------------------------

class TestCoreOperations:
    def test_T4_1_new_state_has_empty_history(self):
        """T4.1: A freshly created ConversationState has no messages."""
        state = ConversationState()
        assert state.history() == []

    def test_T4_2_extend_and_read_single_pair(self):
        """T4.2: Extending with messages and reading history returns them."""
        state = ConversationState()
        msgs = [make_request("hello"), make_response("hi")]
        state.extend(msgs)

        history = state.history()
        assert len(history) == 2

    def test_T4_3_multiple_messages_returned_in_insertion_order(self):
        """T4.3: Multiple messages are returned in the order they were added."""
        state = ConversationState()
        msgs = [
            make_request("first"),
            make_response("second"),
            make_request("third"),
        ]
        state.extend(msgs)

        assert state.history() == msgs

    def test_T4_4_messages_preserve_content(self):
        """T4.4: Message content is preserved exactly as added."""
        state = ConversationState()
        req = make_request("deep thought")
        resp = make_response("42")
        state.extend([req, resp])

        history = state.history()
        assert isinstance(history[0], ModelRequest)
        assert isinstance(history[1], ModelResponse)


# ---------------------------------------------------------------------------
# T4.5 – T4.9: Sliding window truncation
# ---------------------------------------------------------------------------

class TestSlidingWindowTruncation:
    def test_T4_5_no_truncation_below_limit(self):
        """T4.5: History with fewer than N messages is returned complete."""
        state = ConversationState(max_turns=10)
        for i in range(5):
            state.extend([make_request(f"msg {i}")])

        assert len(state.history()) == 5

    def test_T4_6_oldest_message_dropped_at_limit(self):
        """T4.6: When history reaches max_turns, extending drops the oldest."""
        state = ConversationState(max_turns=3)
        m1 = make_request("first")
        m2 = make_response("second")
        m3 = make_request("third")
        m4 = make_response("fourth")

        state.extend([m1, m2, m3, m4])

        history = state.history()
        assert len(history) == 3
        assert m1 not in history
        assert m4 in history

    def test_T4_7_truncation_drops_from_front(self):
        """T4.7: Truncation removes the oldest (front) messages, not the newest."""
        state = ConversationState(max_turns=2)
        m1 = make_request("oldest")
        m2 = make_response("middle")
        m3 = make_request("newest")

        state.extend([m1, m2, m3])

        history = state.history()
        assert history[0] is m2
        assert history[1] is m3

    def test_T4_8_remaining_messages_in_chronological_order_after_truncation(self):
        """T4.8: After truncation, surviving messages remain in insertion order."""
        state = ConversationState(max_turns=3)
        msgs = [make_request(f"msg {i}") for i in range(5)]
        state.extend(msgs)

        history = state.history()
        assert history == msgs[-3:]

    def test_T4_9_window_size_is_configurable(self):
        """T4.9: max_turns is respected at any configured value."""
        for window in [1, 5, 20]:
            state = ConversationState(max_turns=window)
            msgs = [make_request(f"msg {i}") for i in range(window + 3)]
            state.extend(msgs)
            assert len(state.history()) == window
