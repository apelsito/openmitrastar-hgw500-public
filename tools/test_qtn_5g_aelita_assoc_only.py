#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

import run_qtn_5g_aelita_assoc_only as gate


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_5g_aelita_assoc_only.py"


def test_aelita_assoc_only_dry_run_is_network_free() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    marker = "OMQTN5G_AELITA_ASSOC_ONLY_DRY_RUN_PASS=1"
    assert marker in proc.stdout
    payload = json.loads(proc.stdout[: proc.stdout.index(marker)])
    assert payload["oracle"] == "AELITA@192.168.1.63"
    assert payload["network_changed_now"] is False
    assert payload["policy"]["association_only"] is True
    assert payload["policy"]["router_mutations"] is False
    assert payload["policy"]["serial_uart"] is False
    assert payload["policy"]["flash"] is False
    assert payload["policy"]["static_ip"] is False
    assert payload["policy"]["ping"] is False
    assert payload["policy"]["traffic"] is False


def test_aelita_assoc_only_source_is_pinned_and_bounded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        'ORACLE_HOST = "192.168.1.63"',
        'ORACLE_USER = "AELITA"',
        "oracle_rsa_unencrypted",
        "client.load_host_keys",
        "paramiko.RejectPolicy()",
        "this gate is pinned to AELITA@192.168.1.63",
        "run_qtn_5g_assoc_only_oracle.ps1",
        "start_qtn_5g_assoc_only_oracle_task.ps1",
        "restore_wifi_oracle_watchdog.ps1",
        "OPENMITRASTAR_QTN_5G_AELITA_ASSOC_ONLY",
        "OPENMITRASTAR_QTN_5G_ASSOC_ONLY_TASK",
        "PASS_ASSOC_ONLY",
    ):
        assert marker in text
    assert "AutoAddPolicy" not in text


def test_aelita_assoc_only_has_no_router_or_flash_path() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden = (
        "192.168.1.90",
        "com3",
        "flash_erase",
        "mtd_debug",
        "fw_setenv",
        "reboot_boot_ramssh",
        "set-netipinterface",
        "new-netipaddress",
        "ping.exe",
        "curl.exe",
    )
    for needle in forbidden:
        assert needle not in text


def test_aelita_assoc_only_parses_noisy_windows_json() -> None:
    raw = (
        "\ufeff\x1b[?25hignored banner\r\n"
        '{"schema":"openmitrastar.qtn-5g-assoc-only-oracle/v1",'
        '"status":"FAIL_NOT_VISIBLE","phases":{"scan_visible":{"raw":"'
        'Nombre de interfaz : Wi-Fi\x07\\nSSID 1 : MOVISTAR-WIFI6-A348"}}}'
        "\r\nOMQTN5G_ASSOC_ONLY_ORACLE_COMPLETE=1\r\n"
    )
    parsed = gate.parse_oracle_json(raw)
    assert parsed["status"] == "FAIL_NOT_VISIBLE"
    assert "MOVISTAR-WIFI6-A348" in parsed["phases"]["scan_visible"]["raw"]
