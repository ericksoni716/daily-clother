"""Starts Closet for the browser tests with stand-ins for the model and for Claude.

    cd backend && python -m tests.e2e_backend --no-browser --no-tray --port N

The cutout is the middle of the photo and Claude always answers with the fixed
answer in `conftest.ANSWER`, so the browser can follow an item from upload to
described without the model file or any call to Claude.
"""
import json
import os
import sys
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

from closet import app, cli, weather
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, fake_cutter

_real_build = app.build_services


def fake_weather(url):
    """Only the trip browser tests enable this; no request leaves the test server."""
    parsed = urlsplit(url)
    if parsed.hostname == "geocoding-api.open-meteo.com":
        return json.dumps({"results": [{"name": "Lisbon", "country": "Portugal", "latitude": 38.7223,
                                        "longitude": -9.1393, "timezone": "Europe/Lisbon"}]}).encode()
    assert parsed.hostname in ("api.open-meteo.com", "archive-api.open-meteo.com")
    p = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    start = date.fromisoformat(p.get("start_date", date.today().isoformat()))
    end = date.fromisoformat(p.get("end_date", start.isoformat()))
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return json.dumps({"daily": {"time": days, "temperature_2m_min": [16] * len(days),
                                "temperature_2m_max": [22] * len(days), "precipitation_probability_max": [10] * len(days),
                                "weather_code": [1] * len(days), "precipitation_sum": [0] * len(days)}}).encode()


def fake_claude(images, routes):
    time.sleep(1)   # long enough for the page to show it being described
    return TagResult(ANSWER, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def build_services(cfg, **kwargs):
    sv = _real_build(cfg, cutter=fake_cutter, tagger=fake_claude, routes=lambda: ("plan",), **kwargs)
    sv.worker.is_ready = lambda: True
    return sv


if __name__ == "__main__":
    app.build_services = build_services
    if os.environ.get("CLOSET_E2E_WEATHER") == "1":
        weather.fetch = fake_weather
    sys.exit(cli.main(sys.argv[1:]))
