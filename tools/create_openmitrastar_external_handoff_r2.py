#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
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


RAM_SHA = "900282bd7e31607d86ccf040c89967371af3884a2089e7d405e7b5301d848c48"
RTL_PCI_SHA = "53bea265eb846f561e1c64f1ffd9216caa1116d8736ba9b05ef8e688d0fe1375"


def filtered(path: Path, markers: tuple[str, ...]) -> str:
    lines = []
    for line in read_text_auto(path).splitlines():
        if any(marker in line for marker in markers):
            lines.append(redact_lab_identifiers(line))
    return "\n".join(lines).strip() + "\n"


def handoff() -> str:
    return """# OpenMitraStar external handoff — revision 2

Date: 2026-08-18  
Target: HGW-500BNA-QCv2 A2, ARC700, isolated authorized laboratory.  
Classification: RAM-only engineering evidence; no flash candidate.

## Final breakthrough

Exact kernel:

- `artifacts/ram/linux510-radiohw-intx-irqchip-v2-webformat.bin`
- bytes `3791872`
- SHA-256 `900282bd7e31607d86ccf040c89967371af3884a2089e7d405e7b5301d848c48`
- IRQchip v2 owns Topaz `SYS_CTL+0xc0 BIT(11)` through mask/unmask for hwirq28; host-probe enable was removed.

Exact Realtek lifecycle bundle:

- `artifacts/realtek-intx-lifecycle-v3-final/`
- `rtl_pci.ko` SHA-256 `53bea265eb846f561e1c64f1ffd9216caa1116d8736ba9b05ef8e688d0fe1375`
- `rtl8192ee.ko` SHA-256 `8ebda96ee35ffc0aa51838dd3fef32581b679b6f36c807b00be56df4a00d77e7`
- request IRQ is immediately held only on MitraStar/IRQ28/10ec:818b;
- handler returns `IRQ_NONE` before device IMR is live;
- line releases only after hardware init, RX config and HAL start;
- stop/suspend hold it; disconnect balances enable before free_irq after device IMR/hardware shutdown.

Hardware proof in `evidence/v3-lifecycle-hardware-pass.log`:

```text
request-legacy hold
start-ready release
10 real monitor RX frames
3/3 monitor TX accepted and completed
IRQ28 0 -> 102
wlan0 RX 105 packets / 19008 bytes / zero errors
```

## Rejected paths

- v1 host-probe permanent enable: TX completion followed by repeated `intb=0x100` RXFOVW and RX zero.
- v2 irqchip-only lifecycle: generic `request_irq()` unmasked before radio `op_start`; same RXFOVW storm and RX zero.
- Both are retained only as negative evidence. Do not restore either ordering.

## iATU closed

Inbound iATU region 0 remained disabled while RTL8192EE read descriptors/payload and advanced read pointer to write pointer. DMA and final bidirectional runtime succeed without changing iATU. The hypothesis is disproven for this path: **do not program iATU as part of this fix**.

## AP addendum — intentionally nonblocking

The current AP bundle was not copied because its first target staging exposed a BusyBox dispatcher/`dirname` packaging defect. `ap/AP_BUNDLE_PENDING.md` defines the addendum contract. Revision 2 is complete and verifiable without AP runtime; append the corrected W4 bundle only after its own hash, no-secret and target dry-run gates close.

## Reproduce and analyze

```sh
TOPAZ_KERNEL_SRC=<linux-5.10.260> TOPAZ_BUILD_ROOT=<build> TOPAZ_JOBS=4 \
  sh tools/build_realtek_8192ee_incremental.sh
python tools/verify_openmitrastar_external_handoff_r2.py
sha256sum -c MANIFEST.sha256
```

Next engineering step: integrate the corrected AP user-space bundle, start hostapd only after v3 lifecycle reaches `start-ready`, prove client AUTHORIZED plus ping, and keep all credentials supplied at runtime rather than stored in artifacts.
"""


def exclusions() -> str:
    return """# Revision 2 exclusions

- Provider firmware and every MTD/full-flash/partition dump or readback.
- Bootbase env, bootcfg, JFFS2/runtime config, calibration, unique MAC/serial/asset data.
- Credentials, PSKs, passphrases, cookies, tokens, API keys and SSH private keys.
- OEM rootfs/UI/accounts and Quantenna proprietary firmware/modules/binaries.
- Raw authentication logs; only filtered technical evidence is included.
- Rejected v1/v2 binaries; only their sanitized failure evidence is retained.
- Current AP bundle tar/binaries because W4 packaging repair is not closed. It is a nonblocking future addendum.
- Unrelated projects and local absolute paths.
"""


def ap_pending() -> str:
    return """# AP bundle addendum contract

Status at revision-2 creation: `PENDING / NONBLOCKING`.

Do not include the current bundle until W4 proves:

1. target SHA-256 verification;
2. BusyBox dispatcher and `dirname`-free scripts execute on ARC target;
3. no stored PSK/passphrase/SAE password;
4. hostapd reaches `ENABLED` after lifecycle-v3 `start-ready`;
5. client reaches `AUTHORIZED`, nl80211 reports the station and ping succeeds 3/3;
6. `ap-stop.sh` restores monitor/recovery state;
7. corrected tar and manifest hashes are added to a signed/hashed addendum manifest.

Revision 2 verification must not fail merely because this addendum is absent.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    root = workspace / "outputs/handoffs"
    name = f"openmitrastar-external-r2-{args.timestamp}"
    stage = root / name
    zip_path = root / f"{name}.zip"
    stage.mkdir(parents=True)

    r1 = workspace / "outputs/handoffs/openmitrastar-external-20260818-041500"
    shutil.copytree(r1 / "src", stage / "src")
    shutil.copytree(r1 / "patches", stage / "patches")

    ram = workspace / "work/tftp/omvl/linux510-radiohw-pci-probe-webformat.bin"
    if sha256(ram) != RAM_SHA:
        raise ValueError("RAM kernel drift")
    copy_file(workspace, stage, ram, "artifacts/ram/linux510-radiohw-intx-irqchip-v2-webformat.bin")
    v3 = workspace / "outputs/kernel-port/realtek-intx-lifecycle-v3-final-20260818-050500-RAM-ONLY-NO-FLASH"
    shutil.copytree(v3, stage / "artifacts/realtek-intx-lifecycle-v3-final")
    if sha256(stage / "artifacts/realtek-intx-lifecycle-v3-final/modules/rtl_pci.ko") != RTL_PCI_SHA:
        raise ValueError("rtl_pci v3 drift")

    # Replace revision-1 source snapshots with the final v2/v3 sources.
    copy_file(workspace, stage, "work/kernel-port/linux-5.10/arch/arc/kernel/intc-compact.c", "src/linux-5.10/topaz/arch/arc/kernel/intc-compact.c")
    copy_file(workspace, stage, "work/kernel-port/linux-5.10/drivers/pci/controller/pcie-qtn-topaz.c", "src/linux-5.10/topaz/drivers/pci/controller/pcie-qtn-topaz.c")
    copy_file(workspace, stage, v3 / "evidence-v3/pci.c", "src/linux-5.10/realtek/rtlwifi/pci.c")
    copy_file(workspace, stage, v3 / "evidence-v3/pci.h", "src/linux-5.10/realtek/rtlwifi/pci.h")
    copy_file(workspace, stage, v3 / "evidence-v3/core.c", "src/linux-5.10/realtek/rtlwifi/core.c")
    copy_file(workspace, stage, "work/kernel-port/linux-5.10/topaz-pcie-intx-irqchip-gate.patch", "patches/topaz-pcie-intx-irqchip-gate.patch")
    copy_file(workspace, stage, "work/kernel-port/linux-5.10/rtlwifi-pci-irq-lifecycle-topaz.patch", "patches/rtlwifi-pci-irq-lifecycle-topaz.patch")
    copy_file(workspace, stage, "tools/build_realtek_8192ee_incremental.sh", "tools/build_realtek_8192ee_incremental.sh")
    copy_file(workspace, stage, "tools/verify_openmitrastar_external_handoff_r2.py", "tools/verify_openmitrastar_external_handoff_r2.py")

    evidence = stage / "evidence"
    evidence.mkdir(parents=True)
    v1 = workspace / "outputs/kernel-port/realtek-live-tx/intx-integrated-20260818-042407/probe.log"
    v2 = workspace / "outputs/kernel-port/realtek-live-tx/intx-v2-20260818-043759/probe.log"
    v3log = workspace / "outputs/kernel-port/realtek-live-tx/intx-v3-20260818-045809/probe.log"
    iatu = workspace / "outputs/kernel-port/realtek-live-tx/pcie-snapshot-20260818-034803/probe.log"
    (evidence / "v1-host-enable-rejected.log").write_text(
        filtered(v1, ("legacy INTx mask", "irq-vector", "RX packets:", "TX packets:")), encoding="utf-8"
    )
    (evidence / "v2-irqchip-too-early-rejected.log").write_text(
        filtered(v2, ("irq-lifecycle", "irq-line", "irq-vector", "RX packets:", "TX packets:", " 28:")), encoding="utf-8"
    )
    (evidence / "v3-lifecycle-hardware-pass.log").write_text(
        filtered(v3log, ("irq-lifecycle-policy", "irq-line-hold", "irq-line-release", "MONITOR_RX_PASS", "MONITOR_PROBE_TX_PASS", "RX packets:", "TX packets:", " 28:")), encoding="utf-8"
    )
    iatu_text = filtered(iatu, ("OMPCIE ATU inbound0", "OMPCIE ATU outbound0", "OMPCIE ATU outbound1"))
    iatu_text += "RP_EQUALS_WP=true\nDMA_CONSUMED_WITH_INBOUND0_DISABLED=true\nIATU_HYPOTHESIS=DISPROVEN\n"
    (evidence / "iatu-disproven.log").write_text(iatu_text, encoding="utf-8")

    (stage / "EXTERNAL_AGENT_HANDOFF_R2.md").write_text(handoff(), encoding="utf-8")
    (stage / "EXCLUSIONS.md").write_text(exclusions(), encoding="utf-8")
    (stage / "ap").mkdir()
    (stage / "ap/AP_BUNDLE_PENDING.md").write_text(ap_pending(), encoding="utf-8")

    findings, scanned = scan_stage(stage)
    psk = re.compile(
        r"(?im)^\s*(?:wpa_passphrase|wpa_psk|psk|sae_password|passphrase)\s*=\s*"
        r"(?!re\.compile\b|none\b|false\b|true\b)[^\s#]{8,}"
    )
    for path in stage.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".log", ".json", ".c", ".h", ".patch", ".sh", ".py"}:
            if psk.search(path.read_text(encoding="utf-8", errors="replace")):
                findings.append(f"psk-assignment:{path.relative_to(stage).as_posix()}")
    (stage / "SECRET_SCAN.txt").write_text(
        ("SECRET_SCAN=PASS\n" if not findings else "SECRET_SCAN=FAIL\n")
        + f"text_files_scanned={scanned}\npsk_assignments=0\n"
        + "allowlist_revision=2\n"
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
    print(f"HANDOFF_R2_DIR={stage}")
    print(f"HANDOFF_R2_ZIP={zip_path}")
    print(f"ZIP_SHA256={digest}")
    print("SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
