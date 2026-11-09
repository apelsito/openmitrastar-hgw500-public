#!/usr/bin/env python3
"""Serve the packaged Lyoko Next overlay against the existing F313 API emulator."""

from __future__ import annotations

import argparse
import copy
import json
from functools import partial
import importlib.util
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SERVER_SOURCE = ROOT / "versions/lyoko-foundation-6.8.0-f313-developer-console-ui/emulator/server.py"
LAB_CHANNELS_5G = [*range(36, 65, 4), *range(100, 145, 4), *range(149, 178, 4)]
DFS_SCENARIOS = ("blocked", "cac", "weather-cac", "available", "radar", "nop", "unknown")
DFS_PATH = "/api/v1/radios/5g/dfs"


def load_server_module():
    spec = importlib.util.spec_from_file_location("lyoko_f313_emulator", SERVER_SOURCE)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load F313 API emulator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_frontend_identity(module, package):
    if (package / "overlay/etc/lyoko/frontend.env").is_file():
        module.SOURCE_OVERLAY = package / "overlay"
        original_frontend = module.frontend_fixture
        def frontend_fixture():
            response = original_frontend()
            response.update(asset_layout="split-v1", bundle=json.loads((package / "overlay/etc/lyoko/web-next.json").read_text(encoding="ascii")))
            return response
        module.frontend_fixture = frontend_fixture
    else:
        module.SOURCE_OVERLAY = ROOT / "versions/lyoko-foundation-6.8.2-f314-qtn-nondfs-guard/overlay"


def dfs_observation_fixture(module, scenario=None):
    """A static observation fixture, never an authority for RF or transactions.

    The default models the unavailable detector. Explicit scenarios describe
    synthetic snapshots: no elapsed-time calculation, driver call or state
    mutation can turn CAC/NOP completion into a radio permission.
    """
    if scenario is not None and scenario not in DFS_SCENARIOS:
        raise ValueError(f"unknown DFS scenario: {scenario}")
    source = "emulator-scenario" if scenario is not None else "emulator-default-fixture"
    radio = module.STATE["radios"]["5g"]
    channel = radio.get("channel") if scenario is None else 36 if scenario == "blocked" else 52
    dfs_required = channel in {52, 56, 60, 64, *range(100, 141, 4)}
    response = {
        "ok": True,
        "schema": "lyoko.radio.dfs-observation/v1",
        "id": "5g",
        "mode": "unavailable",
        "state": "blocked",
        "channel": channel,
        "current_channel": channel,
        "current_channel_dfs": dfs_required,
        "bandwidth_mhz": int(radio["bandwidth"]) if scenario is None else 20,
        "region": radio.get("region") if scenario is None else "ES",
        "policy_region": "ES",
        "backend_ready": False,
        "detector": {"running": False, "liveness_verified": False, "source": source},
        "cac": {"state": "required" if dfs_required else "not-required", "active": False, "required": dfs_required,
                "required_seconds": None, "remaining_seconds": None, "source": source},
        "nop": {"state": "unknown", "active": None, "entries": [], "complete": False, "source": source},
        "tx": {"authorized": None, "state": "unknown", "source": source},
        "dfs_tx_authorized": None,
        "doth": None,
        "channel_availability": {"code": None, "state": "unknown", "source": source},
        "observation_only": True,
        "controls": {"apply": False, "bypass": False},
        "physical_validation": "not-proven",
        "observed_at_uptime_seconds": None,
        "source": {"provider": source, "qdrv": source, "atomic": False},
        "simulation": True,
        "rf_transmission": False,
        "physical_association": False,
        "demo_scenario": scenario,
        "demo_static": True,
        "demo_notice": "Demostracion estatica del emulador; no es una observacion de hardware.",
    }
    if scenario is None:
        return response
    if scenario == "unknown":
        response.update(state="unknown", channel=None, current_channel=None,
                        current_channel_dfs=None, bandwidth_mhz=None, region=None, backend_ready=None)
        response["detector"]["running"] = None
        response["cac"].update(state="unknown", active=None, required=None)
        return response
    response["tx"].update(authorized=False, state="blocked")
    if scenario == "blocked":
        return response

    response["cac"]["required_seconds"] = 70
    response.update(mode="native", state=scenario, backend_ready=True, doth=True)
    response["detector"]["running"] = True
    response["nop"].update(state="clear", active=False, complete=True)
    if scenario in {"cac", "weather-cac"}:
        seconds = 600 if scenario == "weather-cac" else 70
        if scenario == "weather-cac":
            response.update(channel=120, current_channel=120)
        response["cac"].update(state="running", active=True,
                               required_seconds=seconds, remaining_seconds=seconds)
    elif scenario == "available":
        response["cac"].update(state="complete", active=False, required=False, remaining_seconds=0)
        response["tx"].update(authorized=True, state="authorized")
        response["channel_availability"]["state"] = "available"
    elif scenario in {"radar", "nop"}:
        response.update(channel=100, current_channel=100)
        response["cac"]["state"] = "required"
        response["nop"].update(state="active", active=True,
                              entries=[{"channel": 100, "remaining_seconds": 1800}])
        response["channel_availability"]["state"] = "unavailable"
    return response


def configure_dfs_observation(module, base_handler=None, scenario=None):
    """Add a read-only DFS route without changing any radio write validator."""
    # Validate once when configuring the handler, even before the first request.
    dfs_observation_fixture(module, scenario)

    class DfsObservationHandler(base_handler or module.Handler):
        def do_GET(self):
            if urlparse(self.path).path == DFS_PATH:
                self.json(dfs_observation_fixture(module, scenario))
                return
            super().do_GET()

        def reject_dfs_write(self):
            if urlparse(self.path).path != DFS_PATH:
                return False
            self.json({"ok": False, "error": "observation-only", "observation_only": True,
                       "controls": {"apply": False, "bypass": False},
                       "simulation": True, "rf_transmission": False,
                       "physical_association": False}, 405)
            return True

        def do_POST(self):
            if not self.reject_dfs_write():
                super().do_POST()

        def do_PATCH(self):
            if not self.reject_dfs_write():
                super().do_PATCH()

        def do_PUT(self):
            if not self.reject_dfs_write():
                self.send_error(501, "Unsupported method ('PUT')")

        def do_DELETE(self):
            if not self.reject_dfs_write():
                self.send_error(501, "Unsupported method ('DELETE')")

        def json(self, payload, status=200):
            if scenario is not None:
                payload = copy.deepcopy(payload)
                payload.update(simulation=True, rf_transmission=False, physical_association=False,
                               demo_scenario=scenario, demo_static=True)
            super().json(payload, status)

    return DfsObservationHandler


def enable_lab_channels(module, base_handler=None):
    """Explicit in-memory simulation. Does not import or invoke router tools."""
    original_validate = module.validate_changes
    original_settings = module.radio_settings
    def validate(band, changes):
        if band != "5g": return original_validate(band, changes)
        if not changes or not set(changes) <= {"ssid", "channel", "bandwidth"}: return "invalid-config"
        if "ssid" in changes:
            error = original_validate(band, {"ssid": changes["ssid"]})
            if error: return error
        if "channel" in changes and changes["channel"] not in {str(value) for value in LAB_CHANNELS_5G}: return "invalid-channel"
        if "bandwidth" in changes and changes["bandwidth"] not in {"20", "40", "80"}: return "invalid-bandwidth"
        return None
    def settings(band, radio):
        result = original_settings(band, radio)
        if band == "5g":
            for setting in result["settings"]:
                if setting["id"] in {"channel", "bandwidth"}:
                    setting.update(writable=True, blocked_reason="", certification="simulation-only-no-rf",
                                   source="emulador en RAM", risk="Aplicación virtual: no transmite RF ni conecta clientes físicos.")
                if setting["id"] == "channel":
                    setting.update(allowed_values=LAB_CHANNELS_5G, candidate_values=[], dfs_backend_ready=True,
                                   dfs_hardware_present=False, candidate_blocked_reason="", simulation=True)
        return result
    module.validate_changes = validate
    module.radio_settings = settings

    class LabHandler(base_handler or module.Handler):
        def do_GET(self):
            if urlparse(self.path).path == "/api/v1/lab":
                self.json({"ok": True, "schema": "lyoko.emulator.lab/v1", "radio_simulation": True,
                           "rf_transmission": False, "physical_association": False, "channels": LAB_CHANNELS_5G})
                return
            super().do_GET()

        def json(self, payload, status=200):
            payload = copy.deepcopy(payload)
            payload.update(simulation=True, rf_transmission=False, physical_association=False)
            schema = payload.get("schema")
            if schema == "lyoko.api.firmware/v1": payload["version"] = "LAB-SIMULADO-SIN-RF"
            if schema == "lyoko.radio.contract/v1" and payload.get("id") == "5g":
                payload["identity"].update(transport="in-memory-simulation", host_driver="simulator-not-qdrv")
                payload["capabilities"].update(channels=LAB_CHANNELS_5G, writable_settings=["ssid", "channel", "bandwidth"],
                    planned_settings=[], dfs="simulated", dfs_linux510_backend_ready=True, dfs_hardware_present=False,
                    control_backend="in-memory-radio-simulator", simulation=True)
            if schema == "lyoko.qtn.plan/v1": payload["apply_allowed"] = True
            super().json(payload, status)
    return LabHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4180)
    parser.add_argument("--f317", action="store_true", help="Expose the exact F317 optimization response shape")
    parser.add_argument("--lab-channels", action="store_true", help="Enable all catalogue channel transactions in RAM only, without RF")
    parser.add_argument("--dfs-scenario", choices=DFS_SCENARIOS,
                        help="Static DFS display demonstration on loopback; never enables radio writes or RF")
    args = parser.parse_args()
    if args.lab_channels and args.bind not in {"127.0.0.1", "localhost"}:
        raise SystemExit("channel simulation must bind to loopback")
    if args.dfs_scenario and args.bind not in {"127.0.0.1", "localhost"}:
        raise SystemExit("DFS demonstration must bind to loopback")

    from package_lyoko_web_next import default_package_dir
    package = (args.package or default_package_dir()).resolve()
    dashboard = package / "overlay/usr/share/openmitrastar/web/dashboard.html"
    assets = package / "overlay/www/assets"
    if not dashboard.is_file() or not assets.is_dir():
        raise SystemExit("packaged Lyoko Next overlay is incomplete")

    module = load_server_module()
    # Exact frontend identity for the recovered classic F314 presentation.
    configure_frontend_identity(module, package)
    with tempfile.TemporaryDirectory(prefix="lyoko-web-next-emulator-") as directory:
        web_root = Path(directory)
        shutil.copy2(dashboard, web_root / "dashboard.html")
        shutil.copytree(assets, web_root / "assets")
        handler_class = module.Handler
        if args.f317:
            class F317Handler(module.Handler):
                def do_GET(self) -> None:
                    if urlparse(self.path).path == "/api/v1/optimization":
                        self.json({
                            "ok": True,
                            "schema": "lyoko.api.optimization/v1",
                            "mode": "observe",
                            "persistence": "volatile-/run",
                            "supervisor_running": True,
                            "engine_running": True,
                            "last_sequence": 17,
                            "last_decision": "propose 2g=6 5g=44",
                            "automatic_apply": False,
                            "sensitive_identifiers": False,
                        })
                        return
                    super().do_GET()
            handler_class = F317Handler
        handler_class = configure_dfs_observation(module, handler_class, args.dfs_scenario)
        if args.lab_channels:
            handler_class = enable_lab_channels(module, handler_class)
        handler = partial(handler_class, directory=str(web_root))
        print(f"LYOKO_WEB_NEXT_EMULATOR=http://{args.bind}:{args.port}/dashboard.html", flush=True)
        if args.lab_channels: print("LAB_CHANNELS=enabled RF_TRANSMISSION=false PHYSICAL_ASSOCIATION=false", flush=True)
        if args.dfs_scenario:
            print(f"DFS_DEMO={args.dfs_scenario} STATIC=true RF_TRANSMISSION=false PHYSICAL_ASSOCIATION=false", flush=True)
        ThreadingHTTPServer((args.bind, args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
