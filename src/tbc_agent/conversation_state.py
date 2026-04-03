"""
Block 4: Conversation State (in-memory sliding window).

ConversationState  — ordered history of ModelMessage objects with a configurable
                     max-size window.

History is in-memory only and cleared on each process start.
"""

from collections import deque
from collections.abc import Sequence

from pydantic_ai.messages import ModelMessage


class ConversationState:
    """Maintains an ordered, bounded history of conversation messages.

    Args:
        max_turns: Maximum number of messages to retain. Oldest messages are
                   dropped when this limit is exceeded. Defaults to 40.
    """

    def __init__(self, max_turns: int = 40) -> None:
        self._max_turns = max_turns
        self._messages: deque[ModelMessage] = deque(maxlen=max_turns)

    def extend(self, messages: Sequence[ModelMessage]) -> None:
        """Add messages to history."""
        for msg in messages:
            self._messages.append(msg)

    def history(self) -> list[ModelMessage]:
        """Return a snapshot of the current history in chronological order."""
        return list(self._messages)
