"""Provider-neutral shapes for a tool-using conversation.

The orchestrator used to talk to `google.genai` directly, which made the model
vendor a structural property of the agent rather than a choice. Everything the
agent needs from a model is here: send a message, get back some text and zero or
more tool calls, send the tool results back.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ToolSpec:
    """A tool the model may call. Every tool in this project takes one string
    argument, `query`, so the schema is fixed rather than parameterized."""

    name: str
    description: str


@dataclass
class ToolCall:
    id: str  # provider's own call id; Anthropic requires it echoed back verbatim
    name: str
    args: dict


@dataclass
class ToolResult:
    call: ToolCall
    content: str
    is_error: bool = False


@dataclass
class Turn:
    """One model response."""

    text: str
    calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    # A summary of the model's reasoning, when the provider exposes one (Anthropic
    # extended thinking with display="summarized"). Gemini leaves this empty and the
    # trace falls back to whatever prose the model wrote in `text`.
    thinking: str = ""


@runtime_checkable
class Conversation(Protocol):
    """A stateful exchange with one model. Implementations keep whatever history
    representation their SDK wants."""

    async def send(self, message: str) -> Turn: ...

    async def send_tool_results(self, results: list[ToolResult]) -> Turn: ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def start(self, system: str, tools: list[ToolSpec] | None = None) -> Conversation: ...

    async def complete(self, system: str, prompt: str) -> Turn:
        """One-shot, no tools — used by the fleet's Planner, Analyst and
        Strategist, which reason over what the Researchers already gathered."""
        ...

    async def embed(self, texts: list[str], dim: int) -> list[list[float]]:
        """Batched embeddings. Providers without an embedding model of their own
        may delegate; the vectors have to stay comparable across a run."""
        ...
