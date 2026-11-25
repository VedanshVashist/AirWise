"""Airwise local application server. Run with Python 3.11 or later."""
import argparse
import atexit
import base64
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
DATA = ROOT / ".airwise"
PUBLIC = ROOT / "public"
POLLUTANTS = "pm2_5,pm10,nitrogen_dioxide,ozone"
cache = {}
lock = threading.RLock()
model_lock = threading.Lock()
model_process = None
model_url = None


def remote(url, payload=None, timeout=12):
    headers = {"User-Agent": "Airwise/1.0", "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
        if os.getenv("AIRWISE_MODEL_KEY") and url.startswith(os.getenv("AIRWISE_MODEL_URL", "about:blank").rstrip("/") + "/"):
            headers["Authorization"] = "Bearer " + os.environ["AIRWISE_MODEL_KEY"]
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=timeout) as result:
        return json.load(result)


def coordinates(data):
    lat, lon = float(data["lat"]), float(data["lon"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Choose a valid location.")
    return round(lat, 4), round(lon, 4)


def air(location):
    coords = coordinates(location)
    with lock:
        saved = cache.get(coords)
    if saved and time.time() - saved[0] < 600:
        return saved[1]
    query = urlencode(dict(latitude=coords[0], longitude=coords[1], current="us_aqi," + POLLUTANTS,
                           hourly="us_aqi", past_days=1, forecast_days=4, timezone="auto", timeformat="unixtime"))
    result = remote("https://air-quality-api.open-meteo.com/v1/air-quality?" + query)
    current = result["current"]
    if current.get("us_aqi") is None or abs(time.time() - current["time"]) > 7200:
        raise RuntimeError("A fresh reading is unavailable.")
    with lock:
        if len(cache) > 100:
            cache.clear()
        cache[coords] = time.time(), result
    return result


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
            with lock:
                config = read_alerts()
            if config["enabled"]:
                loc = config["location"]
                current = air(loc)["current"]
                aqi = round(current["us_aqi"])
                stamp = [*coordinates(loc), current["time"]]
                if aqi >= config["threshold"] and config.get("last") != stamp:
                    body = precaution(aqi)
                    with lock:
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
            with lock:
                state = read_alerts()
                if state.get("enabled"):
                    state["error"] = "Airwise could not check the AQI or deliver the latest alert. It will retry."
                    save_alerts(state)
        wake_monitor.wait(600)
        wake_monitor.clear()


def inference_url():
    global model_process, model_url
    configured = os.getenv("AIRWISE_MODEL_URL")
    if configured:
        return configured.rstrip("/")
    folder = DATA / "ai"
    binary = folder / "llama-server.exe"
    model = next(folder.glob("*.gguf"), None)
    if not binary.exists() or model is None:
        raise RuntimeError("Local AI has not been installed.")
    with model_lock:
        if model_process is not None and model_process.poll() is None:
            return model_url
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        model_url = f"http://127.0.0.1:{port}/v1"
        model_process = subprocess.Popen([str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                                          "-c", "4096", "-np", "1", "-t", str(min(8, os.cpu_count() or 4))],
                                         cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(120):
            if model_process.poll() is not None:
                break
            try:
                remote(f"http://127.0.0.1:{port}/health", timeout=1)
                return model_url
            except OSError:
                time.sleep(.5)
        if model_process.poll() is None:
            model_process.terminate()
        raise RuntimeError("Local AI could not start.")


@atexit.register
def stop_model():
    if model_process and model_process.poll() is None:
        model_process.terminate()


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
    ids = json.loads(reply["choices"][0]["message"]["content"])["actions"]
    lines = [choices[key] for key in dict.fromkeys(ids) if key in choices][:2]
    if not lines:
        raise RuntimeError("Empty plan.")
    return {"answer": f"The current modeled US AQI in {loc['name']} is {reading}.\n\n" + "\n\n".join(lines),
            "mode": "AI-guided plan"}


def answer(data):
    question = str(data.get("question", "")).strip()[:1200]
    if not question:
        raise ValueError("Enter a question.")
    loc = data["location"]
    coordinates(loc)
    aqi = None
    try:
        aqi = round(air(loc)["current"]["us_aqi"])
        status = f"Current modeled US AQI {aqi}. {precaution(aqi)}"
    except (OSError, RuntimeError, KeyError):
        status = "Current AQI unavailable. Ask the user to check their local advisory before going outside."
    profile = data.get("profile", {})
    context = (f"Location: {str(loc['name'])[:80]}. {status} Household: {str(profile.get('household',''))[:80]}. "
               f"Travel: {str(profile.get('travel',''))[:80]}. Indoor filtration: {str(profile.get('home',''))[:80]}.")
    system = ("You are Airwise, a household air-quality assistant. Use the supplied context to answer the question directly in 2-4 short sentences. "
              "Explain the physical impact of a specific action. Use plain text. Do not invent sensor values, forecasts, savings, or local services. "
              "For indoor particles suggest a room-sized HEPA cleaner, avoiding smoke and candles, and ventilating when outside air improves. "
              "Combine trips or share a ride to reduce fuel use. Never recommend strenuous outdoor activity in unhealthy air. "
              "Never diagnose or suggest drugs. For severe breathing difficulty or chest pain advise urgent local emergency care.")
    messages = [{"role": "system", "content": system}]
    for item in data.get("history", [])[-4:]:
        if item.get("role") in ("user", "assistant"):
            messages.append({"role": item["role"], "content": str(item["content"])[:900]})
    messages.append({"role": "user", "content": context + "\nQuestion: " + question})
    url = inference_url()
    if aqi is not None and aqi > 100:
        return guided_answer(url, messages, aqi, loc, profile)
    reply = remote(url + "/chat/completions", {"model": os.getenv("AIRWISE_MODEL", "local"),
                   "messages": messages, "max_tokens": 230, "temperature": .35}, timeout=120)
    response = reply["choices"][0]["message"]["content"].strip()
    if not response:
        raise RuntimeError("The model returned an empty response.")
    return {"answer": response, "mode": "AI response"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

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
            return super().do_GET()
        q = {k: v[0] for k, v in parse_qs(path.query).items()}
        try:
            if path.path == "/api/air":
                return self.json_response(air(q))
            if path.path == "/api/locations":
                name = q.get("q", "").strip()[:100]
                if len(name) < 2:
                    return self.json_response([])
                results = remote("https://geocoding-api.open-meteo.com/v1/search?" + urlencode({"name": name, "count": 8, "language": "en"}))
                return self.json_response([dict(name=x["name"], country=x.get("country", ""), region=x.get("admin1", ""),
                                                lat=x["latitude"], lon=x["longitude"]) for x in results.get("results", [])])
            if path.path == "/api/alerts":
                with lock:
                    return self.json_response({**read_alerts(), "desktop": os.name == "nt"})
            return self.json_response({"error": "Unknown route."}, 404)
        except (ValueError, KeyError):
            return self.json_response({"error": "Invalid location or upstream data."}, 400)
        except (OSError, RuntimeError):
            return self.json_response({"error": "Air data is temporarily unavailable."}, 503)

    def do_POST(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host.split(":")[0] not in ("localhost", "127.0.0.1") or (origin and urlsplit(origin).netloc != host):
            return self.json_response({"error": "Use the local Airwise app."}, 403)
        if self.headers.get_content_type() != "application/json":
            return self.json_response({"error": "JSON required."}, 415)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 20000:
                return self.json_response({"error": "Invalid request size."}, 413)
            data = json.loads(self.rfile.read(length))
            if self.path == "/api/assistant":
                return self.json_response(answer(data))
            if self.path == "/api/alerts":
                loc = data["location"]
                lat, lon = coordinates(loc)
                threshold = int(data["threshold"])
                if threshold not in (0, 51, 101, 151, 201, 301) or not isinstance(data["enabled"], bool):
                    raise ValueError()
                with lock:
                    config = read_alerts()
                    config.update(enabled=data["enabled"] and os.name == "nt", threshold=threshold,
                                  location=dict(lat=lat, lon=lon, name=str(loc["name"])[:80], country=str(loc.get("country", ""))[:80]))
                    config.pop("error", None)
                    save_alerts(config)
                wake_monitor.set()
                return self.json_response(config)
            return self.json_response({"error": "Unknown route."}, 404)
        except (ValueError, KeyError, TypeError, AttributeError):
            return self.json_response({"error": "Check the submitted values."}, 400)
        except (RuntimeError, OSError, IndexError):
            return self.json_response({"error": "Service temporarily unavailable."}, 503)


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
