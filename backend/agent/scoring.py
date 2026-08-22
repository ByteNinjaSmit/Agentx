import math
from datetime import datetime, timezone

SOURCE_AUTHORITY = {"research": 0.9, "patent": 0.8, "news": 0.5, "social": 0.3}


def keyword_overlap(text: str, context: str) -> float:
    t = set(text.lower().split())
    c = set(context.lower().split())
    if not c:
        return 0.5
    return min(len(t & c) / len(c) * 3, 1.0)


def score_item(item: dict, project_context: str) -> float:
    authority = SOURCE_AUTHORITY.get(item.get("source"), 0.4)

    days_old = 3
    if item.get("date"):
        try:
            dt = datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
            days_old = max((datetime.now(timezone.utc) - dt).days, 0)
        except ValueError:
            pass
    recency = math.exp(-days_old / 14)

    relevance = keyword_overlap(item.get("summary", "") + " " + item.get("title", ""), project_context)

    score = 10 * (0.30 * authority + 0.25 * recency + 0.30 * relevance + 0.15 * 0.5)
    return round(score, 1)
