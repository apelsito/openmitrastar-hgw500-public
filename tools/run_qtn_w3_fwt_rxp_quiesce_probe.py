#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin"
IMAGE_SHA = "5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358"
PRODUCT = ROOT / "work/tftp/omvl/linux510-product-rootfs-ram-equivalent-v1-RAM-ONLY.bin"
PRODUCT_SHA = "08503e290dbe84ed7d6b5d0fdbcedc4087b2fb9f26b69db418d4f2e971500255"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-v89-radiohw-fwt-rxpquiesce-20260818-0315"
MANIFEST = ROOT / "work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_RXPQUIESCE_SIGNED_ARTIFACT.json"
CLOSED_GATE = ROOT / "work/mission-state/w3-offline/W3_FWT_RXP_QUIESCE_PROBE_GATE.env"
APPROVED_GATE = ROOT / "work/mission-state/w3-offline/W3_FWT_RXP_QUIESCE_PROBE_GATE.approved.env"
REMOTE = ROOT / "tools/qtn_w3_fwt_rxp_quiesce_probe_remote.sh"
RAM_INSMOD = ROOT / "outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
RAM_INSMOD_SHA = "8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6"
RELEASE = "5.10.260-openmitrastar-radiohw"
ACK = "OPENMITRASTAR_QTN_W3_FWT_RXP_QUIESCE_PROBE"
REMOTE_ROOT = "/tmp/w3-qtn-fwt-rxp"
REMOTE_GATE = "/tmp/W3_FWT_RXP_QUIESCE_PROBE_GATE.env"
REMOTE_SCRIPT = "/tmp/qtn_w3_fwt_rxp_quiesce_probe_remote.sh"
REMOTE_RESULT = "/tmp/W3_FWT_RXP_QUIESCE_PROBE.worker.log"
LOGICAL_DATE = "20260818"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], timeout: int = 120) -> None:
    subprocess.run(command, cwd=ROOT, check=True, timeout=timeout)


def values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )


def ssh_capture(host: str, command: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", command, "--host", host, "--timeout", str(timeout)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout + 10,
    )


def restore_product(host: str) -> None:
    run([
        "pwsh.exe", "-NoProfile", "-File", "tools/run_product_rootfs_ram_candidate.ps1",
        "-ExecuteRam", "-AckRamOnly", "OPENMITRASTAR_PRODUCT_ROOTFS_RAM_ONLY",
    ], 600)
    run([
        sys.executable, "tools/ramssh_exec.py",
        "uname -r;echo W3_PRODUCT_RESTORE_SSH_PASS", "--host", host,
    ], 60)


def wait_for_worker(host: str, timeout: int = 90) -> str:
    deadline = time.monotonic() + timeout
    last_output = ""
    while time.monotonic() < deadline:
        result = ssh_capture(
            host,
            f"test -f {REMOTE_RESULT} && cat {REMOTE_RESULT} || true",
        )
        if result.stdout:
            last_output = result.stdout
        if "W3_FWT_RXP_QUIESCE_PROBE_PASS" in last_output:
            print(last_output, end="" if last_output.endswith("\n") else "\n")
            return last_output
        if "W3_FWT_RXP_STOP" in last_output:
            raise RuntimeError(last_output)
        time.sleep(2)
    raise TimeoutError(f"detached RXP worker did not finish: {last_output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--port", default="COM3")
    args = parser.parse_args()

    if sha(IMAGE) != IMAGE_SHA or sha(PRODUCT) != PRODUCT_SHA or sha(RAM_INSMOD) != RAM_INSMOD_SHA:
        raise SystemExit("pinned input mismatch")
    run([sys.executable, "tools/qtn_w3_artifact_gate.py", "--manifest", str(MANIFEST), "--verify"])
    gate = APPROVED_GATE if args.execute else CLOSED_GATE
    approved = values(gate)["W3_FWT_RXP_QUIESCE_PROBE_APPROVED"]
    print({
        "mode": "execute" if args.execute else "dry-run",
        "approved": approved,
        "logical_date": "2026-08-18",
        "single_variable": "EMAC0 RXP_CTRL 0xe8000304 -> 0 -> exact snapshot",
        "detached_worker": True,
        "fwt_table_access": False,
        "other_mmio_writes": False,
        "flash": False,
        "product_restore": True,
    })
    if not args.execute:
        print("W3_FWT_RXP_QUIESCE_PROBE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK or approved != "1":
        raise SystemExit("probe gate not approved")

    tftp = None
    capture = None
    try:
        tftp = subprocess.Popen([
            sys.executable, "tools/tftp_serve_once.py", "--root", str(IMAGE.parent),
            "--bind", "0.0.0.0", "--port", "69", "--timeout", "480", "--once",
        ], cwd=ROOT)
        time.sleep(0.6)
        run([
            "pwsh.exe", "-NoProfile", "-File", "tools/reboot_boot_ramssh.ps1",
            "-Port", args.port, "-Filename", IMAGE.name, "-ServerIp", args.server_ip,
            "-ClientIp", args.host, "-TimeoutSeconds", "480",
            "-EntropyPromptPattern", "(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED",
            "-EntropyOkPattern", "OMPRODUCT_SERIAL_ENTROPY_OK bits=256",
            "-ReadyPattern", "OMPRODUCT_READY state=(ready|degraded)",
        ], 600)
        capture = subprocess.Popen([
            "pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
            "-Port", args.port, "-Seconds", "180", "-OutputDirectory",
            str(ROOT / "outputs/uart-live" / f"w3-fwt-rxp-{LOGICAL_DATE}-{time.strftime('%H%M%S')}"),
        ], cwd=ROOT)
        run([
            sys.executable, "tools/ramssh_exec.py",
            f"rm -rf {REMOTE_ROOT};mkdir -p {REMOTE_ROOT};rm -f {REMOTE_RESULT}",
            "--host", args.host,
        ])
        module_root = ARTIFACT / "rootfs/lib/modules" / RELEASE / "extra/quantenna/platform/ruby"
        support = module_root / "qtn_platform_support.ko"
        board = module_root / "board_compat.ko"
        for source, destination, mode in (
            (support, f"{REMOTE_ROOT}/qtn_platform_support.ko", "0600"),
            (board, f"{REMOTE_ROOT}/board_compat.ko", "0600"),
            (RAM_INSMOD, f"{REMOTE_ROOT}/ram_insmod", "0700"),
            (gate, REMOTE_GATE, "0600"),
            (REMOTE, REMOTE_SCRIPT, "0700"),
        ):
            run([
                sys.executable, "tools/ramssh_upload.py", str(source), destination,
                "--host", args.host, "--mode", mode,
            ])
        run([
            sys.executable, "tools/ramssh_exec.py",
            f"sed -i 's/\\r$//' {REMOTE_GATE} {REMOTE_SCRIPT};"
            f"sh {REMOTE_SCRIPT} {REMOTE_ROOT} {REMOTE_GATE}",
            "--host", args.host, "--timeout", "30",
        ], 45)
        wait_for_worker(args.host)
        if capture.poll() is None:
            capture.terminate()
            capture = None
        if tftp.poll() is None:
            tftp.terminate()
            tftp = None
        restore_product(args.host)
    except Exception:
        if capture is not None and capture.poll() is None:
            capture.terminate()
        if tftp is not None and tftp.poll() is None:
            tftp.terminate()
        try:
            run(["pwsh.exe", "-NoProfile", "-File", "tools/uart_sysrq_reboot.ps1", "-Port", args.port], 60)
        except Exception:
            pass
        restore_product(args.host)
        raise
    finally:
        if capture is not None and capture.poll() is None:
            capture.terminate()
        if tftp is not None and tftp.poll() is None:
            tftp.terminate()

    print("W3_FWT_RXP_QUIESCE_PROBE_PASS=1 product_restore=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
