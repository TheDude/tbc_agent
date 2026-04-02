"""
Block 1: Input Event abstraction and CLI producer.

EventRecord   — normalized envelope for a single input event.
ShutdownSignal — sentinel returned when the input stream ends.
CliProducer   — concrete producer that reads from a text stream (stdin by default).
"""

import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TextIO

from pydantic import BaseModel


class EventRecord(BaseModel):
    """Normalized input event. All producers emit this shape."""

    event_id: int
    source: str
    timestamp: datetime
    payload: str


class ShutdownSignal:
    """Returned by a producer to signal that no more events will be produced."""


class InputProducer(ABC):
    """Abstract base for all input event producers."""

    @abstractmethod
    def next_event(self) -> EventRecord | ShutdownSignal:
        """Block until an event is available and return it.

        Returns ShutdownSignal when the source is exhausted or the user
        requests shutdown.
        """


class CliProducer(InputProducer):
    """Reads lines from a text stream (defaults to stdin) and emits EventRecords.

    Skips blank and whitespace-only lines. Returns ShutdownSignal on EOF or
    when the user types the 'exit' sentinel.
    """

    SHUTDOWN_SENTINEL = "exit"

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdin
        self._counter = 0

    def next_event(self) -> EventRecord | ShutdownSignal:
        while True:
            line = self._stream.readline()

            # EOF
            if line == "":
                return ShutdownSignal()

            # Strip only the newline at the end, preserving interior whitespace
            text = line.rstrip("\n").rstrip("\r")

            # Skip blank / whitespace-only lines
            if not text.strip():
                continue

            # Shutdown sentinel
            if text.strip() == self.SHUTDOWN_SENTINEL:
                return ShutdownSignal()

            self._counter += 1
            return EventRecord(
                event_id=self._counter,
                source="cli",
                timestamp=datetime.now(tz=timezone.utc),
                payload=text,
            )
