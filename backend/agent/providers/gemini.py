"""Google Gemini implementation of the provider protocol."""

import os
import uuid

from google import genai
from google.genai import types

from .base import Conversation, ToolCall, ToolResult, ToolSpec, Turn

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")

_QUERY_PARAM = {
    "type": "OBJECT",
    "properties": {"query": {"type": "STRING"}},
    "required": ["query"],
}


def _usage(resp) -> tuple[int, int]:
    meta = getattr(resp, "usage_metadata", None)
    if not meta:
        return 0, 0
    return getattr(meta, "prompt_token_count", 0) or 0, getattr(meta, "candidates_token_count", 0) or 0


class GeminiConversation:
    def __init__(self, client: genai.Client, model: str, system: str, tools: list[ToolSpec] | None):
        config = types.GenerateContentConfig(system_instruction=system)
        if tools:
            config.tools = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name, description=t.description, parameters=_QUERY_PARAM
                        )
                        for t in tools
                    ]
                )
            ]
        self._chat = client.aio.chats.create(model=model, config=config)
        # Gemini function calls carry no id of their own; we mint one so the rest
        # of the pipeline can address a specific call the way Anthropic requires.
        self._pending: dict[str, ToolCall] = {}

    def _to_turn(self, resp) -> Turn:
        parts = resp.candidates[0].content.parts or []
        text = "".join(p.text for p in parts if getattr(p, "text", None))
        calls = []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc:
                calls.append(ToolCall(id=uuid.uuid4().hex, name=fc.name, args=dict(fc.args or {})))
        self._pending = {c.id: c for c in calls}
        input_tokens, output_tokens = _usage(resp)
        return Turn(
            text=text.strip(),
            calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def send(self, message: str) -> Turn:
        return self._to_turn(await self._chat.send_message(message))

    async def send_tool_results(self, results: list[ToolResult]) -> Turn:
        parts = [
            types.Part.from_function_response(
                name=r.call.name, response={"result": r.content}
            )
            for r in results
        ]
        return self._to_turn(await self._chat.send_message(parts))


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def start(self, system: str, tools: list[ToolSpec] | None = None) -> Conversation:
        return GeminiConversation(self._client, self.model, system, tools)

    async def complete(self, system: str, prompt: str) -> Turn:
        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        input_tokens, output_tokens = _usage(resp)
        return Turn(
            text=(resp.text or "").strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def embed(self, texts: list[str], dim: int) -> list[list[float]]:
        resp = await self._client.aio.models.embed_content(
            model=EMBED_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY", output_dimensionality=dim
            ),
        )
        return [list(e.values) for e in resp.embeddings]
