#!/usr/bin/env python3
"""Gate, upload and coordinate a RAM-only switch_emac management handoff."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-staged-20260819"
PROFILE = ARTIFACT / "switch-emac-port.env"
PROFILE_SHA256 = "6b512b4dbe9bb4212be293871bf197b3e4cc63ba90d355d3ee0da20ff4ce8ca9"
IMAGE = ROOT / "work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin"
IMAGE_SHA256 = "5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358"
RAM_INSMOD = ROOT / "outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
RAM_INSMOD_SHA256 = "8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6"
CLOSED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_GATE.env"
APPROVED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_GATE.approved.env"
HBM_RECLAIM_ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-hbm-watchdog-safe-20260820"
HBM_RECLAIM_CLOSED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_HBM_RECLAIM_GATE.env"
HBM_RECLAIM_APPROVED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_HBM_RECLAIM_GATE.approved.env"
RXALIGN_ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-rxalign-20260820"
RXALIGN_CLOSED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_RXALIGN_GATE.env"
RXALIGN_APPROVED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_RXALIGN_GATE.approved.env"
DIRECT_SYMBOLS_ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-direct-compact-tqe256-sramgate-20260820"
DIRECT_SYMBOLS_CLOSED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_DIRECT_SYMBOLS_GATE.env"
DIRECT_SYMBOLS_APPROVED_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_DIRECT_SYMBOLS_GATE.approved.env"
REMOTE = ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh"
RELEASE = "5.10.260-openmitrastar-radiohw"
ACK = "OPENMITRASTAR_QTN_W3_SWITCH_EMAC_HANDOFF_RAM_ONLY"
REMOTE_ROOT = "/tmp/w3-switch-emac"
REMOTE_GATE = "/tmp/W3_SWITCH_EMAC_HANDOFF_GATE.env"
REMOTE_STATE = "/run/openmitrastar/switch-emac-handoff"
HBM_COLD_MARKER = ROOT / "work/mission-state/.hbm-cold-required"

MODULES = [
    "platform/ruby/qtn_pm_qos_compat.ko",
    "platform/ruby/qtn_platform_support.ko",
    "platform/ruby/board_compat.ko",
    "platform/ruby/runtime_compat.ko",
    "platform/ruby/iputil.ko",
    "platform/ruby/dmautil.ko",
    "platform/topaz/switch_vlan.ko",
    "platform/topaz/fwt_if.ko",
    "platform/topaz/hbm.ko",
    "platform/topaz/topaz_congest_queue.ko",
    "platform/ruby/emac_lib.ko",
    "platform/topaz/dpi.ko",
    "platform/topaz/switch_tqe.ko",
    "platform/fwt/fwt_ctrl.ko",
    "platform/topaz/switch_emac.ko",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def gate_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def verify_sha256s() -> None:
    for line in (ARTIFACT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(None, 1)
        candidate = ARTIFACT / relative.strip()
        if sha256(candidate) != expected:
            raise SystemExit(f"artifact hash mismatch: {relative}")


def verify_module_manifest() -> None:
    module_root = ARTIFACT / "rootfs/lib/modules" / RELEASE / "extra/quantenna"
    rows = (ARTIFACT / "module-manifest.tsv").read_text(encoding="utf-8").splitlines()
    if not rows or rows[0] != "module\tsha256\tsize\tvermagic\tdepends":
        raise SystemExit("invalid module manifest header")
    verified: set[str] = set()
    for row in rows[1:]:
        relative, expected_sha, expected_size, vermagic, _depends = row.split("\t", 4)
        module = module_root / relative
        if not module.is_file():
            raise SystemExit(f"module manifest path missing: {relative}")
        if sha256(module) != expected_sha or module.stat().st_size != int(expected_size):
            raise SystemExit(f"module manifest mismatch: {relative}")
        if not vermagic.startswith(RELEASE + " "):
            raise SystemExit(f"module vermagic mismatch: {relative}")
        verified.add(relative)
    if len(verified) != 25:
        raise SystemExit("module manifest does not contain exactly 25 modules")


def verify_gate_artifact(values: dict[str, str]) -> None:
    manifest = ARTIFACT / "module-manifest.tsv"
    if values.get("W3_MODULE_MANIFEST_SHA256") != sha256(manifest):
        raise SystemExit("gate module manifest hash mismatch")
    rows = manifest.read_text(encoding="utf-8").splitlines()
    switch_hash = next(
        (row.split("\t", 4)[1] for row in rows[1:] if row.startswith("platform/topaz/switch_emac.ko\t")),
        None,
    )
    if not switch_hash or values.get("W3_SWITCH_EMAC_SHA256") != switch_hash:
        raise SystemExit("gate switch_emac hash mismatch")


def verify_artifact() -> None:
    if not ARTIFACT.is_dir():
        raise SystemExit(f"artifact missing: {ARTIFACT}")
    if sha256(IMAGE) != IMAGE_SHA256:
        raise SystemExit("watchdog image hash mismatch")
    if sha256(RAM_INSMOD) != RAM_INSMOD_SHA256:
        raise SystemExit("ram_insmod hash mismatch")
    if (ARTIFACT / "kernelrelease.txt").read_text(encoding="utf-8").strip() != RELEASE:
        raise SystemExit("artifact kernel release mismatch")
    expected = (ARTIFACT / "expected-modules.txt").read_text(encoding="utf-8")
    actual = (ARTIFACT / "actual-modules.txt").read_text(encoding="utf-8")
    if expected != actual or len([line for line in actual.splitlines() if line]) != 25:
        raise SystemExit("artifact 25-module closure mismatch")
    verify_sha256s()
    verify_module_manifest()
    module_root = ARTIFACT / "rootfs/lib/modules" / RELEASE / "extra/quantenna"
    for relative in MODULES:
        if not (module_root / relative).is_file():
            raise SystemExit(f"required handoff module missing: {relative}")
    if (ARTIFACT / "depmod-unresolved.log").read_bytes():
        raise SystemExit("artifact has unresolved module dependencies")
    duplicate_rows = (ARTIFACT / "duplicate-exported-symbols.tsv").read_text(
        encoding="utf-8"
    ).splitlines()
    if duplicate_rows != ["symbol\tmodules"]:
        raise SystemExit("artifact has duplicate exported symbols")
    if (ARTIFACT / "null-dma-api-calls.txt").read_bytes():
        raise SystemExit("artifact source gate found NULL Linux DMA API calls")
    if sha256(PROFILE) != PROFILE_SHA256:
        raise SystemExit("switch-emac profile hash mismatch")
    profile = gate_values(PROFILE)
    expected_profile = {
        "BOARD_PHY0": "1", "BOARD_PHY1": "3",
        "BOARD_RGMII_TIMING": "0x81828282",
        "MANAGEMENT_EMAC": "1",
        "MANAGEMENT_PHY": "3",
        "STANDBY_EMAC": "0",
        "MAC_SOURCE": "dt-local-mac-address-fail-closed",
        "PHYLIB_MODE": "disabled-no-phy-profile",
        "EMAC_BONDING": "0",
        "FWT_REMAPPER": "compiled-out-nonbonded",
        "HBM_IRQ": "arc-default-domain-hwirq21",
        "DMA_DEVICE": "openmitrastar-qtn-dma-32bit",
        "TRAFFIC_DIAGNOSTICS": "first8-tx-rx-hbm-plus-8s-snapshots",
        "RX_ROUTE": "explicit-static-tqe-lhost-readback",
        "RX_ALIGNMENT": "net-ip-align-2-arc700",
        "DESCRIPTOR_MODE": "real-dmautil-dram-lab-fallback-required",
    }
    for key, expected_value in expected_profile.items():
        if profile.get(key) != expected_value:
            raise SystemExit(f"switch-emac profile mismatch: {key}")


def ssh(host: str, command: str, timeout: int = 20, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "tools/ramssh_exec.py", command, "--host", host, "--timeout", str(timeout)],
        timeout=timeout + 15,
        check=check,
    )


def upload(host: str, source: Path, destination: str, mode: str) -> None:
    run(
        [sys.executable, "tools/ramssh_upload.py", str(source), destination, "--host", host, "--mode", mode],
        timeout=90,
    )


def wait_for_new_ssh(host: str, rollback_seconds: int, preserve_2g: bool,
                     preserve_direct_emac: bool = False) -> bool:
    deadline = time.monotonic() + rollback_seconds - 5
    management_path = (
        "test -e /sys/class/net/br0/brif/eth0 && "
        "test ! -e /sys/class/net/eth1_emac0 && "
        "test ! -e /sys/class/net/eth1_emac1 && "
        "test \"$(cat /sys/module/switch_emac/parameters/w3_symbols_only)\" = Y && "
        if preserve_direct_emac else
        "test -e /sys/class/net/br0/brif/eth1_emac1 && "
        "test ! -e /sys/class/net/br0/brif/tqe && "
        "test -e /sys/class/net/eth1_emac0 && "
        "test \"$(cat /sys/class/net/eth1_emac0/operstate)\" = down && "
    )
    validation = (
        f"test \"$(cat {REMOTE_STATE}/status)\" = awaiting-host-commit && "
        + management_path +
        "grep -q '^switch_emac ' /proc/modules && "
        "test \"$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)\" = 0 && "
        + ("test -e /sys/class/net/br0/brif/wlan0 && " if preserve_2g else "") +
        f"touch {REMOTE_STATE}/commit && echo W3_SWITCH_EMAC_NEW_SSH_COMMIT"
    )
    while time.monotonic() < deadline:
        result = ssh(host, validation, timeout=8, check=False)
        if result.returncode == 0 and "W3_SWITCH_EMAC_NEW_SSH_COMMIT" in result.stdout:
            return True
        time.sleep(2)
    return False


def main() -> int:
    global ARTIFACT, PROFILE, PROFILE_SHA256, CLOSED_GATE, APPROVED_GATE
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--management-host")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--rollback-seconds", type=int, default=75)
    parser.add_argument("--timeout", type=int, default=480)
    parser.add_argument("--wait-for-cold-power-cycle", action="store_true")
    parser.add_argument("--use-current-watchdog-boot", action="store_true")
    parser.add_argument("--use-current-no-watchdog-boot", action="store_true")
    parser.add_argument("--autoboot-wait-seconds", type=int, default=900)
    parser.add_argument("--hbm-reclaim", action="store_true")
    parser.add_argument("--rx-align", action="store_true")
    parser.add_argument("--preserve-2g", action="store_true")
    parser.add_argument(
        "--no-uart-reboot-on-failure", action="store_true",
        help="leave recovery to the already armed target-local rollback; never request UART reboot",
    )
    parser.add_argument(
        "--skip-ioss-reset-pulse", action="store_true",
        help="load board compatibility without pulsing IOSS reset; Q1 live-safe diagnostic path",
    )
    parser.add_argument(
        "--preserve-direct-emac", action="store_true",
        help="load switch_emac as a symbol provider only; keep direct eth0 bound and untouched",
    )
    parser.add_argument(
        "--tqe-ring-entries", type=int, choices=(256, 512), default=512,
        help="TQE RX ring size; compact 256 is explicit and MitraStar-only",
    )
    args = parser.parse_args()

    management_host = args.management_host or args.host
    try:
        ipaddress.IPv4Address(args.host)
        ipaddress.IPv4Address(management_host)
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"invalid IPv4 address: {exc}") from exc

    if args.hbm_reclaim and args.rx_align:
        raise SystemExit("--hbm-reclaim and --rx-align are mutually exclusive")
    if args.preserve_direct_emac and not args.skip_ioss_reset_pulse:
        raise SystemExit("--preserve-direct-emac requires --skip-ioss-reset-pulse")
    if args.preserve_direct_emac:
        ARTIFACT = DIRECT_SYMBOLS_ARTIFACT
        PROFILE = ARTIFACT / "switch-emac-port.env"
        PROFILE_SHA256 = "47c930f8ccadc1318d6993a35a801be7851cd49cbbbc477afcecedbe90dcdf31"
        CLOSED_GATE = DIRECT_SYMBOLS_CLOSED_GATE
        APPROVED_GATE = DIRECT_SYMBOLS_APPROVED_GATE
    elif args.rx_align:
        ARTIFACT = RXALIGN_ARTIFACT
        PROFILE = ARTIFACT / "switch-emac-port.env"
        PROFILE_SHA256 = "6b512b4dbe9bb4212be293871bf197b3e4cc63ba90d355d3ee0da20ff4ce8ca9"
        CLOSED_GATE = RXALIGN_CLOSED_GATE
        APPROVED_GATE = RXALIGN_APPROVED_GATE
    elif args.hbm_reclaim:
        ARTIFACT = HBM_RECLAIM_ARTIFACT
        PROFILE = ARTIFACT / "switch-emac-port.env"
        PROFILE_SHA256 = "6b512b4dbe9bb4212be293871bf197b3e4cc63ba90d355d3ee0da20ff4ce8ca9"
        CLOSED_GATE = HBM_RECLAIM_CLOSED_GATE
        APPROVED_GATE = HBM_RECLAIM_APPROVED_GATE

    if not 30 <= args.rollback_seconds <= 180:
        raise SystemExit("--rollback-seconds must be 30..180")
    if not 60 <= args.autoboot_wait_seconds <= 1800:
        raise SystemExit("--autoboot-wait-seconds must be 60..1800")
    if args.use_current_watchdog_boot and args.use_current_no_watchdog_boot:
        raise SystemExit("watchdog and no-watchdog current boot modes are mutually exclusive")
    if args.wait_for_cold_power_cycle and (args.use_current_watchdog_boot or args.use_current_no_watchdog_boot):
        raise SystemExit("cold wait and current watchdog boot are mutually exclusive")
    if args.execute and args.use_current_watchdog_boot and HBM_COLD_MARKER.exists():
        raise SystemExit(
            "HBM host state requires a physical cold cycle; use --wait-for-cold-power-cycle"
        )
    active_modules = (
        [relative for relative in MODULES if relative != "platform/fwt/fwt_ctrl.ko"]
        if args.skip_ioss_reset_pulse else MODULES
    )
    verify_artifact()
    gate = APPROVED_GATE if args.execute else CLOSED_GATE
    values = gate_values(gate)
    verify_gate_artifact(values)
    print(
        {
            "mode": "execute" if args.execute else "dry-run",
            "artifact": str(ARTIFACT),
            "modules": 25,
            "handoff_modules": len(active_modules),
            "approved": values["W3_SWITCH_EMAC_HANDOFF_APPROVED"],
            "target": values["W3_TARGET_COMPATIBLE"],
            "rollback_seconds": args.rollback_seconds,
            "cold_power_cycle_wait": args.wait_for_cold_power_cycle,
            "current_watchdog_boot": args.use_current_watchdog_boot,
            "current_no_watchdog_boot": args.use_current_no_watchdog_boot,
            "boot_host": args.host,
            "management_host": management_host,
            "preserve_2g": args.preserve_2g,
            "skip_ioss_reset_pulse": args.skip_ioss_reset_pulse,
            "preserve_direct_emac": args.preserve_direct_emac,
            "tqe_ring_entries": args.tqe_ring_entries,
            "uart_reboot_on_failure": not args.no_uart_reboot_on_failure,
            "module_order": [Path(relative).stem for relative in active_modules],
            "fwt_acceleration": "disabled-local-shims" if args.skip_ioss_reset_pulse else "hardware-fwt_ctrl",
            "rollback_before_first_insmod": True,
            "profile_sha256": PROFILE_SHA256,
            "logical_date": "2026-08-19",
            "flash": False,
        }
    )
    if not args.execute:
        print("W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    if values.get("W3_SWITCH_EMAC_HANDOFF_APPROVED") != "1":
        raise SystemExit("approved gate is not open")

    # Use a runtime copy so the chosen bounded rollback interval is signed by
    # the uploaded gate contents and visible to the remote script.
    runtime_gate = ROOT / "work/mission-state/w3-offline/.W3_SWITCH_EMAC_HANDOFF_GATE.runtime.env"
    runtime_text = APPROVED_GATE.read_text(encoding="utf-8")
    runtime_text = runtime_text.replace("W3_ROLLBACK_SECONDS=75", f"W3_ROLLBACK_SECONDS={args.rollback_seconds}")
    runtime_text = runtime_text.replace("W3_HOST_IPV4=192.168.1.43", f"W3_HOST_IPV4={args.server_ip}")
    runtime_text = runtime_text.replace("W3_MANAGEMENT_IPV4=192.168.1.200", f"W3_MANAGEMENT_IPV4={management_host}")
    runtime_text += f"\nW3_SKIP_IOSS_RESET_PULSE={1 if args.skip_ioss_reset_pulse else 0}\n"
    runtime_text += f"W3_PRESERVE_DIRECT_EMAC={1 if args.preserve_direct_emac else 0}\n"
    runtime_text += f"W3_TQE_RING_ENTRIES={args.tqe_ring_entries}\n"
    runtime_gate.write_text(runtime_text, encoding="utf-8", newline="\n")

    tftp: subprocess.Popen[str] | None = None
    capture: subprocess.Popen[str] | None = None
    effective_timeout = max(
        args.timeout,
        args.autoboot_wait_seconds + 300 if args.wait_for_cold_power_cycle else args.timeout,
    )
    try:
        if args.use_current_watchdog_boot or args.use_current_no_watchdog_boot:
            bridge_preflight = (
                "test -e /sys/class/net/br0/brif/eth0 && "
                "test -e /sys/class/net/br0/brif/wlan0 && "
                "/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl "
                "-i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && "
                if args.preserve_2g else
                "test ! -e /sys/class/net/br0 && "
            )
            watchdog_preflight = (
                "dmesg | grep -Eq 'OMWDT stage=(armed|pet first=1)' && "
                if args.use_current_watchdog_boot else ""
            )
            current = ssh(
                args.host,
                "test \"$(uname -r)\" = 5.10.260-openmitrastar-radiohw && "
                + watchdog_preflight +
                "test -e /sys/class/net/eth0 && " + bridge_preflight +
                "! grep -Eq '^(hbm|switch_tqe|fwt_ctrl|switch_emac|wlan|qdrv) ' /proc/modules && "
                "echo W3_CURRENT_WATCHDOG_BOOT_PREFLIGHT_PASS",
                timeout=20,
            )
            if "W3_CURRENT_WATCHDOG_BOOT_PREFLIGHT_PASS" not in current.stdout:
                raise RuntimeError("current RAM boot preflight marker missing")
        else:
            tftp = subprocess.Popen(
                [sys.executable, "tools/tftp_serve_once.py", "--root", str(IMAGE.parent), "--bind", "0.0.0.0", "--port", "69", "--timeout", str(effective_timeout), "--once"],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            time.sleep(0.6)
            boot_command = [
                "pwsh.exe", "-NoProfile", "-File", "tools/reboot_boot_ramssh.ps1",
                "-Port", args.port, "-Filename", IMAGE.name, "-ServerIp", args.server_ip,
                "-ClientIp", args.host, "-TimeoutSeconds", str(effective_timeout),
                "-AutobootWaitSeconds", str(args.autoboot_wait_seconds),
                "-EntropyPromptPattern", "(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED",
                "-EntropyOkPattern", "OMPRODUCT_SERIAL_ENTROPY_OK bits=256",
                "-ReadyPattern", "OMPRODUCT_READY state=(ready|degraded)",
            ]
            if args.wait_for_cold_power_cycle:
                boot_command.append("-SkipReboot")
            # Keep the serial listener's readiness marker visible to outer
            # orchestrators.  Capturing this child until completion makes a
            # cold-cycle supervisor announce readiness before COM is open.
            subprocess.run(
                boot_command,
                cwd=ROOT,
                text=True,
                timeout=effective_timeout + 120,
                check=True,
            )
        if not args.use_current_no_watchdog_boot:
            ssh(args.host, "dmesg | grep -E 'OMWDT stage=(armed|pet first=1)'", timeout=20)
        HBM_COLD_MARKER.write_text(
            "required=1\n"
            f"armed_at={time.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            "reason=HBM ladder entered; warm reboot is not sufficient until ordered teardown is hardware-proven\n",
            encoding="utf-8",
        )
        uart_dir = ROOT / "outputs/uart-live" / ("w3-switch-emac-handoff-" + time.strftime("%Y%m%d-%H%M%S"))
        capture = subprocess.Popen(
            ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1", "-Port", args.port, "-Seconds", str(args.rollback_seconds + 150), "-OutputDirectory", str(uart_dir)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        ssh(args.host, f"rm -rf {REMOTE_ROOT}; mkdir -p {REMOTE_ROOT}")
        module_root = ARTIFACT / "rootfs/lib/modules" / RELEASE / "extra/quantenna"
        for relative in active_modules:
            source = module_root / relative
            upload(args.host, source, f"{REMOTE_ROOT}/{source.name}", "0600")
        upload(args.host, RAM_INSMOD, f"{REMOTE_ROOT}/ram_insmod", "0700")
        upload(args.host, REMOTE, f"{REMOTE_ROOT}/handoff.sh", "0700")
        upload(args.host, runtime_gate, REMOTE_GATE, "0600")
        launch = (
            f"sed -i 's/\\r$//' {REMOTE_ROOT}/handoff.sh {REMOTE_GATE}; "
            f"if command -v setsid >/dev/null 2>&1; then "
            f"setsid sh {REMOTE_ROOT}/handoff.sh {REMOTE_ROOT} {REMOTE_GATE} {REMOTE_STATE} "
            f"</dev/null >/dev/console 2>&1 & "
            f"else sh {REMOTE_ROOT}/handoff.sh {REMOTE_ROOT} {REMOTE_GATE} {REMOTE_STATE} "
            f"</dev/null >/dev/console 2>&1 & fi; echo W3_SWITCH_EMAC_DETACHED_PID=$!"
        )
        launched = ssh(args.host, launch, timeout=20)
        if "W3_SWITCH_EMAC_DETACHED_PID=" not in launched.stdout:
            raise RuntimeError("detached handoff did not acknowledge launch")
        if not wait_for_new_ssh(management_host, args.rollback_seconds, args.preserve_2g,
                                args.preserve_direct_emac):
            # The remote timer owns normal rollback.  Give the rebound direct
            # interface time to return before escalating to UART recovery.
            time.sleep(12)
            restored = ssh(
                management_host,
                f"cat {REMOTE_STATE}/status 2>/dev/null; test -e /sys/class/net/br0/brif/eth0",
                timeout=10,
                check=False,
            )
            if restored.returncode == 0 and "rolled-back" in restored.stdout:
                raise RuntimeError("accelerated handoff rolled back to direct EMAC")
            if args.no_uart_reboot_on_failure:
                raise RuntimeError(
                    "management did not return; target-local rollback left armed; UART reboot forbidden"
                )
            run(["pwsh.exe", "-NoProfile", "-File", "tools/uart_sysrq_reboot.ps1", "-Port", args.port], timeout=60, check=False)
            raise RuntimeError("management did not return; UART recovery requested")
        management_path = (
            "test -e /sys/class/net/br0/brif/eth0 && "
            "test ! -e /sys/class/net/eth1_emac0 && "
            "test ! -e /sys/class/net/eth1_emac1 && "
            "test \"$(cat /sys/module/switch_emac/parameters/w3_symbols_only)\" = Y && "
            if args.preserve_direct_emac else
            "test -e /sys/class/net/br0/brif/eth1_emac1 && "
            "test ! -e /sys/class/net/br0/brif/tqe && "
        )
        committed = ssh(
            management_host,
            f"i=0; while [ $i -lt 15 ]; do s=$(cat {REMOTE_STATE}/status 2>/dev/null || true); "
            f"[ \"$s\" = committed ] && break; sleep 1; i=$((i+1)); done; "
            f"test \"$(cat {REMOTE_STATE}/status)\" = committed && "
            + management_path +
            "test \"$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)\" = 0 && "
            + ("test -e /sys/class/net/br0/brif/wlan0 && " if args.preserve_2g else "") +
            "echo W3_SWITCH_EMAC_HANDOFF_PASS",
            timeout=30,
        )
        if "W3_SWITCH_EMAC_HANDOFF_PASS" not in committed.stdout:
            raise RuntimeError("commit readback missing")
        print("W3_SWITCH_EMAC_HANDOFF_EXPERIMENT_PASS=1")
        return 0
    finally:
        try:
            runtime_gate.unlink(missing_ok=True)
        except OSError:
            pass
        if capture and capture.poll() is None:
            capture.terminate()
        if tftp and tftp.poll() is None:
            tftp.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
