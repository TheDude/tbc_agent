"""
Prompt Registry — maps event sources to system prompts.

PromptRegistry     — looks up the system prompt for a given source string.
DEFAULT_SYSTEM_PROMPT — generic fallback used when no source-specific prompt exists.
DEFAULT_PROMPTS       — initial source→prompt mappings.
"""


DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, concise assistant. "
    "Answer clearly and directly."
)

DEFAULT_PROMPTS: dict[str, str] = {
    "cli": DEFAULT_SYSTEM_PROMPT,
}


class PromptRegistry:
    """Resolves the system prompt for a given event source.

    Args:
        prompts: Mapping of source names to system prompt strings.
        default: Fallback prompt returned when the source has no entry.
    """

    def __init__(
        self,
        prompts: dict[str, str] | None = None,
        default: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._prompts = dict(prompts) if prompts is not None else {}
        self._default = default

    def get_system_prompt(self, source: str) -> str:
        """Return the system prompt for *source*, falling back to the default."""
        return self._prompts.get(source, self._default)
