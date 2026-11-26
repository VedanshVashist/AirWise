"""Optional, quota-limited headline generation for public campaign posters."""
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


HEADLINES = {
    "School families": "Cleaner air starts at the school gate",
    "Commuters": "Give your commute a cleaner route",
    "Neighbours": "One neighbourhood, cleaner air",
}


def post_json(url, token, payload):
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    request.add_unredirected_header("Authorization", "Bearer " + token)
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def reserve_call():
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".upstash.io") or not token:
        return False
    limit = int(os.getenv("AIRWISE_CAMPAIGN_DAILY_LIMIT", "25"))
    if limit <= 0:
        return False
    day = datetime.now(timezone.utc).date().isoformat()
    key = "airwise:campaign:" + day
    result = post_json(url + "/multi-exec", token, [["INCR", key], ["EXPIRE", key, 172800]])
    count = result[0]["result"]
    return type(count) is int and 0 < count <= limit and result[1]["result"] == 1


def campaign_headline(data):
    audience = data["audience"]
    fallback = {"headline": HEADLINES[audience], "author": "Airwise template"}
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return fallback
    try:
        if reserve_call():
            result = post_json("https://api.openai.com/v1/chat/completions", key, {
                "model": os.getenv("AIRWISE_CAMPAIGN_MODEL", "gpt-4.1-mini"),
                "store": False, "max_completion_tokens": 80,
                "messages": [{"role": "user", "content": "Write one short, plain-text headline for a clean-air "
                              "awareness poster for " + audience + ". Encourage reducing vehicle emissions. "
                              "Use at most nine words. No statistics, quotes or claims about current conditions."}],
            })
            message = result["choices"][0]["message"]
            title = " ".join(message["content"].split()).strip('"')
            if not message.get("refusal") and 0 < len(title) <= 80:
                return {"headline": title, "author": "OpenAI headline"}
    except (ValueError, OSError, KeyError, IndexError, TypeError, AttributeError):
        pass
    return fallback
