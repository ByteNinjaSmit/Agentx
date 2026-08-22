import math
import os
from datetime import datetime, timezone

from google import genai
from google.genai import types

SOURCE_AUTHORITY = {"research": 0.9, "patent": 0.8, "news": 0.5, "social": 0.3}

# rough per-source scale for turning a raw engagement count into a 0..1 signal —
# "what count feels like strong traction for this source type"
ENGAGEMENT_SCALE = {"research": 50, "social": 200, "news": 100, "patent": 10}

EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _velocity(item: dict) -> float:
    engagement = item.get("engagement")
    if not isinstance(engagement, (int, float)):
        return 0.5  # no engagement signal available for this source — honestly neutral
    scale = ENGAGEMENT_SCALE.get(item.get("source"), 50)
    return min(math.log1p(max(engagement, 0)) / math.log1p(scale) * 0.5, 1.0)


def _recency(item: dict) -> float:
    days_old = 3
    if item.get("date"):
        try:
            dt = datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days_old = max((datetime.now(timezone.utc) - dt).days, 0)
        except ValueError:
            pass
    return math.exp(-days_old / 14)


async def score_items(items: list[dict], project_context: str) -> list[dict]:
    """Scores in place and returns items, batching one embedding call for all of
    them plus the project context — real semantic relevance instead of exact
    keyword overlap, and real engagement-based velocity instead of a constant."""
    if not items:
        return items

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    texts = [project_context] + [
        f"{it.get('title', '')} {it.get('summary', '')}" for it in items
    ]
    resp = await client.aio.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
    )
    vectors = [e.values for e in resp.embeddings]
    context_vec = vectors[0]

    for item, vec in zip(items, vectors[1:]):
        authority = SOURCE_AUTHORITY.get(item.get("source"), 0.4)
        recency = _recency(item)
        relevance = max(_cosine(context_vec, vec), 0.0)
        velocity = _velocity(item)
        score = 10 * (0.30 * authority + 0.25 * recency + 0.30 * relevance + 0.15 * velocity)
        item["impact_1_10"] = round(score, 1)

    return items
