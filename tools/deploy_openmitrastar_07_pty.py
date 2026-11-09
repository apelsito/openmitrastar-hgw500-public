#!/usr/bin/env python3
"""Deploy 0.7 through a real Windows pseudo-console for legacy Dropbear 0.52."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
from winpty import PtyProcess  # noqa: E402

IMAGE = ROOT / "work" / "tftp" / "openmitrastar-0.7-radio-control.bin"
REMOTE = "/tmp/openmitrastar-0.7.bin"


def credentials() -> tuple[str, str]:
    for raw in (ROOT / "Accesos.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and ":" in line:
            user, password = line.split(":", 1)
            return user.strip(), password.strip()
    raise RuntimeError("No usable SSH credential found")


def read_until(proc: PtyProcess, marker: str, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[str] = []
    while time.monotonic() < deadline:
        try:
            chunk = proc.read(4096)
        except EOFError:
            break
        if chunk:
            chunks.append(chunk)
            joined = "".join(chunks)
            if marker.lower() in joined.lower():
                return joined
        else:
            time.sleep(0.05)
    raise TimeoutError(f"marker not received: {marker}")


def command(proc: PtyProcess, shell_command: str, marker: str, timeout: int) -> str:
    proc.write(shell_command + f"; echo {marker}\r\n")
    return read_until(proc, marker, timeout)


def main() -> int:
    user, password = credentials()
    expected_size = IMAGE.stat().st_size
    expected_md5 = hashlib.md5(IMAGE.read_bytes()).hexdigest()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    argv = [
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@192.168.1.90",
    ]
    proc = PtyProcess.spawn(argv, cwd=str(ROOT))
    login = read_until(proc, "password:", 20)
    if "password:" not in login.lower():
        raise RuntimeError("password prompt not received")
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)
    ready = command(proc, "id", "__READY_07__", 20)
    if "uid=0" not in ready:
        raise RuntimeError("root shell not established")
    print("root shell ready")

    transfer = command(
        proc,
        f"rm -f {REMOTE}; tftp -g -r {IMAGE.name} -l {REMOTE} 192.168.1.43; "
        f"rc=$?; echo TFTP_RC=$rc; wc -c < {REMOTE}; md5sum {REMOTE}",
        "__TFTP_07__",
        120,
    )
    print(transfer.strip())
    if "TFTP_RC=0" not in transfer or str(expected_size) not in transfer or expected_md5 not in transfer.lower():
        raise RuntimeError("TFTP transfer verification failed")

    checked = command(proc, f"chkimage -A arc -O linux -T kernel -v {REMOTE}; echo CHECK_RC=$?", "__CHECK_07__", 40)
    print(checked.strip())
    if "CHECK_RC=0" not in checked:
        raise RuntimeError("chkimage rejected image")

    flashed = command(
        proc,
        "rm -f /tmp/result_upgrade /tmp/openmitrastar-fwupgrade.log; "
        f"sh /etc/default/FWupgrade.sh {REMOTE} live; rc=$?; echo FLASH_RC=$rc; "
        "cat /tmp/result_upgrade 2>/dev/null; cat /tmp/openmitrastar-fwupgrade.log 2>/dev/null",
        "__FLASH_07__",
        220,
    )
    print(flashed.strip())
    if "FLASH_RC=0" not in flashed or "complete" not in flashed.lower():
        raise RuntimeError("flash backend did not report complete")

    # Match the stock firmware CGI: keep the delayed reboot independent from
    # the SSH PTY, otherwise closing the legacy Dropbear session can kill it.
    proc.write("sync; (reboot -d 6 >/dev/null 2>&1 &)\r\n")
    print("flash complete; reboot requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
