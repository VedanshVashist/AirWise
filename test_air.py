"""Offline tests of the air data pipeline and its public HTTP contract."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
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
                ("{}", {"Content-Type": "application/json", "Origin": "https://elsewhere.example"}, 403),
            ]
            for body, headers, expected in cases:
                with self.subTest(expected=expected):
                    status, data = self.request("POST", "/api/campaign", body, headers)
                    self.assertEqual(status, expected)
                    self.assertIn("error", data)
            generate.assert_not_called()
