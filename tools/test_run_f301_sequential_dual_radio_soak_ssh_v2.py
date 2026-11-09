from __future__ import annotations

import argparse
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f301_sequential_dual_radio_soak_ssh_v2.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("f301_soak_ssh_v2_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def namespace(runner, tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "execute": False,
        "router_host": "192.168.1.90",
        "oracle_host": "192.168.1.63",
        "oracle_user": "AELITA",
        "controller_url": "http://192.168.1.43:8008/speed.bin",
        "duration_hours": 6.0,
        "soak_seconds": 120,
        "cycle_pause_seconds": 30,
        "max_cycles": 0,
        "snapshot_attempts": 5,
        "snapshot_retry_seconds": 3.0,
        "resume": False,
        "output_dir": tmp_path / "output",
        "aelita_known_hosts": tmp_path / "known_hosts",
        "aelita_host_key_mode": "compat",
        "aelita_host_key_sha256": "",
        "aelita_ssh_connect_timeout": 8,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_v2_commands_use_policy_wrappers_and_hide_fingerprint_from_plan(tmp_path: Path) -> None:
    runner = load_runner()
    args = namespace(runner, tmp_path, aelita_host_key_sha256="SHA256:" + "A" * 43)
    command2 = runner.radio2_command(args, tmp_path / "radio2")
    command5 = runner.radio5_command(args, tmp_path / "radio5")
    plan = runner.immutable_plan(args, Path("candidate.bin"), runner.base.EXPECTED_SHA256)
    assert command2[1].endswith("run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py")
    assert command5[1].endswith("run_f293_5g_aelita_traffic_ssh_v2.py")
    assert "--aelita-host-key-sha256" in command2
    assert "--aelita-host-key-sha256" in command5
    assert plan["aelita_fingerprint_enforced"] is True
    assert args.aelita_host_key_sha256 not in json.dumps(plan)


def test_v2_dry_run_is_local_only_and_does_not_rewrite_pin(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    encoded = base64.b64encode(b"offline-aelita-host-key").decode("ascii")
    original = f"192.168.1.63 ssh-ed25519 {encoded}\n"
    known_hosts.write_text(original, encoding="ascii")
    output = tmp_path / "dry-run"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--duration-hours", "0.25",
            "--soak-seconds", "120",
            "--aelita-host-key-mode", "pinned",
            "--aelita-known-hosts", str(known_hosts),
            "--output-dir", str(output),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["mode"] == "dry-run"
    assert plan["schema"].endswith("/v2")
    assert plan["aelita_host_key_mode"] == "pinned"
    assert plan["hardware_actions_performed"] is False
    assert known_hosts.read_text(encoding="ascii") == original


def test_v2_source_is_scoped_and_legacy_soak_contract_remains_available() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    legacy = (ROOT / "tools/run_f301_sequential_dual_radio_soak.py").read_text(encoding="utf-8")
    assert "run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py" in source
    assert "run_f293_5g_aelita_traffic_ssh_v2.py" in source
    assert "run_aelita_2g_wpa2_speed_router_probe.py" in legacy
    assert "run_f293_5g_aelita_traffic.py" in legacy
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
