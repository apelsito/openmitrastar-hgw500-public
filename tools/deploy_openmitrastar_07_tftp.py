#!/usr/bin/env python3
"""Transfer and install the validated 0.7 image over the authorized LAN."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402

IMAGE = ROOT / "work" / "tftp" / "openmitrastar-0.7-radio-control.bin"
REMOTE = "/tmp/openmitrastar-0.7.bin"
HOST = "192.168.1.90"
TFTP_HOST = "192.168.1.43"


def credentials() -> tuple[str, str]:
    for raw in (ROOT / "Accesos.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and ":" in line:
            user, password = line.split(":", 1)
            return user.strip(), password.strip()
    raise RuntimeError("No usable SSH credential found")


def run(client: paramiko.SSHClient, command: str, timeout: int = 60) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    return stdout.channel.recv_exit_status(), output


def main() -> int:
    expected_size = IMAGE.stat().st_size
    expected_md5 = hashlib.md5(IMAGE.read_bytes()).hexdigest()
    user, password = credentials()

    warnings.filterwarnings("ignore")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    def legacy_transport(sock, **kwargs):
        return paramiko.Transport(sock, strict_kex=False, **kwargs)

    client.connect(HOST, username=user, password=password, look_for_keys=False,
                   allow_agent=False, timeout=10, banner_timeout=10, auth_timeout=10,
                   transport_factory=legacy_transport)

    print("connected")
    rc, output = run(
        client,
        f"rm -f {REMOTE}; tftp -g -r {IMAGE.name} -l {REMOTE} {TFTP_HOST}; "
        f"rc=$?; echo TFTP_RC=$rc; wc -c < {REMOTE} 2>/dev/null; md5sum {REMOTE} 2>/dev/null; exit $rc",
        timeout=90,
    )
    print(output.strip())
    if rc != 0:
        raise RuntimeError("TFTP transfer failed")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if str(expected_size) not in lines or not any(line.startswith(expected_md5) for line in lines):
        raise RuntimeError("remote size or MD5 mismatch")

    rc, output = run(client, f"chkimage -A arc -O linux -T kernel -v {REMOTE}", timeout=30)
    print(output.strip())
    if rc != 0:
        raise RuntimeError("chkimage rejected image")

    flash = (
        "rm -f /tmp/result_upgrade /tmp/openmitrastar-fwupgrade.log; "
        f"sh /etc/default/FWupgrade.sh {REMOTE} live; "
        "rc=$?; echo FLASH_RC=$rc; cat /tmp/result_upgrade 2>/dev/null; "
        "cat /tmp/openmitrastar-fwupgrade.log 2>/dev/null; exit $rc"
    )
    rc, output = run(client, flash, timeout=180)
    print(output.strip())
    if rc != 0 or "complete" not in output:
        raise RuntimeError("flash did not report complete")

    run(client, "sync; (sleep 2; reboot -d 6 >/dev/null 2>&1 &) >/dev/null 2>&1", timeout=5)
    client.close()
    print("flash complete; reboot scheduled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
