import httpx

ALERT_THRESHOLD = 8.0


async def send_alert(item: dict, webhook_url: str):
    if not webhook_url or item.get("impact_1_10", 0) < ALERT_THRESHOLD:
        return
    text = (
        f"*High-impact signal* ({item.get('source')}, {item.get('impact_1_10')}/10)\n"
        f"{item.get('title')}\n{item.get('url')}\n_{item.get('relevance_reason', '')}_"
    )
    async with httpx.AsyncClient(timeout=10) as c:
        await c.post(webhook_url, json={"text": text})
