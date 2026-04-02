"""
Block 4: Conversation State (in-memory sliding window).

TurnRecord         — a single conversation turn (role, text, timestamp).
ConversationState  — ordered history of turns with a configurable max-size window.

History is in-memory only and cleared on each process start.
The system message is not stored here — it is configuration owned by the orchestrator.
"""

from collections import deque
from datetime import datetime

from pydantic import BaseModel

_ALLOWED_ROLES = {"user", "assistant"}


class TurnRecord(BaseModel):
    """A single turn in the conversation."""

    role: str
    text: str
    timestamp: datetime


class ConversationState:
    """Maintains an ordered, bounded history of conversation turns.

    Args:
        max_turns: Maximum number of turns to retain. Oldest turns are dropped
                   when this limit is exceeded. Defaults to 40.
    """

    def __init__(self, max_turns: int = 40) -> None:
        self._max_turns = max_turns
        self._turns: deque[TurnRecord] = deque(maxlen=max_turns)

    def append(self, turn: TurnRecord) -> None:
        """Add a turn to history.

        Raises:
            ValueError: If the turn's role is 'system'. The system message is
                        orchestrator configuration, not conversation history.
        """
        if turn.role == "system":
            raise ValueError(
                "Cannot store a 'system' role turn in conversation history. "
                "The system message is orchestrator configuration."
            )
        if turn.role not in _ALLOWED_ROLES:
            raise ValueError(
                f"Unknown role '{turn.role}'. Allowed roles: {sorted(_ALLOWED_ROLES)}"
            )
        self._turns.append(turn)

    def history(self) -> list[TurnRecord]:
        """Return a snapshot of the current history in chronological order."""
        return list(self._turns)
