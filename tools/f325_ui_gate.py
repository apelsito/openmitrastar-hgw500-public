"""Exact F325 installed files, unchanged F321 UI and unarmed provider baseline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

import f325_execution_contract as contract
import post_flash_f321_ui_gate as previous


def expected_identity() -> tuple[dict, dict]:
    contract.validate_sealed_inputs()
    files, bundle = previous.expected_identity()
    inventory = contract.read_json(Path(contract.F325["directory"]) / "rootfs-inventory.json")
    files.update({"/" + name: row["sha256"] for name, row in inventory["expected_changes"].items()})
    return files, bundle


def verify_baseline(text: str) -> dict:
    match = re.search(r"(?ms)^OMF325_BASELINE_BEGIN\r?\n(.*?)^OMF325_BASELINE_END", text)
    if not match:
        raise ValueError("missing F325 baseline")
    values = {}
    for line in match[1].splitlines():
        if "=" not in line:
            raise ValueError("invalid baseline field")
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError("duplicate baseline field")
        values[key] = value
    expected = {"lifecycle": "f325-single-boot-reset-required", "once_phase": "0", "hardware_dirty": "0",
                "reboot_required": "0", "shadow_arm": "0", "configured": "0", "polling": "0",
                "poll_runs": "0", "mmio_writes": "0", "callback_invocations": "0", "backend_ready": "0",
                "sample_window_ms": "20000", "channel": "36", "bandwidth": "80"}
    if values != expected:
        raise ValueError("F325 is not pristine/unarmed")
    return {"unarmed": True, "mmio_writes": 0, "callbacks": 0, "hardware_dirty": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    files, bundle = expected_identity()
    if not args.execute:
        print(json.dumps({"status": "PASS_OFFLINE_UI_PLAN", "files": len(files), "hardware_actions": False}))
        return 0
    if args.output_dir is None:
        parser.error("new output directory required")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fields = "lifecycle|once_phase|hardware_dirty|reboot_required|shadow_arm|configured|polling|poll_runs|mmio_writes|callback_invocations|backend_ready|sample_window_ms|channel|bandwidth"
    script = previous.ssh_script(files) + "echo OMF325_BASELINE_BEGIN\n" + (
        "awk -F= '$1 ~ /^(" + fields + ")$/ {print}' /proc/openmitrastar_radar_f315/status\n"
        "echo OMF325_BASELINE_END\n")
    known = Path(contract.F325["directory"]) / contract.F325["known_hosts"]
    command = [r"C:\Windows\System32\OpenSSH\ssh.exe", "-i", str(Path.home() / ".ssh/id_ed25519"),
               "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "UserKnownHostsFile=" + str(known), "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR",
               "root@" + contract.HOST, "sh", "-s"]
    result = {"schema": "openmitrastar.f325-unarmed-ui-gate/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "FAIL_F325_UI_BASELINE", "radio_mutation": False, "flash": False}
    try:
        proc = subprocess.run(command, input=script.encode(), capture_output=True, timeout=35, check=False)
        if proc.returncode or proc.stderr.strip():
            raise ValueError("pinned SSH failed")
        text = proc.stdout.decode("utf-8", "strict")
        result["files"] = previous.verify_ssh(text, files, bundle)
        result["baseline"] = verify_baseline(text)
        result["http"] = previous.verify_http(bundle)
        result["status"] = "PASS_F325_UI_HTTP_API"
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result["error_type"] = type(error).__name__
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS_F325_UI_HTTP_API" else 1


if __name__ == "__main__":
    raise SystemExit(main())
