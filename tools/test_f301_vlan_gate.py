from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import f301_vlan_gate as gate


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools/f301_vlan_gate.py"
ENDPOINT_SOURCE = ROOT / "tools/f301_vlan_endpoint.c"
BUILD_SCRIPT = ROOT / "tools/build_f301_vlan_endpoint.py"
CONTROLLER = ROOT / "tools/f301_vlan_controller.ps1"
UART_GUARD = ROOT / "tools/f301_vlan_uart_guard.ps1"


def clear_workflows() -> dict[str, object]:
    return {
        "active": False,
        "processes": [],
        "detection_error": "",
        "shared_lock_present": False,
    }


def test_local_preflight_pins_exact_f301_and_endpoint() -> None:
    result = gate.local_preflight()
    assert result["ready"] is True, result
    assert result["candidate_sha256"] == gate.EXPECTED_CANDIDATE_SHA256
    assert len(str(result["endpoint_sha256"])) == 64
    assert all(result["checks"].values())


def test_dry_run_is_offline_and_describes_vlan_4090(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run attempted hardware")

    monkeypatch.setattr(gate, "active_workflow_evidence", clear_workflows)
    monkeypatch.setattr(gate, "router_exec", forbidden)
    monkeypatch.setattr(gate, "powershell_json", forbidden)
    monkeypatch.setattr(gate.wpa, "oracle_ps", forbidden)
    output = tmp_path / "dry-run"
    assert gate.main(["--output-dir", str(output)]) == 0
    plan = json.loads((output / "plan.json").read_text(encoding="ascii"))
    assert plan["vlan"]["id"] == 4090
    assert plan["vlan"]["attached_to_br0"] is False
    assert plan["vlan"]["qdrv_vlan_path"] is False
    assert plan["recovery"]["all_three_required_before_mutation"] is True
    assert plan["execute_eligible_offline"] is True
    assert plan["execute_allowed_now"] is False
    assert len(plan["execute_blocked_until"]) == 5
    assert plan["hardware_actions_performed"] is False
    assert plan["router_persistence"] is False
    assert plan["mtd_writes"] is False


def test_execute_fails_closed_on_conflicting_workflow_before_hardware(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    conflict = clear_workflows()
    conflict["active"] = True
    conflict["processes"] = [{"pid": 42, "name": "python.exe", "kind": "dfs"}]
    monkeypatch.setattr(gate, "active_workflow_evidence", lambda: conflict)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("blocked gate attempted hardware")

    monkeypatch.setattr(gate, "router_exec", forbidden)
    monkeypatch.setattr(gate, "powershell_json", forbidden)
    output = tmp_path / "blocked"
    rc = gate.main([
        "--execute", "--ack", gate.ACK,
        "--controller-interface", "Ethernet",
        "--output-dir", str(output),
    ])
    assert rc == 2
    result = json.loads((output / "blocked.json").read_text(encoding="ascii"))
    assert result["status"] == "BLOCKED"
    assert result["hardware_actions_performed"] is False


def test_workflow_guard_is_fail_closed() -> None:
    assert gate.workflow_guard_clear(clear_workflows()) is True
    for field, value in (
        ("active", True),
        ("detection_error", "inventory failed"),
        ("shared_lock_present", True),
    ):
        evidence = clear_workflows()
        evidence[field] = value
        assert gate.workflow_guard_clear(evidence) is False


def test_vlan_packet_protocol_round_trip() -> None:
    token = "a" * 32
    packet = gate.vlan_packet(token, "DOWN", 17, 256)
    assert len(packet) == 256
    assert gate.parse_vlan_reply(packet, token) == 17
    assert gate.parse_vlan_reply(packet, "b" * 32) is None
    with pytest.raises(ValueError):
        gate.run_vlan_traffic("not-a-token", 1)


def test_management_snapshot_comparison_is_exact() -> None:
    before = {
        "ports": ["eth0", "wifi0", "wlan0"],
        "br0_state": "up",
        "br0_mtu": "1500",
        "ip_forward": "0",
        "persist": "ro",
        "mtd_table": "a" * 64,
        "route_table": "b" * 64,
        "vlan_config": "c" * 64,
    }
    assert gate.immutable_management(before) == gate.immutable_management(dict(before))
    changed = dict(before)
    changed["ports"] = ["eth0", "eth0.4090", "wifi0", "wlan0"]
    assert gate.immutable_management(before) != gate.immutable_management(changed)


def test_router_rollback_is_ram_only_and_does_not_touch_br0() -> None:
    script = gate.rollback_script().decode("ascii")
    assert "/run/openmitrastar/vlan4090" in script
    assert "delete eth0.4090" in script
    for forbidden in (
        "brctl addif", "brctl delif", "bridge vlan", "/persist", "/etc/",
        "flash_erase", "mtd_debug", "nandwrite", "fw_setenv", "reboot",
    ):
        assert forbidden not in script


def test_gate_contract_has_required_exclusions_and_no_flash_path() -> None:
    source = GATE.read_text(encoding="utf-8")
    for marker in (
        "run_f301_sequential_dual_radio_soak",
        "run_f301_multicast_igmp_physical",
        "f301_dfs",
        "f301_vlan_gate",
        "f301-vlan4090",
        "OPENMITRASTAR_F301_VLAN4090_PHYSICAL",
        "router_local_watchdog",
        "controller_adapter_watchdog",
        "uart_guard",
        "all_three_required_before_mutation",
        "StrictHostKeyChecking=yes",
    ):
        assert marker in source
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv", "ATGU", "tftpboot"):
        assert forbidden not in source


def test_endpoint_is_pinned_to_linux_8021q_not_qdrv_vlan() -> None:
    source = ENDPOINT_SOURCE.read_text(encoding="utf-8")
    assert "ADD_VLAN_CMD" in source
    assert "DEL_VLAN_CMD" in source
    assert "vlan-id-must-be-4090" in source
    assert "LYOKO-VLAN1" in source
    for forbidden in ("qtn_vlan_info", "vlan_enabled", "switch_vlan", "brctl", "/dev/mtd"):
        assert forbidden not in source
    manifest = json.loads((gate.ENDPOINT_MANIFEST).read_text(encoding="ascii"))
    assert manifest["artifact"]["architecture"] == "ARC700 v4 ABI"
    assert manifest["artifact"]["reproducible_two_builds"] is True
    assert manifest["contract"]["bridge_mutation"] is False
    assert manifest["contract"]["mtd_writes"] is False


def test_build_script_uses_noatomic_static_arc700_contract() -> None:
    source = BUILD_SCRIPT.read_text(encoding="utf-8")
    for marker in ("-mno-atomic", "-static", "ARC700, v4 ABI", "reproducible_two_builds"):
        assert marker in source


@pytest.mark.parametrize("script", [CONTROLLER, UART_GUARD])
def test_powershell_helpers_parse(script: Path) -> None:
    escaped = str(script).replace("'", "''")
    proc = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            f"[void][ScriptBlock]::Create((Get-Content -Raw -LiteralPath '{escaped}'))",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_controller_helper_has_snapshot_watchdog_and_exact_restore() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")
    for marker in (
        "Get-NetAdapterAdvancedProperty",
        "Set-NetAdapterAdvancedProperty",
        "controller-watchdog-ready.json",
        "controller-watchdog-trigger",
        "Remove-NetIPAddress",
        "Original VLAN registry value",
        "This gate is pinned to isolated VLAN 4090",
        "ipv4_restored_exactly",
        "existing_vlan_disabled",
    ):
        assert marker in source
    assert "Set-NetIPInterface" not in source
    assert "Set-DnsClient" not in source


def test_uart_guard_verifies_sysrq_path_before_ready() -> None:
    source = UART_GUARD.read_text(encoding="utf-8")
    ready_check = source.index("Send-MagicSysRq 'h'")
    ready_write = source.index("sysrq_help_verified = $true")
    assert ready_check < ready_write
    for marker in (
        "DtrEnable = $false", "RtsEnable = $false", "uart-guard-trigger",
        "Send-MagicSysRq 'b'", "RECOVERY_REBOOT_CONFIRMED",
    ):
        assert marker in source
    for forbidden in ("ATGU", "tftpboot", "mtd", "CredentialPath", "Password:"):
        assert forbidden not in source
