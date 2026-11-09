from __future__ import annotations

import copy
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode

import pytest

from run_lyoko_web_next_emulator import (
    DFS_PATH,
    DFS_SCENARIOS,
    configure_dfs_observation,
    enable_lab_channels,
    load_server_module,
)


@pytest.fixture
def emulator(tmp_path):
    servers = []

    def start(scenario=None, lab_channels=False):
        module = load_server_module()
        handler = configure_dfs_observation(module, scenario=scenario)
        if lab_channels:
            handler = enable_lab_channels(module, handler)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(tmp_path)))
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        servers.append((server, worker))

        def request(path=DFS_PATH, method="GET", body=None, headers=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            effective = {"Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": module.CSRF}
            effective.update(headers or {})
            try:
                connection.request(method, path, body=urlencode(body or {}), headers=effective)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        return request, module

    yield start
    for server, worker in servers:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def assert_observation_boundary(payload):
    assert payload["schema"] == "lyoko.radio.dfs-observation/v1"
    assert payload["id"] == "5g"
    assert payload["observation_only"] is True
    assert payload["controls"] == {"apply": False, "bypass": False}
    assert payload["simulation"] is True
    assert payload["rf_transmission"] is False
    assert payload["physical_association"] is False
    assert payload["physical_validation"] == "not-proven"
    assert payload["dfs_tx_authorized"] is None
    assert payload["detector"]["liveness_verified"] is False
    assert payload["observed_at_uptime_seconds"] is None
    assert payload["source"]["provider"].startswith("emulator-")
    assert payload["cac"]["state"] in {"running", "required", "complete", "not-required", "unknown", "inconsistent"}
    assert payload["demo_static"] is True
    assert "no es una observacion de hardware" in payload["demo_notice"]


def test_default_endpoint_reports_missing_detector_without_unlocking_the_radio(emulator):
    request, module = emulator()
    before = copy.deepcopy(module.STATE)
    status, payload = request()
    assert status == 200
    assert_observation_boundary(payload)
    assert payload["demo_scenario"] is None
    assert payload["state"] == "blocked"
    assert payload["backend_ready"] is False
    assert payload["detector"]["running"] is False
    assert payload["tx"]["authorized"] is None
    assert payload["cac"]["remaining_seconds"] is None
    assert payload["cac"]["state"] == "not-required"
    assert payload["cac"]["required"] is False
    assert payload["nop"]["complete"] is False
    assert payload["channel"] == before["radios"]["5g"]["channel"]
    assert module.STATE == before


@pytest.mark.parametrize(
    "scenario, backend_ready, cac_state, seconds, nop_active, tx_authorized",
    [
        ("blocked", False, "not-required", None, None, False),
        ("cac", True, "running", 70, False, False),
        ("weather-cac", True, "running", 600, False, False),
        ("available", True, "complete", 0, False, True),
        ("radar", True, "required", None, True, False),
        ("nop", True, "required", None, True, False),
        ("unknown", None, "unknown", None, None, None),
    ],
)
def test_scenario_snapshots_are_explicitly_synthetic(
    emulator, scenario, backend_ready, cac_state, seconds, nop_active, tx_authorized
):
    request, module = emulator(scenario)
    before = copy.deepcopy(module.STATE)
    status, payload = request()
    assert status == 200
    assert_observation_boundary(payload)
    assert payload["demo_scenario"] == scenario
    assert payload["backend_ready"] is backend_ready
    assert payload["cac"]["state"] == cac_state
    assert payload["cac"]["remaining_seconds"] == seconds
    assert payload["nop"]["active"] is nop_active
    assert payload["tx"]["authorized"] is tx_authorized
    if nop_active:
        assert payload["nop"]["entries"] == [{"channel": 100, "remaining_seconds": 1800}]
    if scenario == "blocked":
        assert payload["current_channel"] == 36
        assert payload["cac"]["required"] is False
        assert payload["cac"]["required_seconds"] is None
    if scenario == "available":
        assert payload["backend_ready"] is True and payload["detector"]["running"] is True
        assert payload["cac"]["active"] is False and payload["cac"]["required"] is False
        assert payload["nop"]["active"] is False and payload["nop"]["complete"] is True
        assert payload["nop"]["entries"] == []
    if scenario == "weather-cac":
        assert payload["channel"] == 120
        assert payload["cac"]["required_seconds"] == 600
    if scenario == "unknown":
        assert payload["channel"] is None
        assert payload["detector"]["running"] is None
        assert payload["cac"]["required"] is None
        assert payload["nop"]["complete"] is False
    assert module.STATE == before


@pytest.mark.parametrize("scenario", DFS_SCENARIOS)
def test_display_scenarios_preserve_existing_channel_write_gates(emulator, scenario):
    request, module = emulator(scenario)
    before = copy.deepcopy(module.STATE)
    status, contract = request("/api/v1/radios/5g?view=contract")
    assert status == 200
    assert contract["simulation"] is True
    assert contract["rf_transmission"] is False
    assert contract["physical_association"] is False
    setting = next(item for item in contract["settings"]["settings"] if item["id"] == "channel")
    assert setting["writable"] is False
    assert setting["dfs_backend_ready"] is False
    assert request("/api/v1/radios/5g/stage", "POST", {"channel": "52"})[0] == 400
    status, error = request("/api/v1/radios/5g", "PATCH", {"channel": "52"},
                            {"X-OM-Regulatory-Ack": "OPENMITRASTAR_ES_DFS_V1"})
    assert status == 409
    assert error["error"] == "dfs-radar-backend-unavailable"
    assert module.STATE == before


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
def test_dfs_observation_has_no_write_operation(emulator, method):
    request, module = emulator("available")
    before = copy.deepcopy(module.STATE)
    status, error = request(method=method, body={"bypass": "true", "apply": "true"})
    assert status == 405
    assert error["error"] == "observation-only"
    assert error["controls"] == {"apply": False, "bypass": False}
    assert error["simulation"] is True and error["rf_transmission"] is False
    assert module.STATE == before


@pytest.mark.parametrize("scenario", ["cac", "weather-cac", "radar", "nop"])
def test_elapsed_time_never_finishes_cac_nop_or_authorizes_tx(emulator, monkeypatch, scenario):
    request, module = emulator(scenario)
    original = request()[1]
    original_state = copy.deepcopy(module.STATE)
    future_wall_time = time.time() + 86400
    future_monotonic = time.monotonic() + 86400
    with monkeypatch.context() as shifted_clock:
        shifted_clock.setattr(time, "time", lambda: future_wall_time)
        shifted_clock.setattr(time, "monotonic", lambda: future_monotonic)
        after = request()[1]
    assert after == original
    assert after["tx"]["authorized"] is False
    assert module.STATE == original_state


def test_query_parameters_cannot_select_a_demonstration(emulator):
    request, _ = emulator()
    normal = request()[1]
    assert request(DFS_PATH + "?scenario=available&backend_ready=true&bypass=true")[1] == normal


def test_lab_channels_remains_an_independent_explicit_mode(emulator):
    request, _ = emulator("cac", lab_channels=True)
    assert_observation_boundary(request()[1])
    _, staged = request("/api/v1/radios/5g/stage", "POST", {"channel": "149"})
    status, applied = request("/api/v1/config/apply", "POST", {
        "_confirm": "OPENMITRASTAR_CONFIG_TRANSACTION_V1", "_transaction": staged["transaction_id"]
    })
    assert status == 200 and applied["applied"] is True
    assert applied["simulation"] is True and applied["rf_transmission"] is False
    assert request("/api/v1/radios/5g")[1]["channel"] == 149
    # The DFS display fixture remains a snapshot, independent of LAB transactions.
    assert request()[1]["cac"]["state"] == "running"


def test_default_observation_keeps_dfs_required_after_a_lab_channel_change(emulator):
    request, _ = emulator(lab_channels=True)
    _, staged = request("/api/v1/radios/5g/stage", "POST", {"channel": "52"})
    status, _ = request("/api/v1/config/apply", "POST", {
        "_confirm": "OPENMITRASTAR_CONFIG_TRANSACTION_V1", "_transaction": staged["transaction_id"]
    })
    assert status == 200
    observation = request()[1]
    assert observation["current_channel"] == 52
    assert observation["cac"]["required"] is True
    assert observation["cac"]["state"] == "required"
    assert observation["backend_ready"] is False
    assert observation["tx"]["authorized"] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for the UI contract integration check")
def test_every_http_fixture_survives_the_real_ui_normalizer(emulator):
    normalizer = Path(__file__).resolve().parents[1] / "work/lyoko-web-next/src/dfs-observation.ts"
    fixtures = [emulator(scenario)[0]()[1] for scenario in (None, *DFS_SCENARIOS)]
    program = """
import { pathToFileURL } from 'node:url';
const { normalizeDfs } = await import(pathToFileURL(process.argv[1]));
let input = '';
for await (const chunk of process.stdin) input += chunk;
process.stdout.write(JSON.stringify(JSON.parse(input).map(payload => normalizeDfs(payload))));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", program, str(normalizer)],
                            input=json.dumps(fixtures), capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    normalized = json.loads(result.stdout)
    assert len(normalized) == len(fixtures)
    for raw, display in zip(fixtures, normalized, strict=True):
        assert display["simulation"] is True
        assert display["kind"] == "native"
        assert display["cac"]["state"] == raw["cac"]["state"]
        assert display["cac"]["active"] is raw["cac"]["active"]
        assert display["cac"]["remaining"] == raw["cac"]["remaining_seconds"]
        assert display["nop"]["active"] is raw["nop"]["active"]
        assert display["nop"]["complete"] is raw["nop"]["complete"]
        assert display["backendReady"] is raw["backend_ready"]
        assert display["detectorRunning"] is raw["detector"]["running"]
        assert display["txAuthorized"] is raw["tx"]["authorized"]
        assert (display["txAuthorized"] is True) == (raw["demo_scenario"] == "available")


def test_cli_requires_local_bind_for_opt_in_dfs_scenarios():
    script = Path(__file__).with_name("run_lyoko_web_next_emulator.py")
    result = subprocess.run([sys.executable, str(script), "--dfs-scenario", "available", "--bind", "0.0.0.0"],
                            capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode != 0
    assert "DFS demonstration must bind to loopback" in result.stderr
