from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import f306_post_promotion_common as common
import f306_vlan_gate as vlan
import run_f306_multicast_igmp_physical as multicast
import run_f306_post_promotion_gates as coordinator


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "tools/f306_store_protection_probe.ps1"


def test_exact_f306_identity_is_shared() -> None:
    assert common.EXPECTED_VERSION == "lyoko-foundation-6.7.3-f306-unified-product-device"
    assert common.EXPECTED_SHA256 == "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
    assert common.KNOWN_HOSTS.name == "known_hosts.f306"
    assert common.LOCK_DIR.name == "f301-physical-radio.lock"


def test_multicast_and_vlan_retarget_exact_f306() -> None:
    multicast_source = (ROOT / "tools/run_f306_multicast_igmp_physical.py").read_text(encoding="utf-8")
    vlan_source = (ROOT / "tools/f306_vlan_gate.py").read_text(encoding="utf-8")
    for source in (multicast_source, vlan_source):
        assert "common.EXPECTED_VERSION" in source
        assert "common.EXPECTED_SHA256" in source
        assert "common.KNOWN_HOSTS" in source
        assert "common.install_ssh_v2" in source
        assert "common.active_soak_evidence" in source
    assert multicast.PLAN_SCHEMA.startswith("openmitrastar.f306-")
    assert vlan.PLAN_SCHEMA.startswith("openmitrastar.f306-")


def test_store_contract_is_f306_read_only_and_watchdog_guarded() -> None:
    source = STORE.read_text(encoding="utf-8")
    for marker in (
        common.EXPECTED_VERSION,
        common.EXPECTED_SHA256,
        "known_hosts.f306",
        "f301-physical-radio.lock",
        "StrictHostKeyChecking=yes",
        "MODULE_WATCHDOG_DISARMED=1",
        "openmitrastar.f306-unified-product-candidate/v1",
        "OPENMITRASTAR_F306_STORE_PROTECTION_READONLY_2F00A2DB",
    ):
        assert marker in source
    for forbidden in ("flash_erase", "nandwrite", "mtd_debug", "fw_setenv", "dd of=/dev/mtd"):
        assert forbidden not in source


def test_coordinator_is_ordered_fail_fast_and_nonpersistent() -> None:
    source = (ROOT / "tools/run_f306_post_promotion_gates.py").read_text(encoding="utf-8")
    assert 'GATES = ("multicast-igmp", "store-protection", "vlan4090")' in source
    assert '"fail_fast": True' in source
    assert '"persistent_writes": False' in source
    assert '"mtd_writes": False' in source
    assert '"flash": False' in source
    assert "common.active_soak_evidence()" in source


def test_store_powershell_parses() -> None:
    escaped = str(STORE).replace("'", "''")
    proc = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            "$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{escaped}',[ref]$t,[ref]$e);if($e.Count){{$e|%{{$_.ToString()}};exit 1}}",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout


def test_coordinator_dry_run_never_executes_hardware(tmp_path: Path) -> None:
    output = tmp_path / "coordinator"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/run_f306_post_promotion_gates.py"), "--output-dir", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    plan = json.loads((output / "plan.json").read_text(encoding="ascii"))
    assert plan["required_firmware"] == common.EXPECTED_VERSION
    assert plan["candidate_sha256"] == common.EXPECTED_SHA256
    assert plan["hardware_actions_performed"] is False
    assert plan["persistent_writes"] is False
    assert plan["mtd_writes"] is False
    assert plan["flash"] is False
    assert plan["child_preflights_pass"] is True
    assert [item["name"] for item in plan["child_preflights"]] == list(coordinator.GATES)


def test_execute_blocks_on_active_soak_before_any_child(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(coordinator, "local_preflight", lambda: {"ready": True})
    monkeypatch.setattr(
        coordinator.common,
        "active_soak_evidence",
        lambda: {
            "active": True,
            "processes": [{"pid": 42, "kind": "soak"}],
            "in_progress_checkpoints": [],
            "detection_error": "",
            "shared_lock_present": True,
        },
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("blocked coordinator attempted a child gate")

    monkeypatch.setattr(coordinator, "run_child", forbidden)
    output = tmp_path / "blocked"
    rc = coordinator.main(["--execute", "--ack", coordinator.ACK, "--output-dir", str(output)])
    assert rc == 2
    blocked = json.loads((output / "blocked.json").read_text(encoding="ascii"))
    assert blocked["status"] == "BLOCKED"
    assert blocked["hardware_actions_performed"] is False


def test_execute_stops_after_first_failed_gate(monkeypatch, tmp_path: Path) -> None:
    clear = {
        "active": False,
        "processes": [],
        "in_progress_checkpoints": [],
        "detection_error": "",
        "shared_lock_present": False,
    }
    monkeypatch.setattr(coordinator, "local_preflight", lambda: {"ready": True})
    monkeypatch.setattr(coordinator.common, "active_soak_evidence", lambda: dict(clear))
    calls: list[str] = []

    def fake_run(name, _command, output_dir):
        calls.append(name)
        return {
            "name": name,
            "status": "PASS" if len(calls) == 1 else "FAIL",
            "returncode": 0 if len(calls) == 1 else 1,
            "pass": len(calls) == 1,
            "evidence_dir": str(output_dir),
            "result_file": "",
        }

    monkeypatch.setattr(coordinator, "run_child", fake_run)
    output = tmp_path / "fail-fast"
    rc = coordinator.main(["--execute", "--ack", coordinator.ACK, "--output-dir", str(output)])
    assert rc == 1
    assert calls == ["multicast-igmp", "store-protection"]
    result = json.loads((output / "result.json").read_text(encoding="ascii"))
    assert result["status"] == "FAIL"
    assert result["failed_gate"] == "store-protection"
