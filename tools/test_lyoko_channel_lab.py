from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
from urllib.parse import urlencode

import pytest
from run_lyoko_web_next_emulator import LAB_CHANNELS_5G, enable_lab_channels, load_server_module


@pytest.fixture
def lab(tmp_path):
    module = load_server_module()
    handler = enable_lab_channels(module)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(tmp_path)))
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    def request(path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        effective = {"Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": module.CSRF}
        effective.update(headers or {})
        connection.request("GET" if body is None else "POST", path, body=urlencode(body or {}), headers=effective)
        response = connection.getresponse(); data = json.loads(response.read()); connection.close()
        return response.status, data
    yield request
    server.shutdown(); server.server_close(); worker.join(timeout=3)


def operate(lab, action, txid):
    return lab(f"/api/v1/config/{action}", {"_confirm": "OPENMITRASTAR_CONFIG_TRANSACTION_V1", "_transaction": txid})


@pytest.mark.parametrize("channel", LAB_CHANNELS_5G)
def test_each_catalogue_channel_applies_and_rolls_back_only_in_simulation(lab, channel):
    _, original = lab("/api/v1/radios/5g")
    status, staged = lab("/api/v1/radios/5g/stage", {"channel": str(channel)})
    assert status == 200 and staged["applied"] is False
    status, applied = operate(lab, "apply", staged["transaction_id"])
    assert status == 200 and applied["applied"] and applied["verified"]
    _, current = lab("/api/v1/radios/5g")
    assert current["channel"] == channel
    assert current["simulation"] and current["rf_transmission"] is False and current["physical_association"] is False
    status, restored = operate(lab, "rollback", staged["transaction_id"])
    assert status == 200 and restored["rolled_back"]
    assert lab("/api/v1/radios/5g")[1]["channel"] == original["channel"]


def test_lab_does_not_disable_csrf_or_transaction_identity(lab):
    assert lab("/api/v1/radios/5g/stage", {"channel": "149"}, {"X-OM-CSRF": "wrong"})[0] == 403
    _, stage = lab("/api/v1/radios/5g/stage", {"channel": "149"})
    assert operate(lab, "apply", "0" * 64)[0] == 409
    assert operate(lab, "apply", stage["transaction_id"])[0] == 200
    assert operate(lab, "commit", stage["transaction_id"])[1]["persistence"] == "volatile"


def test_lab_is_explicit_and_baseline_is_unchanged(lab):
    ordinary = load_server_module()
    assert ordinary.validate_changes("5g", {"channel": "149"}) is not None
    assert lab("/api/v1/lab")[1]["rf_transmission"] is False
    contract = lab("/api/v1/radios/5g?view=contract")[1]
    channel = next(item for item in contract["settings"]["settings"] if item["id"] == "channel")
    assert channel["writable"] and channel["simulation"]
    assert channel["allowed_values"] == LAB_CHANNELS_5G
    assert lab("/api/v1/radios/5g/stage", {"channel": "999"})[0] == 400
