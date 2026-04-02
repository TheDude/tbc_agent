"""
Tests for Block 4: Conversation State (in-memory sliding window).
All tests follow T4.1–T4.10 from the design plan.
"""

from datetime import datetime, timezone

import pytest

from tbc_agent.conversation_state import ConversationState, TurnRecord


def make_turn(role: str, text: str) -> TurnRecord:
    return TurnRecord(role=role, text=text, timestamp=datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# T4.1 – T4.4: Core operations
# ---------------------------------------------------------------------------

class TestCoreOperations:
    def test_T4_1_new_state_has_empty_history(self):
        """T4.1: A freshly created ConversationState has no turns."""
        state = ConversationState()
        assert state.history() == []

    def test_T4_2_append_and_read_single_turn(self):
        """T4.2: Appending a turn and reading history returns that turn."""
        state = ConversationState()
        turn = make_turn("user", "hello")
        state.append(turn)

        history = state.history()
        assert len(history) == 1
        assert history[0] is turn

    def test_T4_3_multiple_turns_returned_in_insertion_order(self):
        """T4.3: Multiple turns are returned in the order they were appended."""
        state = ConversationState()
        turns = [
            make_turn("user", "first"),
            make_turn("assistant", "second"),
            make_turn("user", "third"),
        ]
        for t in turns:
            state.append(t)

        assert state.history() == turns

    def test_T4_4_turn_records_preserve_all_fields(self):
        """T4.4: Role, text, and timestamp are preserved exactly as appended."""
        state = ConversationState()
        ts = datetime.now(tz=timezone.utc)
        turn = TurnRecord(role="assistant", text="deep thought", timestamp=ts)
        state.append(turn)

        retrieved = state.history()[0]
        assert retrieved.role == "assistant"
        assert retrieved.text == "deep thought"
        assert retrieved.timestamp == ts


# ---------------------------------------------------------------------------
# T4.5 – T4.9: Sliding window truncation
# ---------------------------------------------------------------------------

class TestSlidingWindowTruncation:
    def test_T4_5_no_truncation_below_limit(self):
        """T4.5: History with fewer than N turns is returned complete."""
        state = ConversationState(max_turns=10)
        for i in range(5):
            state.append(make_turn("user", f"msg {i}"))

        assert len(state.history()) == 5

    def test_T4_6_oldest_turn_dropped_at_limit(self):
        """T4.6: When history reaches max_turns, appending drops the oldest."""
        state = ConversationState(max_turns=3)
        t1 = make_turn("user", "first")
        t2 = make_turn("assistant", "second")
        t3 = make_turn("user", "third")
        t4 = make_turn("assistant", "fourth")

        for t in [t1, t2, t3, t4]:
            state.append(t)

        history = state.history()
        assert len(history) == 3
        assert t1 not in history
        assert t4 in history

    def test_T4_7_truncation_drops_from_front(self):
        """T4.7: Truncation removes the oldest (front) turns, not the newest."""
        state = ConversationState(max_turns=2)
        t1 = make_turn("user", "oldest")
        t2 = make_turn("assistant", "middle")
        t3 = make_turn("user", "newest")

        for t in [t1, t2, t3]:
            state.append(t)

        history = state.history()
        assert history[0] is t2
        assert history[1] is t3

    def test_T4_8_remaining_turns_in_chronological_order_after_truncation(self):
        """T4.8: After truncation, surviving turns remain in insertion order."""
        state = ConversationState(max_turns=3)
        turns = [make_turn("user", f"msg {i}") for i in range(5)]
        for t in turns:
            state.append(t)

        history = state.history()
        assert history == turns[-3:]

    def test_T4_9_window_size_is_configurable(self):
        """T4.9: max_turns is respected at any configured value."""
        for window in [1, 5, 20]:
            state = ConversationState(max_turns=window)
            for i in range(window + 3):
                state.append(make_turn("user", f"msg {i}"))
            assert len(state.history()) == window


# ---------------------------------------------------------------------------
# T4.10: Boundary — system message excluded
# ---------------------------------------------------------------------------

class TestBoundary:
    def test_T4_10_system_role_turn_is_rejected(self):
        """T4.10: Appending a turn with role='system' raises ValueError."""
        state = ConversationState()
        with pytest.raises(ValueError, match="system"):
            state.append(make_turn("system", "you are a helpful assistant"))
