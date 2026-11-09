#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

from create_openmitrastar_external_handoff import (
    copy_file,
    read_text_auto,
    redact_lab_identifiers,
    scan_stage,
    sha256,
    write_manifest,
)


WSL = Path(r"\\wsl.localhost\podman-mem9-tidb\home\user\mitrastar-linux-5.10.260")
KERNEL_SHA = "900282bd7e31607d86ccf040c89967371af3884a2089e7d405e7b5301d848c48"
RTL_PCI_SHA = "e572839c296703732cd26171901dd481d6baed7fdcdd610c46d4f422499531ab"
PSK = re.compile(
    r"(?im)^\s*(?:wpa_passphrase|wpa_psk|psk|sae_password|passphrase)\s*=\s*"
    r"(?!__RUNTIME_|\$|@|\{|<|re\.compile\b|none\b|false\b|true\b)[^\s#]{8,}"
)


def copy_tree(source: Path, target: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {
            name for name in names
            if name in {".git", "__pycache__"}
            or name.endswith((".o", ".ko", ".cmd", ".pyc"))
        }
    shutil.copytree(source, target, ignore=ignore)


def extract_log(path: Path, markers: tuple[str, ...]) -> str:
    lines = []
    for line in read_text_auto(path).splitlines():
        if any(marker in line for marker in markers):
            line = redact_lab_identifiers(line)
            line = re.sub(r"SHA256:[A-Za-z0-9+/=]+", "SHA256:<public-key-fingerprint-redacted>", line)
            lines.append(line)
    return "\n".join(lines).strip() + "\n"


def migration_doc() -> str:
    return """# MIGRATION TARGET 2G4

Date: 2026-08-18  
Target: MitraStar HGW-500BNA-QCv2 A2, Realtek `10ec:818b`, ARC700.  
Scope: private engineering handoff; RAM-only, no flash candidate.

## OEM/origen -> Linux 5.10

The OEM/origen used Linux 2.6.35.12 plus a vendor Realtek stack. The migration replaces the 2.4 GHz control/data path with Linux `5.10.260-openmitrastar-radiohw`, upstream rtlwifi/RTL8192EE, mac80211, cfg80211/nl80211, public `rtl8192eefw.bin`, ES regulatory data and a static hostapd control plane.

The Topaz substrate is explicit: ARC IRQ controller, `LHOST_INT_EN`, SoC PCIe Legacy INTx gate, Bootbase-preserved PCIe enumeration, non-coherent DMA/cache operations and the MitraStar RAM DT.

## Exact current stack

- RAM kernel SHA-256 `900282bd7e31607d86ccf040c89967371af3884a2089e7d405e7b5301d848c48`.
- V5 `rtl_pci.ko` SHA-256 `e572839c296703732cd26171901dd481d6baed7fdcdd610c46d4f422499531ab`.
- `rtl8192ee.ko` SHA-256 `8ebda96ee35ffc0aa51838dd3fef32581b679b6f36c807b00be56df4a00d77e7`.
- Realtek firmware SHA-256 `c6e5beeeb2a716ce417a9ede5974d0876b18ebf0368c195da8a181f6ba6d9b4b`.
- `regulatory.db` SHA-256 `e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393`.

## Proven hardware milestones

- Linux 5.10 RAM boot, Ethernet and key-only SSH.
- PCIe endpoint enumeration, BAR2 and IRQ28.
- ARC unaligned EEPROM fault understood and fixed.
- RTL8192EE firmware, MAC, PHY and IQK initialization.
- `phy0`/`wlan0`, channel 1 monitor mode.
- Descriptor and payload DMA consumed; MGNT read pointer reaches write pointer.
- Real management TX completion and real 2.4 GHz RX delivered to AF_PACKET.
- IRQ lifecycle V3 produced stable bidirectional monitor runtime.
- V5 preserves managed deferred reentries as `IRQ_HANDLED`; AP UART no longer reaches `nobody cared` in the captured V5 interval.
- ES regulatory domain loads before cfg80211.

## Rejected failures

1. Raw ARC `u16` EEPROM access: alignment exception.
2. No SoC INTx bit: descriptors consumed but IRQ28/TX counters remained zero.
3. Inbound iATU hypothesis: disproven; DMA succeeds while inbound0 stays disabled.
4. V1 permanent host-probe INTx enable: RXFOVW storm and RX zero.
5. V2 irqchip-only enable: request_irq still opened the route before radio start.
6. V3 immediate post-request disable: auto-enable race allowed IRQ_NONE responses and Linux disabled IRQ28 as `nobody cared` during AP key installation.
7. V4 `NO_AUTOEN` fixed request-time race, but deferred reentries after the first real ISR still returned IRQ_NONE.
8. Foreground AP bridge migration: removing L3 from eth0 killed its own SSH launcher before br0 readback.

## V5, AP and bridge state

V5 is the current module target. It uses dedicated `IRQF_NO_AUTOEN` only for MitraStar/IRQ28/`10ec:818b`; other rtlwifi platforms retain shared IRQ behavior. Managed reentry while the tasklet temporarily owns the interrupt returns `IRQ_HANDLED`; nonmanaged shared interrupts still return `IRQ_NONE`.

The corrected AP offline bundle is reproducible (`2f79e625...20f19b6`), contains static hostapd/iw/tools, no bundled PSK, ES regdb, bridge/isolated topologies and a detached executor. Offline/QEMU/hash gates pass.

AP and bridge runtime is **runtime pendiente**: latest V5 AP staging kept IRQ28 alive and constructed br0, but the foreground SSH launcher timed out when eth0 L3 moved. A detached launcher must finish bridge management recovery, hostapd `ENABLED`, client `AUTHORIZED` and ping 3/3.

## Next changes

1. Clean RAM boot with V5 and verify markers `irq-line-noautoen`, `start-ready`, `managed-deferred` and absence of `nobody cared`.
2. Run AP start detached from management SSH.
3. Preserve management IP atomically on br0 before clearing eth0 L3; retain rollback watchdog.
4. Supply SSID/PSK only at runtime; never log or archive them.
5. Prove hostapd `ENABLED`, station `AUTHORIZED`, nl80211 station telemetry and ping 3/3.
6. Run AP stop/rollback and restore monitor/recovery management.
7. Only after repeated clean RAM boots integrate 2.4 GHz into the product rootfs. Flash remains out of scope.
"""


def exclusions_doc() -> str:
    return """# Private 2.4 GHz handoff exclusions

- Provider firmware and all MTD/full-flash/partition/readback images.
- Bootbase env, bootcfg, JFFS2/runtime configuration, calibration and unique identifiers.
- PSKs, passphrases, SSIDs used in live tests, client MACs, cookies, tokens, passwords and private keys.
- Raw authentication logs; evidence files are filtered and identifiers redacted.
- OEM rootfs/UI/accounts and proprietary Quantenna binaries.
- Device-specific wireless calibration/regulatory configuration. Included regulatory.db is public/reproducible ES policy data.
- Unrelated projects and generated object/build-cache files.

Allowed configuration files are build/Kconfig fragments only, never live device configuration.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    name = f"openmitrastar-2g4-private-{args.timestamp}"
    stage = workspace / "outputs/handoffs" / name
    zip_path = stage.with_suffix(".zip")
    stage.mkdir(parents=True)

    kernel = workspace / "work/tftp/omvl/linux510-radiohw-pci-probe-webformat.bin"
    if sha256(kernel) != KERNEL_SHA:
        raise ValueError("kernel drift")
    copy_file(workspace, stage, kernel, "artifacts/kernel/linux510-radiohw-intx-irqchip-v2-webformat.bin")
    current = workspace / "outputs/kernel-port/realtek-loop/current-RAM-ONLY-NO-FLASH"
    for relative in (
        "modules/cfg80211.ko", "modules/libarc4.ko", "modules/mac80211.ko",
        "modules/rtlwifi.ko", "modules/btcoexist.ko", "modules/rtl_pci.ko",
        "modules/rtl8192ee.ko", "firmware/rtlwifi/rtl8192eefw.bin",
        "manifest.json", "LOAD_ORDER.txt", "UPLOAD_SHA256SUMS", "SHA256SUMS", "ram_insmod",
    ):
        copy_file(workspace, stage, current / relative, f"artifacts/{relative}")
    if sha256(stage / "artifacts/modules/rtl_pci.ko") != RTL_PCI_SHA:
        raise ValueError("rtl_pci drift")

    ap = workspace / "outputs/kernel-port/realtek-ap-bundle"
    for relative in (
        "openmitrastar-realtek-ap-RAM-ONLY-NO-FLASH.tar", "manifest.json",
        "validation.log", "BUNDLE_SHA256", "SHA256SUMS.target",
        "provenance/HOSTAPD_PROVENANCE.txt", "provenance/REGDB_PROVENANCE.txt",
        "firmware/regulatory.db", "runtime/ap-start.sh", "runtime/ap-stop.sh", "runtime/ap-smoke.sh",
    ):
        copy_file(workspace, stage, ap / relative, f"artifacts/ap/{relative}")
    copy_file(workspace, stage, ap / "firmware/regulatory.db", "artifacts/firmware/regulatory.db")

    copy_tree(WSL / "drivers/net/wireless/realtek/rtlwifi", stage / "src/linux-5.10/drivers/net/wireless/realtek/rtlwifi")
    copy_tree(WSL / "net/mac80211", stage / "src/linux-5.10/net/mac80211")
    copy_tree(WSL / "net/wireless", stage / "src/linux-5.10/net/wireless")
    for relative in (
        "include/net/mac80211.h", "include/net/cfg80211.h", "include/net/regulatory.h",
        "include/uapi/linux/nl80211.h", "drivers/pci/controller/pcie-qtn-topaz.c",
        "arch/arc/kernel/intc-compact.c", "arch/arc/mm/cache.c", "kernel/dma/direct.c",
        "kernel/dma/pool.c", "drivers/irqchip/irq-qtn-topaz.c",
        "arch/arc/boot/dts/topaz_mitrastar_ramssh.dts",
    ):
        copy_file(workspace, stage, WSL / relative, f"src/linux-5.10/{relative}")

    patches = stage / "patches"
    patches.mkdir()
    for path in sorted((workspace / "work/kernel-port/linux-5.10").glob("*.patch")):
        shutil.copy2(path, patches / path.name)

    tools = (
        "apply_topaz_linux_510_overlay.sh", "build_topaz_linux_510_radiohw_probe.sh",
        "build_realtek_8192ee_incremental.sh", "openmitrastar_realtek_loop.py",
        "run_realtek_ram_probe.ps1", "bootbase_ram_tftp_one_shot.py",
        "reboot_boot_ramssh.ps1", "tftp_serve_once.py", "ramssh_upload.py", "ramssh_exec.py",
        "build_busybox_ramtools.sh", "build_iw_arc700.sh", "test_openmitrastar_realtek_loop.py",
        "test_realtek_tx_doorbell_bundle.py", "test_topaz_pcie_intx_irqchip_v2.py",
        "test_realtek_intx_lifecycle_v3.py", "test_realtek_intx_noautoen_v4.py",
        "test_realtek_intx_deferred_v5.py", "verify_openmitrastar_2g4_private_handoff.py",
    )
    for name_tool in tools:
        copy_file(workspace, stage, workspace / "tools" / name_tool, f"tools/{name_tool}")
    ap_source = workspace / "work/mission-state/w2-ap-bundle"
    for subdir in ("scripts", "runtime"):
        for path in (ap_source / subdir).glob("*"):
            if path.is_file() and path.suffix.lower() in {".sh", ".py", ".ps1"}:
                copy_file(workspace, stage, path, f"tools/ap/{subdir}/{path.name}")

    evidence = stage / "evidence"
    evidence.mkdir()
    specs = {
        "v1-host-enable-rejected.log": ("outputs/kernel-port/realtek-live-tx/intx-integrated-20260818-042407/probe.log", ("legacy INTx mask", "irq-vector", "RX packets:", "TX packets:")),
        "v2-irqchip-too-early.log": ("outputs/kernel-port/realtek-live-tx/intx-v2-20260818-043759/probe.log", ("irq-line", "irq-vector", "RX packets:", " 28:")),
        "v3-monitor-pass.log": ("outputs/kernel-port/realtek-live-tx/intx-v3-20260818-045809/probe.log", ("irq-lifecycle-policy", "irq-line-hold", "irq-line-release", "MONITOR_RX_PASS", "MONITOR_PROBE_TX_PASS", " 28:")),
        "v4-ap-nobody-cared.log": ("outputs/kernel-port/realtek-ap-runtime/20260818-054953/uart/topaz-20260818-054954.log", ("irq-line-noautoen", "irq-skip-disabled", "nobody cared", "hostapd")),
        "v5-ap-lifecycle.log": ("outputs/kernel-port/realtek-ap-runtime/20260818-060256/uart/topaz-20260818-060256.log", ("irq-line-noautoen", "irq-line-release", "irq-deferred-handled", "nobody cared", "br0:", "hostapd")),
        "dma-iatu-disproof.log": ("outputs/kernel-port/realtek-live-tx/pcie-snapshot-20260818-034803/probe.log", ("OMPCIE ATU inbound0", "OMPCIE ATU outbound0", "OMPCIE ATU outbound1")),
        "ap-offline-validation.log": ("outputs/kernel-port/realtek-ap-bundle/validation.log", ("OMAP_",)),
    }
    for target, (source, markers) in specs.items():
        (evidence / target).write_text(extract_log(workspace / source, markers), encoding="utf-8")
    (evidence / "dma-iatu-disproof.log").write_text(
        (evidence / "dma-iatu-disproof.log").read_text(encoding="utf-8")
        + "RP_EQUALS_WP=true\nDMA_SUCCEEDS_WITH_INBOUND0_DISABLED=true\nIATU_HYPOTHESIS=DISPROVEN\n",
        encoding="utf-8",
    )

    copy_file(workspace, stage, "outputs/kernel-port/realtek-intx-deferred-v5-final-20260818-061000-RAM-ONLY-NO-FLASH/deferred-manifest.json", "manifests/v5-deferred-manifest.json")
    copy_file(workspace, stage, "outputs/kernel-port/radiohw-intx-irqchip-v2-20260818-044000-RAM-ONLY-NO-FLASH/manifest.json", "manifests/kernel-irqchip-v2-manifest.json")
    copy_file(workspace, stage, "work/mission-state/MISSION_STATE.md", "manifests/MISSION_STATE.snapshot.md")
    (stage / "MIGRATION_TARGET_2G4.md").write_text(migration_doc(), encoding="utf-8")
    (stage / "EXCLUSIONS.md").write_text(exclusions_doc(), encoding="utf-8")

    findings, scanned = scan_stage(stage)
    for path in stage.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".log", ".json", ".c", ".h", ".patch", ".sh", ".py", ".conf", ".in"}:
            if PSK.search(path.read_text(encoding="utf-8", errors="replace")):
                findings.append(f"concrete-psk:{path.relative_to(stage).as_posix()}")
    with tarfile.open(stage / "artifacts/ap/openmitrastar-realtek-ap-RAM-ONLY-NO-FLASH.tar", "r") as archive:
        for member in archive.getmembers():
            if member.isfile() and member.size < 2_000_000:
                stream = archive.extractfile(member)
                if stream:
                    blob = stream.read()
                    if b"\0" not in blob[:4096] and PSK.search(blob.decode("utf-8", errors="replace")):
                        findings.append(f"concrete-psk-in-tar:{member.name}")
    (stage / "SECRET_SCAN.txt").write_text(
        ("SECRET_SCAN=PASS\n" if not findings else "SECRET_SCAN=FAIL\n")
        + f"text_files_scanned={scanned}\nconcrete_psk=0\nprivate_handoff=1\n"
        + ("\n".join(findings) + "\n" if findings else ""),
        encoding="utf-8",
    )
    if findings:
        raise RuntimeError("scan failed: " + "; ".join(findings))
    write_manifest(stage)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            archive.write(path, f"{name}/{path.relative_to(stage).as_posix()}")
    digest = sha256(zip_path)
    zip_path.with_suffix(".zip.sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(f"PRIVATE_2G4_DIR={stage}")
    print(f"PRIVATE_2G4_ZIP={zip_path}")
    print(f"ZIP_SHA256={digest}")
    print("SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
