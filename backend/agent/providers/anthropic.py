"""Anthropic Claude implementation of the provider protocol.

Uses a manual message loop rather than the SDK's beta tool runner: the agent has
to emit a trace event between the model's turn and the tool execution, and has to
time each tool call itself, which the runner does not expose.
"""

import os

from anthropic import AsyncAnthropic

from .base import Conversation, ToolCall, ToolResult, ToolSpec, Turn

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "16000"))
# low | medium | high | xhigh | max — controls thinking depth and token spend.
EFFORT = os.environ.get("ANTHROPIC_EFFORT", "high")

# Claude has no embedding model. Relevance scoring stays on Gemini embeddings so
# that vectors written by a Claude run and a Gemini run remain comparable in the
# same pgvector column — mixing embedding families would silently corrupt every
# similarity comparison across runs.
_EMBED_DELEGATE = None


def _query_schema() -> dict:
    return {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query."}},
        "required": ["query"],
        "additionalProperties": False,
    }


def _to_tool_params(tools: list[ToolSpec]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": _query_schema(),
            "strict": True,
        }
        for t in tools
    ]


class AnthropicConversation:
    def __init__(
        self,
        client: AsyncAnthropic,
        model: str,
        system: str,
        tools: list[ToolSpec] | None,
    ):
        self._client = client
        self._model = model
        self._system = system
        self._tools = _to_tool_params(tools) if tools else None
        self._messages: list[dict] = []

    async def _create(self) -> Turn:
        kwargs = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": self._system,
            "messages": self._messages,
            # Adaptive thinking is on by default for Opus 5; asking for the summary
            # explicitly is what makes the reasoning visible in the trace, since the
            # default display is "omitted".
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": EFFORT},
        }
        if self._tools:
            kwargs["tools"] = self._tools

        response = await self._client.messages.create(**kwargs)

        # Echo the assistant turn back verbatim — thinking blocks included, which
        # the API requires when continuing the same conversation on the same model.
        self._messages.append({"role": "assistant", "content": response.content})

        text_parts, thinking_parts, calls = [], [], []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                thinking_parts.append(getattr(block, "thinking", "") or "")
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, args=dict(block.input or {})))

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            reason = getattr(details, "explanation", None) or "safety classifier declined"
            raise RuntimeError(f"Claude declined this request: {reason}")

        return Turn(
            text="".join(text_parts).strip(),
            calls=calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            thinking="\n".join(p for p in thinking_parts if p).strip(),
        )

    async def send(self, message: str) -> Turn:
        self._messages.append({"role": "user", "content": message})
        return await self._create()

    async def send_tool_results(self, results: list[ToolResult]) -> Turn:
        # All results for one assistant turn go back in a single user message —
        # splitting them teaches the model to stop calling tools in parallel.
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call.id,
                        "content": r.content,
                        **({"is_error": True} if r.is_error else {}),
                    }
                    for r in results
                ],
            }
        )
        return await self._create()


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = AsyncAnthropic()

    def start(self, system: str, tools: list[ToolSpec] | None = None) -> Conversation:
        return AnthropicConversation(self._client, self.model, system, tools)

    async def complete(self, system: str, prompt: str) -> Turn:
        conversation = AnthropicConversation(self._client, self.model, system, None)
        return await conversation.send(prompt)

    async def embed(self, texts: list[str], dim: int) -> list[list[float]]:
        global _EMBED_DELEGATE
        if _EMBED_DELEGATE is None:
            from .gemini import GeminiProvider

            _EMBED_DELEGATE = GeminiProvider()
        return await _EMBED_DELEGATE.embed(texts, dim)
