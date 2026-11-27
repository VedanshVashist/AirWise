"""JSON transport for Airwise data and inference providers."""
import json
import os
import urllib.request


def remote(url, payload=None, timeout=12):
    headers = {"User-Agent": "Airwise/1.0", "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, headers=headers)
    configured_url = os.getenv("AIRWISE_MODEL_URL")
    model_key = os.getenv("AIRWISE_MODEL_KEY")
    if body is not None and configured_url and model_key and url == configured_url.rstrip("/") + "/chat/completions":
        request.add_unredirected_header("Authorization", "Bearer " + model_key)
    with urllib.request.urlopen(request, timeout=timeout) as result:
        try:
            return json.load(result)
        except ValueError as error:
            raise RuntimeError("The service returned invalid JSON.") from error
