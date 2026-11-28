"""Offline tests of the air data pipeline and its public HTTP contract."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import server


NOW = 1_800_000_000
LOCATION = {"lat": 28.61, "lon": 77.21}


def report(stamp=NOW, aqi=0):
    return {"current": {"time": stamp, "us_aqi": aqi}}


class AirDataTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(server, "cache", {}))
        self.clock = self.enterContext(patch("server.time.time", return_value=NOW))
        self.timer = self.enterContext(patch("server.time.monotonic", return_value=100))
        self.remote = self.enterContext(patch("server.remote"))

    def test_cache_reuses_rounded_coordinates_until_ttl(self):
        self.remote.return_value = report()
        server.air(LOCATION)
        self.timer.return_value += server.CACHE_TTL - 1
        server.air({**LOCATION, "lat": 28.610001})
        self.remote.assert_called_once()
        self.timer.return_value += 1
        server.air(LOCATION)
        self.assertEqual(self.remote.call_count, 2)

    def test_reading_can_expire_before_cache_entry(self):
        self.remote.side_effect = [report(NOW - 7200), report(NOW, 42)]
        self.assertEqual(server.air(LOCATION)["current"]["us_aqi"], 0)
        self.clock.return_value += 1
        self.assertEqual(server.air(LOCATION)["current"]["us_aqi"], 42)

    def test_late_provider_response_preserves_newer_cached_reading(self):
        def finish_request(url):
            # A second request has completed since the first cache lookup.
            server.cache[server.coordinates(LOCATION)] = (100, report(NOW, 75))
            return report(NOW - 3600, 42)

        self.remote.side_effect = finish_request
        self.assertEqual(server.air(LOCATION)["current"]["us_aqi"], 75)
        self.assertEqual(server.air(LOCATION)["current"]["us_aqi"], 75)
        self.remote.assert_called_once()

    def test_half_point_aqi_crosses_the_same_thresholds_as_the_dashboard(self):
        for boundary in [50, 100, 150, 200, 300]:
            with self.subTest(boundary=boundary):
                self.assertEqual(server.rounded_aqi({"us_aqi": boundary + .49}), boundary)
                self.assertEqual(server.rounded_aqi({"us_aqi": boundary + .5}), boundary + 1)

    def test_invalid_upstream_data_is_never_cached(self):
        for value in [None, {}, report(NOW + 1), report(NOW - 7201),
                      report(aqi=-1), report(aqi=True), report(aqi=float("nan")), report(stamp="today")]:
            with self.subTest(value=value):
                self.remote.return_value = value
                with self.assertRaises(RuntimeError):
                    server.air(LOCATION)
                self.assertFalse(server.cache)

    def test_invalid_coordinates_do_not_contact_provider(self):
        for loc in [{}, {"lat": 0, "lon": 181}, {**LOCATION, "lat": None},
                    {**LOCATION, "lat": True}, {**LOCATION, "lon": "nan"}]:
            with self.subTest(loc=loc), self.assertRaises(ValueError):
                server.air(loc)
        self.remote.assert_not_called()

    def test_cache_evicts_only_the_oldest_city(self):
        self.remote.return_value = report()
        with patch.object(server, "CACHE_CAPACITY", 2):
            for lon in [1, 2, 3]:
                server.air({"lat": 0, "lon": lon})
                self.timer.return_value += 1
        self.assertEqual(set(server.cache), {(0, 2), (0, 3)})

    def test_sensor_uses_latest_valid_outdoor_measurement(self):
        def row(age, sensor, indoor=0, pm="12.3"):
            stamp = datetime.fromtimestamp(NOW - age, timezone.utc).isoformat()
            return {"timestamp": stamp, "location": {"indoor": indoor}, "sensor": {"id": sensor},
                    "sensordatavalues": [{"value_type": "P1", "value": pm}, {"value_type": "P2", "value": "8"}]}

        latest = row(10, 2)
        # An offset-bearing timestamp represents the same instant as its UTC equivalent.
        local_zone = timezone(timedelta(hours=5, minutes=30))
        latest["timestamp"] = datetime.fromtimestamp(NOW - 10, local_zone).isoformat()
        self.remote.return_value = [None, row(901, 0), row(900, 1), latest, row(0, 3, indoor=1),
                                    row(1, 4, pm="nan"), row(-1, 5), row(60, 6)]
        self.assertEqual(server.observation(LOCATION)["observation"],
                         {"time": NOW - 10, "sensor": 2, "pm10": 12.3, "pm2_5": 8})

    def test_empty_sensor_area_is_a_successful_lookup(self):
        self.remote.return_value = []
        self.assertIsNone(server.observation(LOCATION)["observation"])


class HostedApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.HostedHandler)
        thread = Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(httpd.server_close)
        cls.addClassCleanup(thread.join)
        cls.addClassCleanup(httpd.shutdown)
        cls.port = httpd.server_port

    def request(self, method, path, body=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        return response.status, json.load(response)

    def test_bad_coordinates_return_400_and_provider_outage_returns_503(self):
        with patch.object(server, "cache", {}), patch("server.remote", side_effect=OSError) as remote:
            self.assertEqual(self.request("GET", "/api/air?lat=wrong&lon=0")[0], 400)
            remote.assert_not_called()
            self.assertEqual(self.request("GET", "/api/air?lat=0&lon=0")[0], 503)

    def test_hosted_alerts_report_browser_mode(self):
        status, data = self.request("GET", "/api/alerts")
        self.assertEqual(status, 200)
        self.assertIs(data["desktop"], False)

    def test_invalid_campaign_requests_return_json_before_provider_call(self):
        with patch("server.campaign_headline") as generate:
            cases = [
                ("{}", {"Content-Type": "text/plain"}, 415),
                ("{", {"Content-Type": "application/json"}, 400),
                ("[]", {"Content-Type": "application/json"}, 400),
                ("{}", {"Content-Type": "application/json", "Origin": "https://elsewhere.example"}, 403),
            ]
            for body, headers, expected in cases:
                with self.subTest(expected=expected):
                    status, data = self.request("POST", "/api/campaign", body, headers)
                    self.assertEqual(status, expected)
                    self.assertIn("error", data)
            generate.assert_not_called()

    def test_city_search_keeps_usable_rows_and_reports_provider_failures(self):
        london = {"name": "London", "latitude": 51.5, "longitude": -0.12}
        with patch("server.remote", side_effect=[
            {"results": [None, {}, {**london, "latitude": 95}, london]}, None, {},
        ]) as provider:
            path = "/api/locations?q=London"
            self.assertEqual(self.request("GET", "/api/locations?q=L"), (200, []))
            provider.assert_not_called()
            self.assertEqual(self.request("GET", path), (200, [
                dict(name="London", lat=51.5, lon=-0.12, country="", region="")]))
            self.assertEqual(self.request("GET", path)[0], 503)
            self.assertEqual(self.request("GET", path), (200, []))

    def test_invalid_assistant_context_is_rejected_before_provider_access(self):
        body = {"location": {**LOCATION, "name": "Delhi"}, "question": "Plan my commute"}
        with patch.dict("os.environ", AIRWISE_MODEL_URL="https://model.example"), patch("server.remote") as provider:
            for invalid in [{"profile": []}, {"history": [None]}, {"question": None}]:
                with self.subTest(invalid=invalid):
                    status, _ = self.request("POST", "/api/assistant", json.dumps({**body, **invalid}),
                                             {"Content-Type": "application/json"})
                    self.assertEqual(status, 400)
            provider.assert_not_called()

    def test_assistant_uses_approved_actions_and_handles_malformed_model_replies(self):
        body = json.dumps({"location": {**LOCATION, "name": "Delhi"}, "question": "Plan my commute"})
        with patch("server.inference_url", return_value="https://model.example"), patch.dict(
                "os.environ", AIRWISE_MODEL_URL="https://model.example"), patch("server.air", return_value=report(aqi=155)):
            for content, status in [('{"actions":["errands"]}', 200), ('{"actions":["unknown"]}', 503),
                                    ('{"actions":"errands"}', 503), (None, 503)]:
                with self.subTest(content=content), patch("server.remote", return_value={"choices": [{"message": {"content": content}}]}):
                    code, result = self.request("POST", "/api/assistant", body, {"Content-Type": "application/json"})
                    self.assertEqual(code, status)
                    if status == 200:
                        self.assertIn("Combine essential errands", result["answer"])


class DesktopAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(server, "DATA", Path(folder)))
        self.settings = dict(enabled=True, threshold=101, history=[],
                             location={**LOCATION, "name": "Delhi"})

    def test_provider_failure_after_city_change_preserves_new_settings(self) -> None:
        updated = {**self.settings, "location": {"lat": 0, "lon": 0, "name": "New city"}}

        def switch_city_before_failure(location):
            server.save_alerts(updated)
            raise OSError("Provider offline")

        server.save_alerts(self.settings)
        with patch("server.air", side_effect=switch_city_before_failure):
            server.check_desktop_alert()
        self.assertEqual(server.read_alerts(), updated)

    def test_failed_replace_preserves_previous_settings_and_cleans_temp_file(self) -> None:
        server.save_alerts(self.settings)
        with patch.object(Path, "replace", side_effect=OSError), self.assertRaises(OSError):
            server.save_alerts({**self.settings, "enabled": False})
        self.assertEqual(server.read_alerts(), self.settings)
        self.assertEqual(list(server.DATA.iterdir()), [server.DATA / "alerts.json"])

    def test_desktop_failure_records_one_history_entry_for_repeated_reading(self) -> None:
        server.save_alerts(self.settings)
        with patch("server.air", return_value=report(aqi=100.5)), patch(
                "server.desktop_notice", side_effect=OSError) as notify:
            server.check_desktop_alert()
            server.check_desktop_alert()
        notify.assert_called_once()
        saved = server.read_alerts()
        self.assertEqual([entry["aqi"] for entry in saved["history"]], [101])
        self.assertIn("Windows notifications", saved["error"])

    def test_invalid_updates_preserve_saved_preferences(self):
        data = dict(enabled=False, threshold="101", location={**LOCATION, "name": "Delhi"})
        with patch.object(server, "wake_monitor") as wake:
            saved = server.configure_alerts(data)
            self.assertEqual(saved["threshold"], 101)
            for invalid in [False, 101.5, -1]:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    server.configure_alerts({**data, "threshold": invalid})
            self.assertEqual(server.read_alerts(), saved)
            wake.set.assert_called_once()
