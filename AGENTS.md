## Development Security and Safety

These rules protect the developer's secrets from leaking into an AI agent's context when the AI is acting as a developer working on this codebase. They govern how *you*, the AI agent, should behave when modifying or examining this code, not how the compiled software operates.

When you are acting as a developer AI (e.g., reading code, making changes, debugging):
- **NEVER** read any `.env` files or environment variables. Secrets are injected at runtime by `bws` when the software runs; you as the developer AI must never inspect them during development.
- **ALWAYS** respect the developer's privacy. Never examine, log, or echo secrets that may appear in code comments, configuration files, or documentation.
- **Only use `bws run` to execute commands** when testing your changes. The `bws` tool injects credentials; do not invoke it with other subcommands or attempt to obtain credentials through other means.

These rules do NOT apply to the software itself when it is running as an agent. The software may read environment variables (e.g., for Langfuse configuration or Google Drive credentials) as part of its normal operation when executed via `bws run`. This restriction is solely for AI agents acting in a developer role during code modification and review.