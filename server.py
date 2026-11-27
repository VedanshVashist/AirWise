"""Airwise local application server. Run with Python 3.11 or later."""
import argparse
import base64
import json
import math
import os
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.etree import ElementTree

from campaign_service import campaign_headline
from http_client import remote
from model_runtime import inference_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / ".airwise"
PUBLIC = ROOT / "public"
POLLUTANTS = "pm2_5,pm10,nitrogen_dioxide,ozone"
MAX_READING_AGE = 7200
CACHE_TTL = 600
CACHE_CAPACITY = 100
cache = {}
cache_lock = threading.Lock()
alerts_lock = threading.Lock()


def coordinates(data):
    try:
        if isinstance(data["lat"], bool) or isinstance(data["lon"], bool):
            raise ValueError
        lat, lon = float(data["lat"]), float(data["lon"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("Choose a valid location.") from error
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Choose a valid location.")
    return round(lat, 4), round(lon, 4)


def fresh_reading(result, now):
    current = result.get("current") if isinstance(result, dict) else None
    if not isinstance(current, dict):
        return False
    aqi, stamp = current.get("us_aqi"), current.get("time")
    return (type(aqi) in (int, float) and 0 <= aqi < math.inf
            and type(stamp) in (int, float) and now - MAX_READING_AGE <= stamp <= now)


def air(location):
    coords = coordinates(location)
    with cache_lock:
        saved = cache.get(coords)
        if saved and time.monotonic() - saved[0] < CACHE_TTL and fresh_reading(saved[1], time.time()):
            return saved[1]
    query = urlencode(dict(latitude=coords[0], longitude=coords[1], current="us_aqi," + POLLUTANTS,
                           hourly="us_aqi", past_days=1, forecast_days=4, timezone="auto", timeformat="unixtime"))
    result = remote("https://air-quality-api.open-meteo.com/v1/air-quality?" + query)
    if not fresh_reading(result, time.time()):
        raise RuntimeError("A fresh reading is unavailable.")
    with cache_lock:
        existing = cache.get(coords)
        if existing and existing[1]["current"]["time"] > result["current"]["time"] and fresh_reading(existing[1], time.time()):
            return existing[1]
        if coords not in cache and len(cache) >= CACHE_CAPACITY:
            del cache[min(cache, key=lambda key: cache[key][0])]
        cache[coords] = time.monotonic(), result
    return result


def observation(location):
    lat, lon = coordinates(location)
    rows = remote(f"https://data.sensor.community/airrohr/v1/filter/area={lat},{lon},10")
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected sensor response.")
    now = time.time()
    latest = None
    for row in rows:
        try:
            if str(row["location"]["indoor"]) != "0":
                continue
            observed = datetime.fromisoformat(row["timestamp"])
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            stamp = observed.timestamp()
            if not 0 <= now - stamp <= 900 or (latest and stamp <= latest["time"]):
                continue
            values = {v["value_type"]: float(v["value"]) for v in row["sensordatavalues"]
                      if v["value_type"] in ("P1", "P2")}
            pm10, pm25 = values["P1"], values["P2"]
            if all(math.isfinite(v) and v >= 0 for v in (pm10, pm25)):
                latest = dict(time=int(stamp), sensor=int(row["sensor"]["id"]), pm10=pm10, pm2_5=pm25)
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
            continue
    return {"source": "Sensor.Community", "radius_km": 10, "unit": "µg/m³", "observation": latest}


def search_locations(query):
    name = query.strip()[:100]
    if len(name) < 2:
        return []
    params = urlencode({"name": name, "count": 8, "language": "en"})
    result = remote("https://geocoding-api.open-meteo.com/v1/search?" + params)
    if not isinstance(result, dict) or not isinstance(result.get("results", []), list):
        raise RuntimeError("Unexpected geocoding response.")
    locations = []
    for row in result.get("results", []):
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
            continue
        try:
            lat, lon = coordinates({"lat": row.get("latitude"), "lon": row.get("longitude")})
        except ValueError:
            continue
        locations.append(dict(name=row["name"], lat=lat, lon=lon,
                              region=row.get("admin1") or "", country=row.get("country") or ""))
    return locations


def rounded_aqi(current):
    """Match the dashboard's Math.round at category and notification thresholds."""
    return math.floor(current["us_aqi"] + 0.5)


def precaution(aqi):
    if aqi > 300:
        return "Avoid outdoor physical activity and use the cleanest indoor space available."
    if aqi > 200:
        return "Avoid strenuous outdoor activity. Sensitive groups should move activity indoors."
    if aqi > 150:
        return "Shorten outdoor activity and take breaks. Sensitive groups should avoid prolonged or heavy exertion."
    if aqi > 100:
        return "Children, older adults and people with heart or lung conditions should shorten prolonged or intense outdoor activity."
    if aqi > 50:
        return "If you are unusually sensitive, consider shorter or less intense outdoor activity."
    return "Outdoor activities are generally suitable. Check again before a long outing."


def read_alerts():
    try:
        return json.loads((DATA / "alerts.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {"enabled": False, "threshold": 101, "history": []}


def save_alerts(value):
    DATA.mkdir(exist_ok=True)
    path = DATA / "alerts.tmp"
    path.write_text(json.dumps(value), encoding="utf8")
    path.replace(DATA / "alerts.json")


def configure_alerts(data):
    loc = data["location"]
    lat, lon = coordinates(loc)
    threshold = data["threshold"]
    if isinstance(threshold, str) and threshold.isdecimal():
        threshold = int(threshold)
    if type(threshold) is not int or threshold not in (0, 51, 101, 151, 201, 301):
        raise ValueError("Invalid alert threshold.")
    if type(data["enabled"]) is not bool or not isinstance(loc["name"], str):
        raise ValueError("Invalid alert settings.")
    with alerts_lock:
        config = read_alerts()
        config.update(enabled=data["enabled"] and os.name == "nt", threshold=threshold,
                      location=dict(lat=lat, lon=lon, name=loc["name"][:80], country=str(loc.get("country", ""))[:80]))
        config.pop("error", None)
        save_alerts(config)
    wake_monitor.set()
    return config


def desktop_notice(title, body):
    toast = ElementTree.Element("toast")
    binding = ElementTree.SubElement(ElementTree.SubElement(toast, "visual"), "binding", template="ToastGeneric")
    for line in (title, body):
        ElementTree.SubElement(binding, "text").text = line
    script = """
    $ErrorActionPreference='Stop'
    [Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime] | Out-Null
    $xml=New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($env:AIRWISE_TOAST)
    $toast=[Windows.UI.Notifications.ToastNotification]::new($xml)
    $id='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
    $notifier=[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id)
    $setting=$notifier.Setting.ToString()
    if ($setting -eq 'Enabled') { $notifier.Show($toast) }
    Write-Output $setting
    """
    process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                    base64.b64encode(script.encode("utf-16le")).decode()], check=True, timeout=20,
                   env={**os.environ, "AIRWISE_TOAST": ElementTree.tostring(toast, encoding="unicode")},
                   creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
    return process.stdout.decode(errors="replace").strip() == "Enabled"


wake_monitor = threading.Event()


def monitor():
    while True:
        try:
            with alerts_lock:
                config = read_alerts()
            if config["enabled"]:
                loc = config["location"]
                current = air(loc)["current"]
                aqi = rounded_aqi(current)
                stamp = [*coordinates(loc), current["time"]]
                if aqi >= config["threshold"] and config.get("last") != stamp:
                    body = precaution(aqi)
                    with alerts_lock:
                        check = read_alerts()
                        if check == config:
                            try:
                                delivered = desktop_notice(f"Airwise · {loc['name']} · US AQI {aqi}", body)
                            except (OSError, subprocess.SubprocessError):
                                delivered = False
                            config["last"] = stamp
                            config["history"] = ([dict(time=current["time"], city=loc["name"], aqi=aqi, body=body)] + config["history"])[:20]
                            if delivered:
                                config.pop("error", None)
                            else:
                                config["error"] = "Your AQI alert is saved here. Enable Windows notifications for PowerShell to receive desktop alerts."
                            save_alerts(config)
        except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
            with alerts_lock:
                state = read_alerts()
                if state.get("enabled"):
                    state["error"] = "Airwise could not check the AQI or deliver the latest alert. It will retry."
                    save_alerts(state)
        wake_monitor.wait(600)
        wake_monitor.clear()


def model_content(reply):
    try:
        content = reply["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Unexpected model response.") from error
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The model returned an empty response.")
    return content.strip()


def guided_answer(url, messages, reading, loc, profile):
    """Let the model compose a plan from actions suitable for the current AQI."""
    choices = {
        "outdoors": precaution(reading) + " Moving exertion into cleaner air reduces the amount of polluted air inhaled.",
        "school_run": "Coordinate a shared school pickup and turn off the engine while waiting. This cuts vehicle trips and exhaust at the school gate.",
        "shared_transport": "For an essential journey, use a shared ride or transit where available. Wait away from idling engines to reduce roadside exposure.",
        "errands": "Combine essential errands into one trip and postpone optional stops. This reduces both fuel use and time in traffic.",
        "cooking": "Steam or simmer food instead of frying and use a hood that vents outdoors. This reduces particles produced by cooking.",
        "indoor_sources": "Skip candles, incense and smoking indoors. Preventing particles at the source helps keep the room cleaner.",
        "windows": "When outdoor particle levels are elevated, keep windows closed if the room stays comfortable and safe. Ventilate when outdoor air improves.",
        "community": "Arrange a cleaner indoor venue and share the latest AQI with the group before people leave home. One update can help members avoid unnecessary trips.",
        "family": "Offer a cleaner indoor activity for children and older relatives. It reduces their time breathing polluted outdoor air.",
        "pollutants": "PM2.5 and PM10 describe airborne particles of different sizes. Fine particles can reach deep into the lungs. Nitrogen dioxide and ozone are gases and require different controls from particle filtration.",
        "index": "The US AQI summarizes outdoor pollution on a health-based scale. A higher number means greater risk, particularly for children, older adults and people with heart or lung conditions.",
        "filter": "A HEPA cleaner sized for the room can capture airborne particles. Use it in the room where people spend the most time.",
    }
    if profile.get("home") == "No air purifier":
        choices["filter"] = "If a filter is unavailable, choose a room away from cooking smoke and skip candles or incense. Avoiding new particles helps limit indoor exposure."
    if reading <= 150:
        choices["quiet_route"] = "If outdoor activity is suitable for your household, use a short route away from busy roads. This reduces time beside concentrated traffic exhaust."
    instructions = ("Select the one or two most relevant action IDs for the user's latest question. "
                    "Respect household resources and travel mode. Answer with JSON only. Available actions: "
                    + json.dumps(choices))
    schema = {"type": "object", "properties": {"actions": {"type": "array", "minItems": 1, "maxItems": 2,
              "items": {"type": "string", "enum": list(choices)}}}, "required": ["actions"], "additionalProperties": False}
    reply = remote(url + "/chat/completions", {"model": os.getenv("AIRWISE_MODEL", "local"),
                   "messages": [{"role": "system", "content": instructions}, *messages[1:]],
                   "max_tokens": 72, "temperature": .15, "response_format": {"type": "json_schema",
                   "json_schema": {"name": "air_plan", "strict": True, "schema": schema}}}, timeout=100)
    try:
        ids = json.loads(model_content(reply))["actions"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("Invalid model plan.") from error
    if not isinstance(ids, list) or not 1 <= len(ids) <= 2 or not all(isinstance(key, str) and key in choices for key in ids):
        raise RuntimeError("Invalid model actions.")
    lines = [choices[key] for key in dict.fromkeys(ids)]
    return {"answer": f"The current modeled US AQI in {loc['name']} is {reading}.\n\n" + "\n\n".join(lines),
            "mode": "AI-guided plan"}


def answer(data):
    question = data.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Enter a question.")
    question = question.strip()[:1200]
    loc = data["location"]
    coordinates(loc)
    if not isinstance(loc.get("name"), str) or not loc["name"].strip():
        raise ValueError("Choose a named location.")
    profile = data.get("profile", {})
    history = data.get("history", [])
    if not isinstance(profile, dict) or not isinstance(history, list):
        raise ValueError("Invalid assistant context.")
    turns = []
    for item in history[-4:]:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            raise ValueError("Invalid conversation history.")
        if item.get("role") in ("user", "assistant"):
            turns.append({"role": item["role"], "content": item["content"][:900]})
    aqi = None
    try:
        aqi = rounded_aqi(air(loc)["current"])
        status = f"Current modeled US AQI {aqi}. {precaution(aqi)}"
    except (OSError, RuntimeError, KeyError):
        status = "Current AQI unavailable. Ask the user to check their local advisory before going outside."
    context = (f"Location: {str(loc['name'])[:80]}. {status} Household: {str(profile.get('household',''))[:80]}. "
               f"Travel: {str(profile.get('travel',''))[:80]}. Indoor filtration: {str(profile.get('home',''))[:80]}.")
    system = ("You are Airwise, a household air-quality assistant. Use the supplied context to answer the question directly in 2-4 short sentences. "
              "Explain the physical impact of a specific action. Use plain text. Do not invent sensor values, forecasts, savings, or local services. "
              "For indoor particles suggest a room-sized HEPA cleaner, avoiding smoke and candles, and ventilating when outside air improves. "
              "Combine trips or share a ride to reduce fuel use. Never recommend strenuous outdoor activity in unhealthy air. "
              "Never diagnose or suggest drugs. For severe breathing difficulty or chest pain advise urgent local emergency care.")
    messages = [{"role": "system", "content": system}, *turns]
    messages.append({"role": "user", "content": context + "\nQuestion: " + question})
    url = inference_url()
    if aqi is not None and aqi > 100:
        return guided_answer(url, messages, aqi, loc, profile)
    reply = remote(url + "/chat/completions", {"model": os.getenv("AIRWISE_MODEL", "local"),
                   "messages": messages, "max_tokens": 230, "temperature": .35}, timeout=120)
    return {"answer": model_content(reply), "mode": "AI response"}


class Handler(SimpleHTTPRequestHandler):
    hosted = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def json_response(self, data, code=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path)
        if not path.path.startswith("/api/"):
            if self.hosted:
                return self.json_response({"error": "Unknown route."}, 404)
            return super().do_GET()
        q = {k: v[0] for k, v in parse_qs(path.query).items()}
        try:
            if path.path == "/api/air":
                return self.json_response(air(q))
            if path.path == "/api/observation":
                return self.json_response(observation(q))
            if path.path == "/api/locations":
                return self.json_response(search_locations(q.get("q", "")))
            if path.path == "/api/alerts":
                if self.hosted:
                    return self.json_response({"desktop": False, "enabled": False, "threshold": 101, "history": []})
                with alerts_lock:
                    return self.json_response({**read_alerts(), "desktop": os.name == "nt"})
            return self.json_response({"error": "Unknown route."}, 404)
        except (ValueError, KeyError):
            return self.json_response({"error": "Invalid location or upstream data."}, 400)
        except (OSError, RuntimeError):
            return self.json_response({"error": "Air data is temporarily unavailable."}, 503)

    def do_POST(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if not self.hosted and host.split(":")[0] not in ("localhost", "127.0.0.1"):
            return self.json_response({"error": "Use the local Airwise app."}, 403)
        if origin and urlsplit(origin).netloc != host:
            return self.json_response({"error": "Use the same Airwise origin."}, 403)
        if self.headers.get_content_type() != "application/json":
            return self.json_response({"error": "JSON required."}, 415)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 20000:
                return self.json_response({"error": "Invalid request size."}, 413)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            path = urlsplit(self.path).path
            if path == "/api/campaign":
                return self.json_response(campaign_headline(data))
            if path == "/api/assistant":
                if self.hosted and not os.getenv("AIRWISE_MODEL_URL"):
                    return self.json_response({"error": "Hosted AI is not configured."}, 503)
                return self.json_response(answer(data))
            if path == "/api/alerts":
                if self.hosted:
                    return self.json_response({"error": "Save browser alerts on this device."}, 400)
                return self.json_response(configure_alerts(data))
            return self.json_response({"error": "Unknown route."}, 404)
        except (ValueError, KeyError, TypeError, AttributeError):
            return self.json_response({"error": "Check the submitted values."}, 400)
        except (RuntimeError, OSError, IndexError):
            return self.json_response({"error": "Service temporarily unavailable."}, 503)


class HostedHandler(Handler):
    hosted = True

    def do_HEAD(self):
        self.send_error(405)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open Airwise in the default browser")
    args = parser.parse_args()
    address = f"http://localhost:{args.port}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        if args.open and "desktop" in remote(address + "/api/alerts", timeout=2):
            webbrowser.open(address)
            raise SystemExit(0)
        raise
    threading.Thread(target=monitor, daemon=True).start()
    print(f"Airwise is running at http://localhost:{args.port}", flush=True)
    if args.open:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
