"""F322 UI identity, public authentication and real HTTP session verification.

Default is a file-only plan. Execute performs pinned SSH reads and a normal
login/logout, never radio or storage configuration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import f322_execution_contract as contract
import post_flash_f321_ui_gate as ui
import verify_f321_authenticated_http as session


def expected_identity() -> tuple[dict, dict]:
    contract.validate_sealed_inputs()
    files, bundle = ui.expected_identity()
    inventory = contract.read_json(Path(contract.F322["directory"]) / "rootfs-inventory.json")
    for path in ("etc/openmitrastar/release", "usr/libexec/openmitrastar/om-api-v1"):
        files["/" + path] = inventory["after"][path]["sha256"]
    return files, bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    files, bundle = expected_identity()
    if not args.execute:
        print(json.dumps({"status": "PASS_OFFLINE_F322_UI_PLAN", "files": files, "hardware_actions_performed": False}))
        return 0
    if not args.output_dir:
        parser.error("new output directory required")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    result = {"schema": "openmitrastar.f322-ui-postflash/v1", "status": "FAIL",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_host": contract.HOST,
              "candidate_sha256": contract.F322["sha256"], "radio_mutation": False, "flash": False}
    try:
        known_hosts = Path(contract.F322["directory"]) / contract.F322["known_hosts"]
        ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
        argv = [ssh, "-i", str(Path.home() / ".ssh/id_ed25519"), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known_hosts),
                "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR", "root@" + contract.HOST, "sh", "-s"]
        proc = ui.run_ssh(argv, ui.ssh_script(files))
        stdout = proc.stdout.decode("utf-8", "replace")
        (args.output_dir / "ssh.stdout.log").write_text(stdout, encoding="utf-8")
        (args.output_dir / "ssh.stderr.log").write_bytes(proc.stderr)
        if proc.returncode:
            raise ValueError("F322 pinned SSH failed")
        result["ssh_checks"] = ui.verify_ssh(stdout, files, bundle)
        result["http_checks"] = ui.verify_http(bundle)
        expected_html = (contract.previous.PACKAGE / "overlay/usr/share/openmitrastar/web/dashboard.html").read_bytes()
        result["authenticated_http"] = session.verify_session(session.private_password(), expected_html, bundle)
        if result["authenticated_http"]["status"] != "PASS_AUTHENTICATED_HTTP_SESSION":
            raise ValueError("F322 authenticated session failed")
        result["status"] = "PASS_F322_UI_AUTHENTICATED_HTTP"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Session helper never returns credentials, cookie values or responses.
        result["error"] = str(error)
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS_F322_UI_AUTHENTICATED_HTTP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
