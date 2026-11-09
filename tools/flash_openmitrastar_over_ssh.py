#!/usr/bin/env python3
"""Flash an OpenMitraStar webformat image over authorized SSH/root access."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import pathlib
import sys
import time
import warnings

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(client: paramiko.SSHClient, command: str, timeout: int = 30) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "image",
        nargs="?",
        default=str(
            ROOT
            / "versions"
            / "openmitrastar-0.4.4-modern-ui-no-cgi-flash"
            / "build"
            / "openmitrastar-0.4.4-modern-ui-no-cgi-flash_webformat.bin"
        ),
    )
    parser.add_argument("--host", default="192.168.1.1")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=None)
    parser.add_argument("--credentials-file", type=pathlib.Path)
    parser.add_argument("--target", choices=["live", "safety"], default="live")
    parser.add_argument("--remote", default="/tmp/openmitrastar-webformat.bin")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="upload and run chkimage, but do not write flash or reboot",
    )
    parser.add_argument("--no-reboot", action="store_true", help="do not reboot after a complete flash")
    args = parser.parse_args()

    image = pathlib.Path(args.image).resolve()
    if not image.exists():
        raise FileNotFoundError(image)
    local_size = image.stat().st_size
    local_sha = sha256(image)
    if local_size <= 0 or local_size > 7_995_392:
        raise ValueError(f"unexpected image size: {local_size}")

    password = args.password
    if password is None and args.credentials_file is not None:
        for raw in args.credentials_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and ":" in line:
                file_user, password = line.split(":", 1)
                args.user = file_user.strip()
                password = password.strip()
                break
        if password is None:
            raise RuntimeError("credentials file has no user:password entry")
    if password is None:
        password = getpass.getpass(f"{args.user}@{args.host} password: ")

    warnings.filterwarnings("ignore")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    def legacy_transport(sock, **kwargs):
        return paramiko.Transport(sock, strict_kex=False, **kwargs)

    client.connect(
        args.host,
        username=args.user,
        password=password,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
        look_for_keys=False,
        allow_agent=False,
        transport_factory=legacy_transport,
    )

    print(f"connected {args.user}@{args.host}")
    for command in [
        "id",
        "cat /proc/mtd",
        "df -h /tmp /mnt/jffs2 2>/dev/null || df -h",
        "command -v chkimage; command -v call_qcsapi; ls -l /etc/default/FWupgrade.sh 2>/dev/null || true",
    ]:
        rc, out, err = run(client, command)
        print(f"\n$ {command}\n{out}{err}".rstrip())
        if rc != 0 and command == "command -v chkimage; command -v call_qcsapi; ls -l /etc/default/FWupgrade.sh 2>/dev/null || true":
            raise RuntimeError("required flash tooling not available")

    sftp = client.open_sftp()
    print(f"\nupload {image.name} -> {args.remote}")
    sftp.put(str(image), args.remote)
    sftp.close()

    remote_hash_cmd = (
        f"(sha256sum {args.remote} 2>/dev/null || md5sum {args.remote}) | awk '{{print $1}}'"
    )
    rc, out, err = run(client, f"wc -c < {args.remote}; {remote_hash_cmd}")
    print(f"\n$ remote verify\n{out}{err}".rstrip())
    if rc != 0:
        raise RuntimeError("remote verification failed")
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines or int(lines[0]) != local_size:
        raise RuntimeError(f"remote size mismatch, expected {local_size}, got {lines[:1]}")
    print(f"local sha256 {local_sha}")

    rc, out, err = run(
        client,
        f"chkimage -A arc -O linux -T kernel -v {args.remote}",
        timeout=30,
    )
    print(f"\n$ chkimage\n{out}{err}".rstrip())
    if rc != 0:
        raise RuntimeError("chkimage rejected image")

    if args.verify_only:
        print("\nverification complete; flash was not modified")
        client.close()
        return 0

    flash_cmd = (
        f"rm -f /tmp/result_upgrade /tmp/openmitrastar-fwupgrade.log; "
        f"sh /etc/default/FWupgrade.sh {args.remote} {args.target}; "
        f"rc=$?; echo RC=$rc; cat /tmp/result_upgrade 2>/dev/null; "
        f"cat /tmp/openmitrastar-fwupgrade.log 2>/dev/null; exit $rc"
    )
    rc, out, err = run(client, flash_cmd, timeout=180)
    print(f"\n$ flash {args.target}\n{out}{err}".rstrip())
    if rc != 0 or "complete" not in out:
        raise RuntimeError("flash backend did not report complete")

    if not args.no_reboot:
        print("\nflash complete; reboot scheduled")
        run(client, "sync; (sleep 2; reboot -d 6 >/dev/null 2>&1 &) >/dev/null 2>&1", timeout=5)
        time.sleep(1)

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
