#!/usr/bin/env python3
"""Real process/lock tests with synthetic IDs; no UART, SSH or promoter execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["f319_uart_guard.ps1", "capture_topaz_uart_resilient.ps1", "promote_f319_mtd4_direct.ps1",
           "rollback_f319_to_f314_mtd4.ps1", "run_f319_spi_owner_probe.ps1", "test_f319_guard_behavior.ps1",
           "f319_flash_fallback.py", "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py",
           "tftp_serve_once.py",
           "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1",
           "reboot_to_topaz_prompt_sysrq.ps1", "run_f319_bootbase_recovery_rehearsal.ps1", "f319_recovery_guard.ps1"]


def main():
    runs = []
    for engine_name in ("powershell.exe", "pwsh.exe"):
        engine = shutil.which(engine_name)
        if not engine: raise RuntimeError(f"Required test engine missing: {engine_name}")
        for action in ("leases", "captures", "transport"):
            with tempfile.TemporaryDirectory(prefix="f319-synthetic-guards-") as temporary:
                argv = [engine, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(ROOT / "tools/test_f319_guard_behavior.ps1"), "-Action", action, "-Scope", temporary,
                        "-FakeIdentity", "OFFLINE_F319_" + uuid.uuid4().hex]
                process = subprocess.run(argv, capture_output=True, text=True, timeout=60)
                if process.returncode: raise RuntimeError(f"{engine_name}/{action} failed:\n{process.stdout}\n{process.stderr}")
                result = json.loads(process.stdout)
                if result["status"] != "PASS" or any(case["status"] != "PASS" for case in result["cases"]):
                    raise RuntimeError("Offline test matrix incomplete")
                runs.append({"engine": engine_name, "matrix": action, **result})
                print(f"{engine_name}/{action}: {len(result['cases'])} PASS", flush=True)
    report = {"schema": "openmitrastar.f319-offline-guard-behavior/v1", "status": "PASS",
              "created_utc": datetime.now(timezone.utc).isoformat(), "runs": runs,
              "sources": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest() for name in SOURCES},
              "hardware_actions": False, "serial_enumeration": False, "ssh": False, "flash": False,
              "test_scope": "synthetic IDs and temporary files; actual Windows mutex/file sharing and child processes",
              "physical_binding": "NOT_RUN", "f319_runtime": "NOT_RUN"}
    path = ROOT / "outputs/preflight" / ("f319-offline-guards-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")) / "result.json"
    path.parent.mkdir(parents=True, exist_ok=False)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"status": "PASS", "tests": sum(len(row["cases"]) for row in runs), "report": str(path)}))


if __name__ == "__main__": main()
