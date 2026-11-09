#!/usr/bin/env python3
"""Create a sanitized, allowlist-only OpenMitraStar external-agent handoff."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path


RAM_SHA256 = "ed1605ddd99b92c5b99851b26fe6a6b79d81692e919277191114ccef73bbbd16"
BUNDLE_REL = Path(
    "outputs/kernel-port/realtek-tx-doorbell/20260818-034233-RAM-ONLY-NO-FLASH"
)
WSL_KERNEL = Path(
    r"\\wsl.localhost\podman-mem9-tidb\home\user\mitrastar-linux-5.10.260"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_auto(path: Path) -> str:
    blob = path.read_bytes()
    if blob.startswith((b"\xff\xfe", b"\xfe\xff")):
        return blob.decode("utf-16")
    if blob[:4096].count(b"\0") > max(8, len(blob[:4096]) // 8):
        return blob.decode("utf-16-le", errors="replace")
    return blob.decode("utf-8", errors="replace")


def redact_lab_identifiers(line: str) -> str:
    line = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "<mac-redacted>", line)
    line = re.sub(r"\b192\.168\.1\.\d{1,3}\b", "<lab-ip-redacted>", line)
    return line


def copy_file(workspace: Path, stage: Path, source: str | Path, target: str) -> None:
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = workspace / source_path
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    target_path = stage / target
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def build_realtek_log(workspace: Path) -> str:
    source = workspace / "outputs/kernel-port/realtek-live-tx/20260818-033040/probe.log"
    selected: list[str] = []
    for line in read_text_auto(source).splitlines():
        stripped = line.strip()
        if (
            stripped.startswith("===")
            or stripped.startswith("28:")
            or "MONITOR_PROBE_TX_PASS" in line
            or "TX packets:" in line
            or "OMRTL stage=tx-" in line
            or "OMRTL stage=pci-tx-" in line
        ):
            selected.append(redact_lab_identifiers(line))
    return "\n".join(selected).strip() + "\n"


def build_iatu_log(workspace: Path) -> str:
    source = workspace / (
        "outputs/kernel-port/realtek-live-tx/pcie-snapshot-20260818-034803/probe.log"
    )
    selected: list[str] = []
    for line in read_text_auto(source).splitlines():
        if any(
            marker in line
            for marker in (
                "qtn-topaz-pcie",
                "pci 0000:00:00.0",
                "INTx IRQ 28",
                "OMPCIE snapshot",
                "OMPCIE ATU",
            )
        ):
            selected.append(redact_lab_identifiers(line))
    return "\n".join(selected).strip() + "\n"


def handoff_markdown() -> str:
    return """# OpenMitraStar external agent handoff

Date: 2026-08-18  
Target: MitraStar HGW-500BNA-QCv2 A2, ARC700, authorized isolated laboratory.  
Classification: engineering handoff, RAM-only evidence; **not flash-ready**.

## Exact executed RAM image

`artifacts/ram/linux510-radiohw-pci-probe-webformat.bin`

- bytes: `3791872`
- SHA-256: `ed1605ddd99b92c5b99851b26fe6a6b79d81692e919277191114ccef73bbbd16`
- kernel release observed on hardware: `5.10.260-openmitrastar-radiohw`
- Bootbase path: TFTP to RAM, `iminfo`, then `bootm`; no flash required.

## Proven state

- Linux 5.10 boots on hardware from the exact RAM image above.
- Ethernet and key-only RAM SSH work.
- Topaz PCI host enumerates Realtek `10ec:818b` at BAR2 `0xc0000000`, legacy INTx IRQ28.
- Patched `rtl8192ee` crosses EEPROM, firmware, PHY/MAC init and `probe-pass`.
- A monitor-mode `wlan0` exists.
- Three probe-request frames enter `rtl_pci_tx`, occupy TX queue 6 descriptors 0..2 and advance the software queue.
- The previous run still showed IRQ28 `0 -> 0` and interface `TX packets 0 -> 0`.
- The instrumented modules in `artifacts/realtek-instrumented/` have not yet run on hardware.

Evidence labels: the statements above are PROVEN by the included sanitized logs except the root cause below, which remains a candidate.

## Current root-cause candidate: inbound iATU disabled

The read-only iATU snapshot preserved and restored the viewport and reported:

```text
OMPCIE ATU inbound0 ... cr1=0x00000000 cr2=0x00000000 ... limit=0x0000ffff ...
OMPCIE ATU outbound0 ... cr1=0x00000004 cr2=0x90000000 ...
OMPCIE ATU outbound1 ... cr1=0x00000000 cr2=0x80000000 ...
```

Inbound region 0 is therefore disabled (`cr2` enable bit clear), while the inherited outbound config/memory windows are enabled. This is a strong candidate for endpoint DMA writes/reads never reaching ARC DDR, but it is **not yet a complete proof**. First correlate the newly logged descriptor and packet DMA addresses with the endpoint-visible PCIe address space.

Do not program iATU blindly. Determine the required inbound PCIe base, ARC DDR target and limit from live DMA addresses plus OEM source contracts, then make one minimal, reversible RAM-only change.

## Instrumented Realtek bundle

Path: `artifacts/realtek-instrumented/`

Changed modules:

- `modules/rtl_pci.ko` — SHA-256 `0e16227671fcd0ddea1fd6ce62387c9b1dc10d0a6bb6ef734cb480974a0b606c`
- `modules/rtl8192ee.ko` — SHA-256 `8ebda96ee35ffc0aa51838dd3fef32581b679b6f36c807b00be56df4a00d77e7`

The instrumentation logs descriptor/BD CPU and DMA addresses, raw words and OWN state; the queue TXBD index before/after the real WP write; PCIe/ISR/TX/RX DMA registers; and snapshots around the otherwise empty `rtl92ee_tx_polling()`.

Load order is in `artifacts/realtek-instrumented/LOAD_ORDER.txt`. Verify every file against its `UPLOAD_SHA256SUMS` before loading.

## Source map

- `src/linux-5.10/topaz/`: current Topaz PCIe host, read-only iATU probe, IRQ, cache/DMA and DTS sources.
- `src/linux-5.10/realtek/`: exact instrumented rtlwifi/RTL8192EE sources and supporting headers.
- `patches/`: selected Topaz ARC/DMA/IRQ and rtlwifi patches used by the current build.
- `src/oem-gpl-minimal/`: minimal GPL source fossils for OEM PCIe, ARC DMA/IRQ and qdrv SoC comparison. No OEM binaries or device configuration.
- `evidence/`: sanitized Realtek TX and iATU logs.

## Build

The helper is incremental and builds modules only:

```sh
TOPAZ_KERNEL_SRC=<linux-5.10.260-tree> \
TOPAZ_BUILD_ROOT=<existing-out-of-tree-build> \
TOPAZ_JOBS=4 \
sh tools/build_realtek_8192ee_incremental.sh
```

Static analysis examples:

```sh
arc-linux-readelf -h artifacts/realtek-instrumented/modules/rtl_pci.ko
arc-linux-readelf -h artifacts/realtek-instrumented/modules/rtl8192ee.ko
arc-linux-objdump -dr artifacts/realtek-instrumented/modules/rtl_pci.ko
arc-linux-objdump -dr artifacts/realtek-instrumented/modules/rtl8192ee.ko
python tools/verify_openmitrastar_external_handoff.py
sha256sum -c MANIFEST.sha256
```

Expected module contract: ELF32, little-endian, ARCompact/ARC700 v4 ABI, vermagic `5.10.260-openmitrastar-radiohw mod_unload ARC700`.

## Next discriminating RAM-only test

1. Boot the pinned RAM image by the already-proven Bootbase/TFTP path.
2. Upload the complete bundle and verify `UPLOAD_SHA256SUMS` on target.
3. Load dependencies in `LOAD_ORDER.txt`; load only the instrumented `rtl_pci.ko` and `rtl8192ee.ko` from this handoff.
4. Bring `wlan0` up in monitor mode and inject exactly three probe requests.
5. Capture UART before loading modules and retain all new markers:
   - `pci-tx-desc-filled`, `pci-tx-bd-filled`;
   - `tx-doorbell-pre`, `tx-doorbell-post`;
   - `pci-tx-doorbell-done`;
   - `tx-poll-enter`, `tx-poll-exit`;
   - `pci-tx-after-poll`.
6. Compare BD packet/descriptor DMA addresses with the inbound iATU aperture and observe whether TXBD RP, ISR, TXDMA status, IRQ28 or TX packet counters move.
7. Only if the address-space mismatch is demonstrated, design a minimal RAM-only inbound iATU setup with save/restore and a hard STOP before any persistent integration.

## Safety boundary

This archive contains no flash command, no raw MTD image, no environment/config backup, no calibration data, no private key and no OEM proprietary binary. It does contain an executed RAM image, GPL-compatible source fossils, Linux modules and public firmware required by the current Realtek bundle.
"""


def exclusions_markdown() -> str:
    return """# Exact exclusions

The handoff was built from an explicit allowlist. The following were excluded:

1. Immutable provider firmware `Firmware_para_HGW-500BNA-QCv2_..._webformat.bin`.
2. `hgw500bna-qcv2-firmware-dump-verified/`, its ZIP, every MTD/raw/full-flash image and every partition readback.
3. Bootbase environments, `bootcfg`, slot backups/readbacks and SPI/CH341A artifacts.
4. `romfile.xml`, OEM configuration exports, runtime data/JFFS2, MAC/serial/asset identifiers, calibration and device-specific regulatory data.
5. `Accesos.txt`, credentials, passwords, tokens, cookies, API keys, private/public operator account material and SSH private keys.
6. OEM rootfs, web UI, user database, `/etc/shadow`, `/etc/passwd` copies and support packages.
7. Quantenna OEM firmware blobs, proprietary modules and extracted binaries. Only the named GPL source fossils were included.
8. Full raw UART/authentication logs. Only filtered technical extracts without authentication lines were included.
9. Local absolute Windows/WSL paths and unrelated Samsung/GPT2742/Process Studio artifacts.

Allowed configuration exception: the Realtek bundle's `kernel.config` is a Linux build configuration, not device/runtime configuration.
"""


TEXT_SUFFIXES = {
    ".c", ".h", ".s", ".S", ".txt", ".md", ".json", ".patch",
    ".sh", ".py", ".config", "", ".dts", ".dtsi", ".mk",
}

SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai-like-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "bearer-token": re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.I),
    "secret-env": re.compile(r"(?:OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|NOTION_TOKEN)\s*=", re.I),
    "local-user-path": re.compile(r"/workspace/user-home\\\\wsl\.localhost", re.I),
}

DENIED_NAME_PATTERNS = (
    "mtdblock", "full_flash", "firmware-dump", "romfile", "accesos",
    "bootcfg", "calibration", "private_key", "id_rsa", ".pem", ".pfx",
)


def scan_stage(stage: Path) -> tuple[list[str], int]:
    findings: list[str] = []
    scanned_text = 0
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        rel = path.relative_to(stage).as_posix()
        lowered = rel.lower()
        for denied in DENIED_NAME_PATTERNS:
            if denied in lowered:
                findings.append(f"denied-filename:{rel}:{denied}")
        if path.suffix not in TEXT_SUFFIXES and path.name not in {
            "Makefile", "Kconfig", "LOAD_ORDER.txt", "SHA256SUMS", "UPLOAD_SHA256SUMS"
        }:
            continue
        blob = path.read_bytes()
        if b"\0" in blob[:4096]:
            continue
        text = blob.decode("utf-8", errors="replace")
        scanned_text += 1
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"content:{rel}:{name}")
    return findings, scanned_text


def write_manifest(stage: Path) -> None:
    lines: list[str] = []
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        rel = path.relative_to(stage).as_posix()
        if rel == "MANIFEST.sha256":
            continue
        lines.append(f"{sha256(path)}  {rel}")
    (stage / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    handoff_root = workspace / "outputs/handoffs"
    name = f"openmitrastar-external-{args.timestamp}"
    stage = handoff_root / name
    zip_path = handoff_root / f"{name}.zip"
    if stage.exists() or zip_path.exists():
        raise FileExistsError(f"handoff already exists: {name}")
    stage.mkdir(parents=True)

    ram_source = workspace / "work/tftp/omvl/linux510-radiohw-pci-probe-webformat.bin"
    if sha256(ram_source) != RAM_SHA256:
        raise ValueError("RAM image hash drift")
    copy_file(workspace, stage, ram_source, "artifacts/ram/linux510-radiohw-pci-probe-webformat.bin")

    shutil.copytree(workspace / BUNDLE_REL, stage / "artifacts/realtek-instrumented")

    modern_sources = {
        "work/kernel-port/linux-5.10/drivers/pci/controller/pcie-qtn-topaz.c": "src/linux-5.10/topaz/drivers/pci/controller/pcie-qtn-topaz.c",
        "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-pcie-ro.c": "src/linux-5.10/topaz/drivers/misc/qtn-topaz-pcie-ro.c",
        "work/kernel-port/pcie-snapshot/qtn_topaz_pcie_snapshot.c": "src/linux-5.10/topaz/drivers/misc/qtn_topaz_pcie_snapshot.c",
        "work/kernel-port/pcie-snapshot/Makefile": "src/linux-5.10/topaz/drivers/misc/pcie-snapshot-Makefile",
        "work/kernel-port/linux-5.10/arch/arc/kernel/intc-compact.c": "src/linux-5.10/topaz/arch/arc/kernel/intc-compact.c",
        "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts": "src/linux-5.10/topaz/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts",
    }
    for source, target in modern_sources.items():
        copy_file(workspace, stage, source, target)

    wsl_sources = {
        "arch/arc/mm/cache.c": "src/linux-5.10/topaz/arch/arc/mm/cache.c",
        "kernel/dma/direct.c": "src/linux-5.10/topaz/kernel/dma/direct.c",
        "kernel/dma/pool.c": "src/linux-5.10/topaz/kernel/dma/pool.c",
        "drivers/net/wireless/realtek/rtlwifi/pci.c": "src/linux-5.10/realtek/rtlwifi/pci.c",
        "drivers/net/wireless/realtek/rtlwifi/efuse.c": "src/linux-5.10/realtek/rtlwifi/efuse.c",
        "drivers/net/wireless/realtek/rtlwifi/wifi.h": "src/linux-5.10/realtek/rtlwifi/wifi.h",
        "drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c": "src/linux-5.10/realtek/rtlwifi/rtl8192ee/trx.c",
        "drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.h": "src/linux-5.10/realtek/rtlwifi/rtl8192ee/trx.h",
        "drivers/net/wireless/realtek/rtlwifi/rtl8192ee/hw.c": "src/linux-5.10/realtek/rtlwifi/rtl8192ee/hw.c",
        "drivers/net/wireless/realtek/rtlwifi/rtl8192ee/reg.h": "src/linux-5.10/realtek/rtlwifi/rtl8192ee/reg.h",
        "drivers/net/wireless/realtek/rtlwifi/rtl8192ee/sw.c": "src/linux-5.10/realtek/rtlwifi/rtl8192ee/sw.c",
    }
    for source, target in wsl_sources.items():
        copy_file(workspace, stage, WSL_KERNEL / source, target)

    patches = (
        "cache-dma-callbacks-topaz.patch",
        "cache-line-callback-topaz.patch",
        "late-irq-handoff-topaz.patch",
        "skip-atomic-dma-pool-topaz.patch",
        "rtlwifi-probe-trace-topaz.patch",
        "rtlwifi-arc-unaligned-efuse-topaz.patch",
        "rtlwifi-arc-align-efuse-dev-addr-topaz.patch",
        "rtl8192ee-module-init-trace-topaz.patch",
        "rtlwifi-runtime-trace-topaz.patch",
        "rtlwifi-tx-trace-topaz.patch",
    )
    for name_part in patches:
        copy_file(
            workspace,
            stage,
            workspace / "work/kernel-port/linux-5.10" / name_part,
            f"patches/{name_part}",
        )

    oem_sources = {
        "work/sources/Quantenna-GPL/drivers/ruby/pcibios.c": "src/oem-gpl-minimal/drivers/ruby/pcibios.c",
        "work/sources/Quantenna-GPL/drivers/ruby/pcibios.h": "src/oem-gpl-minimal/drivers/ruby/pcibios.h",
        "work/sources/Quantenna-GPL/drivers/ruby/irq.c": "src/oem-gpl-minimal/drivers/ruby/irq.c",
        "work/sources/Quantenna-GPL/drivers/ruby/plat_irq.h": "src/oem-gpl-minimal/drivers/ruby/plat_irq.h",
        "work/sources/Quantenna-GPL/drivers/ruby/dmautil.c": "src/oem-gpl-minimal/drivers/ruby/dmautil.c",
        "work/sources/Quantenna-GPL/drivers/ruby/dma_cache_ops.h": "src/oem-gpl-minimal/drivers/ruby/dma_cache_ops.h",
        "work/sources/Quantenna-GPL/drivers/ruby/plat_dma_addr.h": "src/oem-gpl-minimal/drivers/ruby/plat_dma_addr.h",
        "work/sources/Quantenna-GPL/linux_2.6.35.12/arch/arc/mm/dma.c": "src/oem-gpl-minimal/linux_2.6.35.12/arch/arc/mm/dma.c",
        "work/sources/Quantenna-GPL/linux_2.6.35.12/arch/arc/drivers/arc700_pci.c": "src/oem-gpl-minimal/linux_2.6.35.12/arch/arc/drivers/arc700_pci.c",
        "work/sources/Quantenna-GPL/drivers/qdrv/qdrv_soc.c": "src/oem-gpl-minimal/drivers/qdrv/qdrv_soc.c",
        "work/sources/Quantenna-GPL/drivers/qdrv/qdrv_soc.h": "src/oem-gpl-minimal/drivers/qdrv/qdrv_soc.h",
        "work/sources/Quantenna-GPL/include/qtn/dmautil.h": "src/oem-gpl-minimal/include/qtn/dmautil.h",
        "work/sources/Quantenna-GPL/common/ruby_pcie_bda.h": "src/oem-gpl-minimal/common/ruby_pcie_bda.h",
    }
    for source, target in oem_sources.items():
        copy_file(workspace, stage, source, target)

    for source, target in {
        "tools/build_realtek_8192ee_incremental.sh": "tools/build_realtek_8192ee_incremental.sh",
        "tools/verify_openmitrastar_external_handoff.py": "tools/verify_openmitrastar_external_handoff.py",
        "work/mission-state/W2_REALTEK_TX_DOORBELL_INSTRUMENTATION.md": "docs/W2_REALTEK_TX_DOORBELL_INSTRUMENTATION.md",
    }.items():
        copy_file(workspace, stage, source, target)

    (stage / "evidence").mkdir(parents=True, exist_ok=True)
    (stage / "evidence/realtek-tx-sanitized.log").write_text(
        build_realtek_log(workspace), encoding="utf-8"
    )
    (stage / "evidence/pcie-iatu-sanitized.log").write_text(
        build_iatu_log(workspace), encoding="utf-8"
    )
    (stage / "EXTERNAL_AGENT_HANDOFF.md").write_text(handoff_markdown(), encoding="utf-8")
    (stage / "EXCLUSIONS.md").write_text(exclusions_markdown(), encoding="utf-8")

    findings, scanned_text = scan_stage(stage)
    scan_lines = [
        "SECRET_SCAN=PASS" if not findings else "SECRET_SCAN=FAIL",
        f"files_total={sum(1 for p in stage.rglob('*') if p.is_file())}",
        f"text_files_scanned={scanned_text}",
        "method=explicit allowlist + denied filename scan + high-confidence content patterns",
        "binary_payloads=RAM image, Linux modules and rtl8192ee public firmware only",
    ]
    if findings:
        scan_lines.extend(findings)
    (stage / "SECRET_SCAN.txt").write_text("\n".join(scan_lines) + "\n", encoding="utf-8")
    if findings:
        raise RuntimeError("secret scan failed:\n" + "\n".join(findings))

    write_manifest(stage)
    handoff_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            archive.write(path, f"{name}/{path.relative_to(stage).as_posix()}")
    zip_hash = sha256(zip_path)
    zip_path.with_suffix(".zip.sha256").write_text(
        f"{zip_hash}  {zip_path.name}\n", encoding="utf-8"
    )
    print(f"HANDOFF_DIR={stage}")
    print(f"HANDOFF_ZIP={zip_path}")
    print(f"ZIP_SHA256={zip_hash}")
    print("SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
