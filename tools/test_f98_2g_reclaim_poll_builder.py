#!/usr/bin/env python3
from pathlib import Path
import base64
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f98_2g_reclaim_poll_from_f97.py"
WRAPPER = ROOT / "tools/arm_f98_2g_reclaim_poll_flash.ps1"
MONITOR = ROOT / "tools/monitor_f98_flash_then_2g_gate.ps1"
F97_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f97-emac-periodic-rxrestart-from-f96/build"
F97_BASE = "openmitrastar-linux510-q3-persistent-f97-emac-periodic-rxrestart-from-f96-LZMA-OFFLINE-NO-FLASH"
F98_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f98-2g-reclaim-poll-from-f97/build"
F98_BASE = "openmitrastar-linux510-q3-persistent-f98-2g-reclaim-poll-from-f97-LZMA-OFFLINE-NO-FLASH"


def test_f98_builder_is_f97_scoped_and_loader_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f97-emac-periodic-rxrestart-from-f96" in text
    assert "q3-persistent-composite-f98-2g-reclaim-poll-from-f97" in text
    assert "radio2g_loader" in text
    assert "radio2g_modules" in text
    assert "unchanged from F97/F96" in text
    assert "radio5_modules" in text
    assert "qdrv" in text
    assert "bridge" in text
    assert "touches_router\": False" in text
    assert "opens_uart\": False" in text
    assert "flash\": False" in text


def test_f98_builder_enables_only_reclaim_poll_not_rate_churn() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "hgw500_tx_reclaim_poll=0" in text
    assert "hgw500_tx_reclaim_poll=1" in text
    assert "hgw500_tx_reclaim_poll=N" in text
    assert "hgw500_tx_reclaim_poll=Y" in text
    assert "MCS7 forced, MCS15/HT40/SGI not reintroduced" in text
    assert "hgw500_force_data_mcs15=1" not in text
    assert "hgw500_force_data_ht40sgi=1" not in text


def test_f98_flash_wrapper_targets_f98_after_f97_by_default() -> None:
    text = WRAPPER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f98-2g-reclaim-poll-from-f97\\build" in text
    assert "OPENMITRASTAR_Q3_F98_2G_RECLAIM_POLL_FROM_F97_MTD4_FLASH_3B0FA8C4" in text
    assert '$ExpectedSha256 = "3b0fa8c4c6b3ee4eac0325a60b4802d0cdd19269b01949a209dbca7ee229c749"' in text
    assert '$ExpectedBytes = "5611802"' in text
    assert '[string]$CurrentLiveCrc32 = "ffc4637c"' in text
    assert "-AllowBlindAutobreak" in text
    assert "-ConsoleRebootAssist" in text
    assert "-SysRqRebootFirst" in text
    assert "monitor_f98_flash_then_2g_gate.ps1" in text
    assert "monitor_pid" in text


def test_f98_monitor_proves_reclaim_poll_before_2g_gate() -> None:
    text = MONITOR.read_text(encoding="ascii")
    assert "openmitrastar.f98-flash-then-2g-reclaim-gate-monitor/v1" in text
    assert "3b0fa8c4c6b3ee4eac0325a60b4802d0cdd19269b01949a209dbca7ee229c749" in text
    assert "RECLAIM_POLL=" in text
    assert "RECLAIM_POLL=Y" in text
    assert "FAIL_F98_RECLAIM_POLL_NOT_ACTIVE" in text
    assert "PASS_F98_FLASH_SSH_RECLAIM_AND_2G_L3" in text
    assert "run_aelita_2g_wpa2_speed_router_probe.py" in text


def test_f98_powershell_files_parse() -> None:
    command = (
        "$paths=@("
        + ",".join(json.dumps(str(path)) for path in (WRAPPER, MONITOR))
        + ");"
        "$e=$null;$t=$null;"
        "foreach($p in $paths){"
        "  $e=$null;$t=$null;"
        "  $src=Get-Content -LiteralPath $p -Raw;"
        "  [System.Management.Automation.Language.Parser]::ParseInput($src,[ref]$t,[ref]$e)|Out-Null;"
        "  if($e.Count){$e|ForEach-Object{$_.ToString()};exit 1}"
        "}"
    )
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )


def test_f98_artifact_preserves_f97_payload_layout() -> None:
    f97_raw = F97_BUILD / f"{F97_BASE}.decompressed.bin"
    f98_raw = F98_BUILD / f"{F98_BASE}.decompressed.bin"
    manifest = json.loads((F98_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert f97_raw.is_file()
    assert f98_raw.is_file()
    source = f97_raw.read_bytes()
    candidate = f98_raw.read_bytes()
    assert len(candidate) == len(source)
    source_start, _source_entries, source_remainder = f71.parse_first_cpio(source)
    candidate_start, _candidate_entries, candidate_remainder = f71.parse_first_cpio(candidate)
    assert candidate_start == source_start == manifest["patch"]["cpio"]["start"]
    assert len(candidate) - len(candidate_remainder) == len(source) - len(source_remainder)
    assert candidate_remainder == source_remainder
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0


def test_f98_artifact_changes_only_loader_entry_and_keeps_modules() -> None:
    f97_raw = (F97_BUILD / f"{F97_BASE}.decompressed.bin").read_bytes()
    f98_raw = (F98_BUILD / f"{F98_BASE}.decompressed.bin").read_bytes()
    _s1, f97_entries, _r1 = f71.parse_first_cpio(f97_raw)
    _s2, f98_entries, _r2 = f71.parse_first_cpio(f98_raw)
    before = {entry.name: entry.data for entry in f97_entries}
    after = {entry.name: entry.data for entry in f98_entries}
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == ["usr/sbin/om-radio-modules"]
    loader = after["usr/sbin/om-radio-modules"].decode("ascii")
    assert "hgw500_tx_reclaim_poll=1" in loader
    assert "hgw500_tx_reclaim_poll=Y" in loader
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_force_data_mcs15=0" in loader
    assert "hgw500_force_data_ht40sgi=1" not in loader
    for module in (
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko",
    ):
        assert before[module] == after[module]
