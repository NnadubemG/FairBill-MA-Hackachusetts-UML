"""Server smoke test (C10): routes return expected status + valid JSON.

Starts the stdlib server on an ephemeral port in a background thread and makes real
local requests. No new dependencies.
"""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from backend.compare.server import make_handler
from backend.compare.store import Store

FIXTURES = Path(__file__).parent / "fixtures" / "processed"


@pytest.fixture
def base_url():
    store = Store.load(FIXTURES)
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(store))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_c10_procedures_ok(base_url):
    with urlopen(base_url + "/procedures") as r:
        assert r.status == 200
        body = json.loads(r.read())
    assert [p["code"] for p in body["procedures"]] == ["80053", "99213"]
    assert body["framing_note"]


def test_c10_compare_ok(base_url):
    with urlopen(base_url + "/compare?code=99213") as r:
        assert r.status == 200
        body = json.loads(r.read())
    assert body["found"] is True
    assert {h["hospital_id"] for h in body["hospitals"]} == {"mgh", "bmc"}


def test_c10_compare_unknown_is_200(base_url):
    with urlopen(base_url + "/compare?code=00000") as r:
        assert r.status == 200
        body = json.loads(r.read())
    assert body["found"] is False


def test_c10_missing_code_is_400(base_url):
    with pytest.raises(HTTPError) as exc:
        urlopen(base_url + "/compare")
    assert exc.value.code == 400


def test_c10_unknown_route_is_404(base_url):
    with pytest.raises(HTTPError) as exc:
        urlopen(base_url + "/nope")
    assert exc.value.code == 404
