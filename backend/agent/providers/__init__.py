"""Model providers. `get_provider("anthropic"|"gemini")` is the only entry point
the rest of the agent should use."""

import os

from .base import Conversation, LLMProvider, ToolCall, ToolResult, ToolSpec, Turn

DEFAULT_PROVIDER = os.environ.get("AGENT_PROVIDER", "gemini")

__all__ = [
    "Conversation",
    "LLMProvider",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Turn",
    "get_provider",
    "available_providers",
    "DEFAULT_PROVIDER",
]


def available_providers() -> list[str]:
    """Which providers this deployment actually has credentials for — the frontend
    uses this so it can't offer a provider that will fail on the first call."""
    found = []
    if os.environ.get("GEMINI_API_KEY"):
        found.append("gemini")
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        found.append("anthropic")
    return found


def get_provider(name: str | None = None, model: str | None = None) -> LLMProvider:
    name = (name or DEFAULT_PROVIDER).lower()
    if name == "anthropic":
        from .anthropic import AnthropicProvider

        return AnthropicProvider(model)
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(model)
    raise ValueError(f"unknown provider {name!r} (expected 'anthropic' or 'gemini')")
