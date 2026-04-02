"""
Tests for Block 1: Input Event abstraction and CLI producer.
All tests follow T1.1–T1.11 from the design plan.
"""

import io
from datetime import datetime, timezone

import pytest

from tbc_agent.input_events import (
    EventRecord,
    ShutdownSignal,
    CliProducer,
)


# ---------------------------------------------------------------------------
# T1.1 – T1.5: Event record shape
# ---------------------------------------------------------------------------

class TestEventRecordShape:
    def test_T1_1_event_record_has_all_required_fields(self):
        """T1.1: A produced event record contains event_id, source, timestamp, payload."""
        record = EventRecord(
            event_id=1,
            source="cli",
            timestamp=datetime.now(tz=timezone.utc),
            payload="hello",
        )
        assert hasattr(record, "event_id")
        assert hasattr(record, "source")
        assert hasattr(record, "timestamp")
        assert hasattr(record, "payload")

    def test_T1_2_event_ids_are_monotonically_increasing(self):
        """T1.2: Successive events from the same CLI producer have increasing event IDs."""
        stream = io.StringIO("first\nsecond\nthird\n")
        producer = CliProducer(stream=stream)

        events = [producer.next_event() for _ in range(3)]

        ids = [e.event_id for e in events]
        assert ids == sorted(ids)
        assert len(set(ids)) == 3  # all unique

    def test_T1_3_timestamp_is_captured_at_event_time(self):
        """T1.3: The timestamp is close to when next_event() was called."""
        before = datetime.now(tz=timezone.utc)
        stream = io.StringIO("hello\n")
        producer = CliProducer(stream=stream)
        event = producer.next_event()
        after = datetime.now(tz=timezone.utc)

        assert isinstance(event, EventRecord)
        assert before <= event.timestamp <= after

    def test_T1_4_source_tag_is_cli(self):
        """T1.4: CLI producer sets source to 'cli'."""
        stream = io.StringIO("hello\n")
        producer = CliProducer(stream=stream)
        event = producer.next_event()

        assert isinstance(event, EventRecord)
        assert event.source == "cli"

    def test_T1_5_payload_contains_raw_user_text(self):
        """T1.5: The payload is the exact raw text from stdin."""
        stream = io.StringIO("tell me about the project\n")
        producer = CliProducer(stream=stream)
        event = producer.next_event()

        assert isinstance(event, EventRecord)
        assert event.payload == "tell me about the project"


# ---------------------------------------------------------------------------
# T1.6 – T1.11: CLI producer behavior
# ---------------------------------------------------------------------------

class TestCliProducerBehavior:
    def test_T1_6_non_empty_input_produces_one_event(self):
        """T1.6: A non-empty line produces exactly one EventRecord."""
        stream = io.StringIO("hello\n")
        producer = CliProducer(stream=stream)
        result = producer.next_event()

        assert isinstance(result, EventRecord)

    def test_T1_7_empty_line_is_skipped(self):
        """T1.7: An empty line is skipped; the producer waits for the next non-empty input."""
        # First two lines are empty, third is valid
        stream = io.StringIO("\n\nhello\n")
        producer = CliProducer(stream=stream)
        result = producer.next_event()

        assert isinstance(result, EventRecord)
        assert result.payload == "hello"

    def test_T1_8_whitespace_only_input_is_skipped(self):
        """T1.8: Whitespace-only input is treated as empty (no event produced)."""
        stream = io.StringIO("   \n\t\nhello\n")
        producer = CliProducer(stream=stream)
        result = producer.next_event()

        assert isinstance(result, EventRecord)
        assert result.payload == "hello"

    def test_T1_9_eof_returns_shutdown_signal(self):
        """T1.9: EOF (end of stream) returns a ShutdownSignal, not an EventRecord."""
        stream = io.StringIO("")  # immediately EOF
        producer = CliProducer(stream=stream)
        result = producer.next_event()

        assert isinstance(result, ShutdownSignal)

    def test_T1_10_exit_sentinel_returns_shutdown_signal(self):
        """T1.10: The 'exit' sentinel returns a ShutdownSignal."""
        stream = io.StringIO("exit\n")
        producer = CliProducer(stream=stream)
        result = producer.next_event()

        assert isinstance(result, ShutdownSignal)

    def test_T1_11_leading_trailing_whitespace_preserved_in_payload(self):
        """T1.11: Leading/trailing whitespace inside non-empty input is preserved."""
        stream = io.StringIO("  hello world  \n")
        producer = CliProducer(stream=stream)
        result = producer.next_event()

        assert isinstance(result, EventRecord)
        assert result.payload == "  hello world  "
