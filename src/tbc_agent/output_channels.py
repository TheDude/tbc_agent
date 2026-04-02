"""
Block 3: Output Channel abstraction and CLI implementation.

ResponseRecord  — the data delivered to a channel (reply text + optional metadata).
DeliveryOutcome — the result of a delivery attempt.
OutputChannel   — abstract base for all output channels.
CliChannel      — concrete implementation that writes to a text stream (stdout by default).
"""

import sys
from abc import ABC, abstractmethod
from typing import TextIO

from pydantic import BaseModel


class ResponseRecord(BaseModel):
    """Data to be delivered to the user via an output channel."""

    reply_text: str


class DeliveryOutcome(BaseModel):
    """Result of a delivery attempt."""

    success: bool
    error_message: str | None = None


class OutputChannel(ABC):
    """Abstract base for all output channels."""

    @abstractmethod
    def deliver(self, record: ResponseRecord) -> DeliveryOutcome:
        """Deliver a response record to the target medium.

        Returns a DeliveryOutcome indicating success or failure.
        """


class CliChannel(OutputChannel):
    """Writes reply text to a text stream (defaults to stdout)."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def deliver(self, record: ResponseRecord) -> DeliveryOutcome:
        print(record.reply_text, file=self._stream)
        return DeliveryOutcome(success=True)
