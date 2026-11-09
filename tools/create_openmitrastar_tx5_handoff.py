#!/usr/bin/env python3
"""Create a compact, reproducible Linux 5.10 + RTL8192EE TX5 handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


TX5_NAME = "linux510-w2-2g-parity-tx5-desc-clear-beacon-v1-RAM-TEST-NO-FLASH.bin"
TX5_SHA256 = "5a69e2b57c6adeed4d38c13578617cc5680d36e02500405a02e26e8b293c8606"
TX5_BYTES = 4_330_002


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(root: Path, stage: Path, relative: str, target: str | None = None) -> None:
    source_candidate = root / relative
    source = source_candidate.resolve()
    if source_candidate.is_symlink() or not source.is_relative_to(root):
        raise ValueError(f"unsafe source path: {source}")
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = (stage / (target or relative)).resolve()
    if not destination.is_relative_to(stage):
        raise ValueError(f"unsafe destination path: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_source_tree(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name in {".git", "__pycache__"}
            or name.endswith((".o", ".ko", ".cmd", ".pyc"))
            or (Path(_directory) / name).is_symlink()
        }

    shutil.copytree(source, destination, ignore=ignore)


def load_traffic(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def write_handoff(stage: Path, traffic: dict) -> None:
    summary = traffic.get("summary", traffic)
    evaluation = load_traffic(stage / "evidence/tx5-clean-open-traffic-evaluation.json")
    if evaluation:
        traffic_status = evaluation.get("status", "evaluation-unknown")
        traffic_pass = bool(evaluation.get("pass", False))
    elif summary.get("complete") and summary.get("authorization_observed"):
        if summary.get("wifi_rx_bytes_delta", 0) > 0 and summary.get("wifi_tx_bytes_delta", 0) > 0:
            traffic_status = "authorized-bidirectional-light-traffic-observed"
        else:
            traffic_status = "authorized-without-bidirectional-traffic"
        traffic_pass = False
    else:
        traffic_status = summary.get("status", "capture-not-complete")
        traffic_pass = False
    stage.joinpath("HANDOFF.md").write_text(
        f"""# OpenMitraStar Linux 5.10 + Wi-Fi 2.4 GHz TX5 handoff

Generated: {datetime.now().astimezone().isoformat(timespec="seconds")}

## Exact RAM image

- Target: MitraStar HGW-500BNA-QCv2 A2 / ARC700 / Realtek RTL8192EE `10ec:818b`.
- Kernel: `5.10.260-openmitrastar-radiohw`.
- Image: `{TX5_NAME}`.
- SHA-256: `{TX5_SHA256}`.
- Size: `{TX5_BYTES}` bytes.
- Safety class: RAM-only, no flash, no MTD and no bootenv writes.

## Current hardware proof — 2026-08-22

- Exact TX5 image TFTP-loaded and CRC-verified by Bootbase/U-Boot.
- Linux 5.10, Ethernet 1 Gbit/s and authenticated SSH reached the live gate.
- `rtl8192ee`, firmware, MAC, PHY and IQK initialized.
- Open AP `OpenMitraStar-2G-DIAG`, channel 1, `wpa=0`.
- Physical iPhone reached AUTH, ASSOC and AUTHORIZED.
- Station signal was about -26 dBm and negotiated TX rate was 130 Mbit/s.
- `br0` contained `eth0` and `wlan0`; IRQ20 and IRQ28 progressed.
- Traffic capture status: `{traffic_status}`; pass={str(bool(traffic_pass)).lower()}.

The association result is proven. Internet throughput and a ten-minute soak are
not proven unless the included traffic evidence explicitly says so.

## Driver findings carried by TX5

1. Topaz must expose the Realtek endpoint through the preserved PCIe host setup
   and route Legacy INTx through SoC IRQ28.
2. The ARC target needs aligned EEPROM access and non-coherent DMA/cache care.
3. IRQ28 lifecycle is target-gated: request with `IRQF_NO_AUTOEN`, release only
   after the adapter is ready, and acknowledge managed deferred re-entry.
4. RTL8192EE warm firmware state is cleaned before re-download.
5. TX5 uses compact 32-byte TXBDs only for BK/BE/VI/VO; beacon, command,
   management, high and HCCA queues stay at 64 bytes.
6. TX5 clears recycled compact descriptors before setting packet/buffer sizes.
7. The beacon tasklet performs `dma_wmb()` and explicitly polls BCNQ.
8. TX5 proved visibility and authorization, but its historical data-path run
   showed BE WP advancing while RP stayed still. The later global-32 experiment
   and management-layout experiments are included as evidence, not as promoted
   replacements for TX5.

`provenance/tx5-exact` contains the patches/tests captured by the exact TX5
module build. `source/current-working-tree-not-exact-tx5` is intentionally
labelled as later investigative source and must not be treated as byte-identical
TX5 source.

## Reproduction

1. Verify `SHA256SUMS`.
2. Serve `artifacts/{TX5_NAME}` from TFTP.
3. Use `tools/reboot_boot_ramssh.ps1` for RAM boot only.
4. Confirm hostapd `ENABLED` and the open SSID.
5. Run `tools/wait_w2_2g_client.py` until AUTHORIZED.
6. Run `tools/monitor_2g_live_traffic.py`; require bridge traffic, IRQ progress,
   SSH continuity, no fatal kernel marker and useful bidirectional data.

Do not flash this image. Preserve the OEM/recovery slot and UART/TFTP recovery.
No passwords, PSKs, private keys, cookies or device dumps are included.
""",
        encoding="utf-8",
    )

    client_path = stage / "evidence/tx5-clean-open-client-wait.json"
    client = load_traffic(client_path)
    current = {
        "schema": "openmitrastar.current-live-state/v1",
        "captured_on": "2026-08-22",
        "target": "MitraStar HGW-500BNA-QCv2 A2",
        "kernel": "5.10.260-openmitrastar-radiohw",
        "image": {"name": TX5_NAME, "bytes": TX5_BYTES, "sha256": TX5_SHA256},
        "safety": {"ram_only": True, "flash_written": False, "mtd_written": False, "bootenv_written": False},
        "radio_2g": {
            "driver": "rtl8192ee",
            "ssid": "OpenMitraStar-2G-DIAG",
            "security": "OPEN",
            "channel": 1,
            "hostapd_enabled": client.get("ap_enabled_all_samples", False),
            "carrier": client.get("carrier_all_samples", False),
            "associated": client.get("association_observed", False),
            "authorized": client.get("authorization_observed", False),
        },
        "bridge": {"name": "br0", "members": ["eth0", "wlan0"]},
        "traffic_gate": {
            "status": traffic_status,
            "pass": traffic_pass,
            "failures": evaluation.get("failures", []) if evaluation else [],
            "wifi_rx_bytes_delta": summary.get("wifi_rx_bytes_delta", 0),
            "wifi_tx_bytes_delta": summary.get("wifi_tx_bytes_delta", 0),
            "irq20_delta": summary.get("irq20_delta", 0),
            "irq28_delta": summary.get("irq28_delta", 0),
            "ssh_alive_all_samples": summary.get("ssh_alive_all_samples", False),
            "fatal_markers_during_run": summary.get("fatal_markers_during_run"),
            "throughput_tested": False,
            "ten_minute_soak_tested": False,
        },
        "next_gate": "Run controlled LAN/Internet throughput, inspect BE hardware RP/WP, then complete a 10-minute soak.",
    }
    stage.joinpath("CURRENT_LIVE_STATE.json").write_text(
        json.dumps(current, indent=2) + "\n", encoding="utf-8"
    )


def secret_scan(stage: Path) -> tuple[int, list[str]]:
    patterns = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?im)^\s*(?:wpa_passphrase|wpa_psk|sae_password)\s*=\s*(?!<|__|\$)[^\s#]{8,}\s*$"),
        re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    )
    findings: list[str] = []
    scanned = 0
    text_suffixes = {
        ".md", ".txt", ".json", ".log", ".c", ".h", ".patch", ".sh",
        ".py", ".ps1", ".conf", ".yaml", ".yml", ".pem", ".key",
    }
    sensitive_names = {
        "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
        "dropbear_rsa_host_key", "dropbear_ecdsa_host_key", "dropbear_ed25519_host_key",
    }
    for path in stage.rglob("*"):
        if path.is_symlink():
            findings.append(f"symlink:{path.relative_to(stage).as_posix()}")
            continue
        if not path.is_file():
            continue
        if path.name.lower() in sensitive_names:
            findings.append(f"sensitive-filename:{path.relative_to(stage).as_posix()}")
            continue
        if path.suffix.lower() not in text_suffixes:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in patterns):
            findings.append(path.relative_to(stage).as_posix())
    return scanned, findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    root = args.workspace.resolve()
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}", args.timestamp):
        raise ValueError("--timestamp must use YYYYMMDD-HHMMSS")
    name = f"openmitrastar-linux510-2g4-tx5-handoff-{args.timestamp}"
    handoff_root = (root / "outputs" / "handoffs").resolve()
    stage = (handoff_root / name).resolve()
    if stage.parent != handoff_root:
        raise ValueError("handoff path escapes outputs/handoffs")
    zip_path = stage.with_suffix(".zip")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    image = root / "work" / "tftp" / "omvl" / TX5_NAME
    if image.stat().st_size != TX5_BYTES or sha256(image) != TX5_SHA256:
        raise RuntimeError("TX5 image identity mismatch")
    copy_file(root, stage, f"work/tftp/omvl/{TX5_NAME}", f"artifacts/{TX5_NAME}")

    bundle = "outputs/kernel-port/realtek-loop/w2-tx5-beacon-tasklet-poll-desc-clear-RAM-ONLY-NO-FLASH"
    for relative in (
        "manifest.json", "LOAD_ORDER.txt", "SHA256SUMS", "UPLOAD_SHA256SUMS", "ram_insmod",
        "firmware/rtlwifi/rtl8192eefw.bin", "firmware/regulatory.db",
        "modules/ctr.ko", "modules/ccm.ko", "modules/cmac.ko", "modules/cfg80211.ko",
        "modules/libarc4.ko", "modules/mac80211.ko", "modules/rtlwifi.ko",
        "modules/btcoexist.ko", "modules/rtl_pci.ko", "modules/rtl8192ee.ko",
    ):
        copy_file(root, stage, f"{bundle}/{relative}", f"artifacts/realtek-tx5/{relative}")
    copy_source_tree(
        root / bundle / "evidence",
        stage / "provenance/tx5-exact/evidence",
    )
    copy_file(root, stage, f"{bundle}/manifest.json", "provenance/tx5-exact/manifest.json")
    copy_file(root, stage, f"{bundle}/SHA256SUMS", "provenance/tx5-exact/SHA256SUMS")

    kernel = root / "work/kernel-port/linux-5.10"
    copy_source_tree(
        kernel / "drivers/net/wireless/realtek/rtlwifi",
        stage / "source/current-working-tree-not-exact-tx5/linux-5.10/drivers/net/wireless/realtek/rtlwifi",
    )
    for relative in (
        "drivers/pci/controller/pcie-qtn-topaz.c",
        "drivers/irqchip/irq-qtn-topaz.c",
        "arch/arc/boot/dts/topaz_mitrastar_ramssh.dts",
    ):
        copy_file(root, stage, f"work/kernel-port/linux-5.10/{relative}", f"source/current-working-tree-not-exact-tx5/linux-5.10/{relative}")
    for path in sorted(kernel.glob("rtlwifi-*.patch")):
        copy_file(root, stage, str(path.relative_to(root)), f"investigations/post-tx5-patches/{path.name}")
    copy_file(root, stage, "work/kernel-port/linux-5.10/topaz-pcie-intx-irqchip-gate.patch", "investigations/post-tx5-patches/topaz-pcie-intx-irqchip-gate.patch")
    stage.joinpath("source/README.md").write_text(
        "# Source scope\n\n"
        "The exact promoted object code is under `artifacts/realtek-tx5`, with its build-time patches and tests under `provenance/tx5-exact`.\n\n"
        "`current-working-tree-not-exact-tx5` is a later diagnostic tree containing post-TX5 experiments. It is included for ongoing investigation only and is not a source identity claim for the TX5 binaries.\n",
        encoding="utf-8",
    )

    for relative in (
        "tools/reboot_boot_ramssh.ps1", "tools/ramssh_exec.py", "tools/ramssh_upload.py",
        "tools/tiny_tftp_server.py", "tools/wait_w2_2g_client.py",
        "tools/monitor_2g_live_traffic.py", "tools/collect_w2_2g_client_gate.py",
        "tools/evaluate_w2_2g_live_traffic.py", "tools/run_w2_2g_tx5_gate.ps1",
        "tools/build_realtek_8192ee_incremental.sh", "tools/build_w2_2g_parity_ram_candidate.sh",
        "tools/test_realtek_beacon_poll.py", "tools/test_realtek_tx2_ring_accounting.py",
        "tools/test_w2_2g_parity_candidate.py", "tools/test_w2_2g_client_gate.py",
        "tools/test_monitor_2g_live_traffic.py", "tools/test_evaluate_w2_2g_live_traffic.py",
        "tools/create_openmitrastar_tx5_handoff.py",
    ):
        copy_file(root, stage, relative)

    for relative in (
        "work/mission-state/TX5_OFFLINE_CHECKPOINT_20260822.md",
        "work/mission-state/W2_TX7_OEM_TXBD_CONTRACT_20260822.md",
        "work/mission-state/w2-2g-parity-tx5-desc-clear-beacon-v1/build/manifest.json",
        "work/mission-state/w2-2g-parity-tx5-desc-clear-beacon-v1/build/bootbase-contract.json",
    ):
        copy_file(root, stage, relative)
    for relative, target in (
        ("work/mission-state/HARDWARE_STATE.json", "context/historical/HARDWARE_STATE.pre-clean-tx5.json"),
        ("work/mission-state/MISSION_STATE.md", "context/historical/MISSION_STATE.pre-clean-tx5.md"),
        ("work/mission-state/EVIDENCE_LEDGER.md", "context/historical/EVIDENCE_LEDGER.md"),
        ("outputs/uart-live/w2-tx5-clean-open-client-wait.json", "evidence/tx5-clean-open-client-wait.json"),
        ("outputs/uart-live/w2-tx5-clean-open-traffic-20260822.json", "evidence/tx5-clean-open-traffic.raw.log"),
        ("outputs/uart-live/w2-tx5-clean-open-traffic-20260822.json.json", "evidence/tx5-clean-open-traffic-summary.json"),
        ("outputs/uart-live/w2-tx5-clean-open-traffic-evaluation-20260822.json", "evidence/tx5-clean-open-traffic-evaluation.json"),
        ("outputs/uart-live/w2-tx5-postboot-gate.json", "evidence/tx5-earlier-postboot-gate.json"),
    ):
        copy_file(root, stage, relative, target)

    boot_logs = sorted((root / "outputs/uart-live").glob("ramssh-cycle-20260822-182858.log"))
    if boot_logs:
        copy_file(root, stage, str(boot_logs[-1].relative_to(root)), "evidence/tx5-clean-ram-boot.log")

    traffic = load_traffic(root / "outputs/uart-live/w2-tx5-clean-open-traffic-20260822.json.json")
    write_handoff(stage, traffic)

    records = []
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        records.append({
            "path": path.relative_to(stage).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    stage.joinpath("MANIFEST.json").write_text(
        json.dumps({"schema": "openmitrastar.tx5-handoff/v1", "files": records}, indent=2) + "\n",
        encoding="utf-8",
    )
    stage.joinpath("SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(stage).as_posix()}\n" for path in sorted(p for p in stage.rglob("*") if p.is_file())),
        encoding="utf-8",
    )

    scanned, findings = secret_scan(stage)
    stage.joinpath("SECRET_SCAN.txt").write_text(
        f"SECRET_SCAN={'PASS' if not findings else 'FAIL'}\ntext_files_scanned={scanned}\n"
        + "".join(f"finding={item}\n" for item in findings),
        encoding="utf-8",
    )
    if findings:
        raise RuntimeError("secret scan failed: " + ", ".join(findings))

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            archive.write(path, f"{name}/{path.relative_to(stage).as_posix()}")
    digest = sha256(zip_path)
    zip_path.with_suffix(".zip.sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    print(f"HANDOFF_DIR={stage}")
    print(f"HANDOFF_ZIP={zip_path}")
    print(f"ZIP_BYTES={zip_path.stat().st_size}")
    print(f"ZIP_SHA256={digest}")
    print("SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
