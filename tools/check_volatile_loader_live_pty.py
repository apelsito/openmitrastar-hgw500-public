#!/usr/bin/env python3
"""Read-only ABI check for the volatile loader against the running OEM kernel."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.97")
    args = parser.parse_args()
    undefined = ROOT / "work/volatile-loader/out/module-undefined-symbols.txt"
    symbols = [line.split()[-1] for line in undefined.read_text().splitlines() if line.strip()]
    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    proc = PtyProcess.spawn([
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@{args.router}",
    ], cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)
    pattern = "|".join(f"^{name}$" for name in symbols)
    out = command(proc,
        "echo UNAME=$(uname -r); echo MACHINE=$(uname -m); "
        "echo MEM_BEGIN; cat /proc/meminfo; echo MEM_END; "
        "echo SYMBOLS_BEGIN; awk '{print $3}' /proc/kallsyms | "
        f"grep -E '{pattern}'; echo SYMBOLS_END; "
        "echo MODULES_BEGIN; cat /proc/modules; echo MODULES_END",
        "__OMVL_LIVE_ABI__", 40)
    found = set(out.split("SYMBOLS_BEGIN", 1)[1].split("SYMBOLS_END", 1)[0].replace("\r", "").split())
    missing = sorted(set(symbols) - found)
    print(out)
    print(f"OMVL_LIVE_SYMBOLS total={len(symbols)} found={len(found)} missing={len(missing)}")
    if missing:
        print("MISSING=" + ",".join(missing))
        return 1
    print("OMVL_LIVE_ABI_PASS")
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
