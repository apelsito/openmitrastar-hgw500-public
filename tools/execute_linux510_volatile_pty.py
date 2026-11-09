#!/usr/bin/env python3
"""One-shot RAM-only Linux 5.10 handoff with exact preflight and SSH proof."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import socket
import subprocess
import time

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


ARTIFACTS = ROOT / "work/tftp/omvl"
MODULE = ARTIFACTS / "openmitrastar_volatile_loader.ko"
IMAGE = ARTIFACTS / "linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage"
EXPECTED_MODULE_SHA256 = "373e255604b70ee16686f8eabe0967391b2282eab8a7326acf918c78cc205890"
EXPECTED_IMAGE_SHA256 = "e076e7af8a8cbae683fff25769699c19c0345325282139a71300157697f7a0f8"
EXPECTED_TOKEN = "08e69a59"
REPORT_RE = re.compile(r"OMVL_PREFLIGHT_PASS generation=(\d+) token=([0-9a-f]{8}).*execute=1")
INSTANCE_LOCK_PORT = 39461


def support_password() -> str:
    for raw in (ROOT / "Accesos.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.lower().startswith("support-shell:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    raise RuntimeError("support-shell credential is missing from Accesos.txt")


def open_oem_root_pty(host: str) -> PtyProcess:
    user, password = credentials()
    support = support_password()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    proc = PtyProcess.spawn([
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@{host}",
    ], cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, ">", 20)
    proc.write("sh\r\n")
    read_until(proc, "password:", 10)
    proc.write(support + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)
    root_probe = command(proc, "id", "__OMVL_ROOT__", 15)
    if "uid=0(root)" not in root_probe:
        raise RuntimeError("OEM support shell did not yield uid=0")
    return proc


def acquire_instance_lock() -> socket.socket:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", INSTANCE_LOCK_PORT))
        lock.listen(1)
    except OSError as exc:
        lock.close()
        raise RuntimeError(
            "another volatile Linux executor is already running") from exc
    return lock


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wait_for_ssh_banner(host: str, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, 22), timeout=1) as sock:
                sock.settimeout(2)
                banner = sock.recv(256).decode("ascii", "replace").strip()
                if banner.startswith("SSH-"):
                    return banner
                last_error = f"unexpected banner {banner!r}"
        except OSError as exc:
            last_error = str(exc)
        time.sleep(1)
    raise TimeoutError(f"no SSH banner from {host}: {last_error}")


def ssh_banner(host: str, timeout: float = 1.0) -> str | None:
    try:
        with socket.create_connection((host, 22), timeout=timeout) as sock:
            sock.settimeout(timeout)
            banner = sock.recv(256).decode("ascii", "replace").strip()
            return banner if banner.startswith("SSH-") else None
    except OSError:
        return None


def wait_for_volatile_outcome(oem_host: str, target_host: str, started: float,
                              timeout: int) -> tuple[str, str, float]:
    """Return the first SSH endpoint that comes back after the RAM handoff."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        target_banner = ssh_banner(target_host, 0.35)
        if target_banner:
            return "linux510", target_banner, time.monotonic() - started
        oem_banner = ssh_banner(oem_host, 0.35)
        if oem_banner:
            return "oem", oem_banner, time.monotonic() - started
        time.sleep(0.15)
    raise TimeoutError(
        f"neither Linux 5.10 ({target_host}) nor OEM ({oem_host}) returned")


def read_oem_uptime(host: str) -> float:
    """Read OEM uptime over the legacy Dropbear PTY without exposing secrets."""
    proc = open_oem_root_pty(host)
    output = command(proc, "cat /proc/uptime", "__OMVL_UPTIME__", 20)
    proc.write("exit\r\n")
    match = re.search(r"(?:^|\s)(\d+\.\d+)\s+\d+\.\d+", output)
    if not match:
        raise RuntimeError("could not parse OEM uptime")
    return float(match.group(1))


def prove_linux510(host: str) -> str:
    script = (
        "set -eu; key=/home/user/openmitrastar-ramssh-keys/client_ed25519; "
        "test -s $key; ssh -i $key -o BatchMode=yes -o ConnectTimeout=8 "
        "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"root@{host} 'echo RAMSSH_PROOF_BEGIN; uname -a; cat /proc/cpuinfo; "
        "cat /proc/cmdline; cat /proc/meminfo; "
        "ifconfig -a; route -n; cat /proc/interrupts; "
        "echo RAMSSH_PROOF_END'"
    )
    completed = subprocess.run([
        "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e",
        "bash", "--noprofile", "--norc", "-lc", script,
    ], cwd=ROOT, text=True, capture_output=True, timeout=45)
    output = completed.stdout + completed.stderr
    if completed.returncode or "RAMSSH_PROOF_BEGIN" not in output or \
            "5.10.260-openmitrastar-ramssh" not in output or \
            "RAMSSH_PROOF_END" not in output:
        raise RuntimeError("Linux 5.10 SSH proof failed:\n" + output)
    return output


def main() -> int:
    instance_lock = acquire_instance_lock()
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.97")
    parser.add_argument("--target", default="192.168.1.200")
    parser.add_argument("--tftp-host", default="192.168.1.43")
    parser.add_argument("--boot-timeout", type=int, default=120)
    parser.add_argument("--trace-target", type=int, default=0)
    parser.add_argument("--diagnostic-watchdog", action="store_true",
                        help="measure an OEM watchdog return instead of failing")
    parser.add_argument("--calibrate-watchdog", action="store_true",
                        help="read a temporary range-11 counter and do not jump")
    parser.add_argument("--calibrate-oem-reboot", action="store_true",
                        help="measure Bootbase-to-OEM uptime offset")
    args = parser.parse_args()

    if digest(MODULE, "sha256") != EXPECTED_MODULE_SHA256:
        raise RuntimeError("module hash does not match audited quiesce build")
    if digest(IMAGE, "sha256") != EXPECTED_IMAGE_SHA256:
        raise RuntimeError("uImage hash does not match pinned RAMSSH image")

    proc = open_oem_root_pty(args.router)

    if args.calibrate_oem_reboot:
        reboot_started = time.monotonic()
        proc.write("reboot\r\n")
        time.sleep(2)
        while ssh_banner(args.router, 0.3):
            time.sleep(0.2)
        banner = wait_for_ssh_banner(args.router, args.boot_timeout)
        uptime = read_oem_uptime(args.router)
        sampled = time.monotonic() - reboot_started
        offset = sampled - uptime
        print(f"OMVL_OEM_REBOOT_CAL_PASS banner={banner} "
              f"sample_elapsed={sampled:.3f} oem_uptime={uptime:.3f} "
              f"pre_uptime_offset={offset:.3f} FLASH_WRITES=0")
        return 0

    module_md5 = digest(MODULE, "md5")
    transfer = command(proc,
        "rm -f /tmp/openmitrastar_volatile_loader.ko; "
        f"tftp -g -r {MODULE.name} -l /tmp/{MODULE.name} {args.tftp_host}; "
        "echo MODULE_TFTP_RC=$?; wc -c /tmp/openmitrastar_volatile_loader.ko; "
        "md5sum /tmp/openmitrastar_volatile_loader.ko",
        "__OMVL_EXEC_TRANSFER__", 120)
    print(transfer)
    if "MODULE_TFTP_RC=0" not in transfer or str(MODULE.stat().st_size) not in transfer or \
            module_md5 not in transfer.lower():
        raise RuntimeError("module transfer verification failed")

    loaded = command(proc,
        "rmmod openmitrastar_volatile_loader 2>/dev/null || true; "
        "insmod /tmp/openmitrastar_volatile_loader.ko allow_execute=1 "
        f"confirm_dma_quiesced=1 trace_target={args.trace_target}; echo INSMOD_RC=$?; "
        "minor=$(awk '$2==\"openmitrastar-volatile-loader\" {print $1}' /proc/misc); "
        "test -n \"$minor\"; rm -f /dev/openmitrastar-volatile-loader; "
        "mknod /dev/openmitrastar-volatile-loader c 10 $minor; "
        "echo 'OMVL:RESET' > /dev/openmitrastar-volatile-loader; "
        "echo RESET_RC=$?; dmesg | tail -8",
        "__OMVL_EXEC_LOADED__", 60)
    print(loaded)
    if "INSMOD_RC=0" not in loaded or "RESET_RC=0" not in loaded or \
            "execute=1 dma_quiesced=1" not in loaded:
        raise RuntimeError("execution-gated module load failed")

    if args.calibrate_watchdog:
        calibration = command(proc,
            "echo -n 'OMVL:WDT-CAL' > /dev/openmitrastar-volatile-loader; "
            "echo WDT_CAL_RC=$?; dmesg | tail -4",
            "__OMVL_WDT_CAL__", 20)
        print(calibration)
        if "WDT_CAL_RC=0" not in calibration or \
                "OMVL_WDT_CAL_PASS requested=11" not in calibration or \
                "restored=0000000f" not in calibration:
            raise RuntimeError("watchdog calibration failed")
        print("OMVL_WDT_CALIBRATION_COMPLETE FLASH_WRITES=0 NO_JUMP=1")
        return 0

    image_md5 = digest(IMAGE, "md5")
    staged = command(proc,
        "image_rc=1; for image_try in 1 2 3; do "
        f"rm -f /tmp/{IMAGE.name}; "
        f"if tftp -g -r {IMAGE.name} -l /tmp/{IMAGE.name} {args.tftp_host}; "
        "then image_rc=0; break; fi; sleep 1; done; "
        "echo IMAGE_TFTP_RC=$image_rc; "
        f"wc -c /tmp/{IMAGE.name}; md5sum /tmp/{IMAGE.name}; "
        f"cat /tmp/{IMAGE.name} > /dev/openmitrastar-volatile-loader; "
        "echo IMAGE_STAGE_RC=$?; "
        "echo 'OMVL:PREFLIGHT' > /dev/openmitrastar-volatile-loader; "
        "echo PREFLIGHT_RC=$?; dmesg | tail -12",
        "__OMVL_EXEC_PREFLIGHT__", 300)
    print(staged)
    preflight_log = ROOT / "outputs/volatile-execute-last-preflight.log"
    preflight_log.parent.mkdir(parents=True, exist_ok=True)
    preflight_log.write_text(staged, encoding="utf-8")
    match = REPORT_RE.search(staged)
    required = ["IMAGE_TFTP_RC=0", "IMAGE_STAGE_RC=0", "PREFLIGHT_RC=0",
                str(IMAGE.stat().st_size), image_md5, "image=3119872",
                "payload=3119808", "load=8493a000", "entry=849ce000",
                "end=84c33ac0", "hcrc=c1a29886", "dcrc=5885d5ba",
                "overlap=1", "segments=381"]
    if not match or any(value not in staged for value in required):
        raise RuntimeError("exact hardware preflight failed")
    generation = int(match.group(1))
    token = match.group(2)
    if token != EXPECTED_TOKEN:
        raise RuntimeError(f"unexpected execute token {token}")

    execute = f"OMVL:EXECUTE:{generation:08x}:{token}:VOLATILE-JUMP"
    print(f"OMVL_EXECUTE_ARMED generation={generation} token={token} FLASH_WRITES=0")
    # A successful write never returns: the module disables IRQs/bus masters and
    # transfers control to the trampoline.  If it does return, capture the exact
    # errno and kernel log instead of falsely waiting for the new SSH endpoint.
    jump_started = time.monotonic()
    proc.write(
        f"echo -n '{execute}' > /dev/openmitrastar-volatile-loader; "
        "rc=$?; echo OMVL_EXECUTE_RETURNED_RC=$rc; dmesg | tail -12; "
        "echo __OMVL_EXECUTE_RETURNED__\r\n"
    )
    # winpty.read() can block forever when the remote kernel tears the PTY down.
    # The endpoint transition is the authoritative non-returning-jump signal.
    time.sleep(1)
    if ssh_banner(args.router, 2):
        raise RuntimeError(
            "OEM SSH remained reachable after execute; handoff was not observed"
        )
    print("OMVL_OEM_SSH_DOWN_PASS")
    outcome, banner, elapsed = wait_for_volatile_outcome(
        args.router, args.target, jump_started, args.boot_timeout)
    print(f"OMVL_VOLATILE_OUTCOME endpoint={outcome} elapsed={elapsed:.3f} "
          f"banner={banner}")
    if outcome == "oem":
        if args.diagnostic_watchdog:
            print("OMVL_WATCHDOG_DIAGNOSTIC_PASS FLASH_WRITES=0")
            return 3
        raise RuntimeError(
            f"OEM returned after {elapsed:.3f}s before Linux 5.10 SSH")
    print(f"RAMSSH_BANNER_PASS {banner}")
    proof = prove_linux510(args.target)
    print(proof)
    print("OMVL_LINUX510_VOLATILE_BOOT_PASS FLASH_WRITES=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
