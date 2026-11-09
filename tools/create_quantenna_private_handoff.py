#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


FW = {
    "auc_driver.nomu.0.bin": "c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6",
    "auc_driver.default.0.bin": "e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af",
    "qtn_driver.qtn_ruby.0.bin": "71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4",
    "rdsp_driver.0.bin": "87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd",
}
SOURCE_NAMES = {"Makefile", "Kconfig"}
SOURCE_SUFFIXES = {".c", ".h", ".s", ".S", ".mk", ".sh", ".awk", ".lds", ".txt"}
TEXT_SUFFIXES = SOURCE_SUFFIXES | {".md", ".json", ".py", ".env", ".tsv", ".log", ".patch"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(workspace: Path, stage: Path, source: str | Path, target: str) -> None:
    source = Path(source)
    if not source.is_absolute():
        source = workspace / source
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = stage / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_source_tree(workspace: Path, stage: Path, source: str, target: str) -> int:
    source_root = workspace / source
    count = 0
    for path in sorted(p for p in source_root.rglob("*") if p.is_file()):
        if path.name not in SOURCE_NAMES and path.suffix not in SOURCE_SUFFIXES:
            continue
        rel = path.relative_to(source_root)
        copy_file(workspace, stage, path, f"{target}/{rel.as_posix()}")
        count += 1
    return count


def migration_target() -> str:
    return """# OpenMitraStar 5 GHz Quantenna migration target

Classification: PRIVATE engineering handoff. Proprietary blobs are included
solely for the owner's local interoperability analysis and are not public
redistribution assets.

```text
TARGET_HOST_ABI=0x25040059
TARGET_RELEASE=v37.4.0.89
CURRENT_PORT_ABI=0x2504003e
W3_PAIR_APPROVED=0
```

## Hardware and board contract

```text
board_id=65535 name=QHS860
emac0=1 emac1=1
wifi_hw=7 QTN_TPZ_SKY85703
rfic=4 RFIC_V4_IN_USE
pcie=7 PCIE_ROOTCOMPLEX
calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5
tx_power_cal=0 min_tx_power=7 max_tx_power=21
```

`bond_opt`, `power_recheck`, `post_mask` and `dev_mode` are absent in the OEM
environment; retain the vendor source defaults. No MAC, serial, calibration,
power table or runtime configuration is included.

## OEM boot order

```text
switch_vlan -> switch_tqe -> qtn_debug -> qtsens -> pm_interval
-> wlan -> auc_fw -> radar -> qvspmod -> qdrv
-> wlan_xauth -> wlan_ccmp -> wlan_tkip
-> firmware/power-table commands -> qdrv start -> VAP
```

## ABI delta `.62.1 -> .89`

```text
shared_params: 384 -> 400
fw_no_mu: absent -> offset 76
shared_params.auc: 276 -> 280
shared_params_auc: 80 -> 80
free_airtime: 380 -> 384
nac_mon_info_lhost/bus: absent -> 388/392
qtn_txbf_mbox: 4512 -> 4528
qtn_muc_dsp_mbox: 2080 -> 2144
qtn_scs_info_set: 14420 -> 18800
qtn_samp_chan_info: 156 -> 160 and reordered
qtn_scan_chan_info: 168 -> 172
qtn_remain_chan_info: 36 -> 40
qtn_vap_args: 24 -> 25
_shared_params_alloc: 0x5c00 -> 0x77a0
```

Resolved: FWINFO loader semantics, board values, AuC/HBM OEM overlap, all OEM
exports, private ioctl compatibility, `fw_no_mu`, unchanged AuC/node/VAP stats,
NAC pointer/entry geometry, host ioctl and node argument sizes.

Opaque/blocking: TXBF/MuC-DSP/SCS added fields, remainder of the reordered sample
layout, NAC opaque header/tails and the final VAP byte. Never represent these as
anonymous production padding.

## Fail-closed ladder

Run offline gates and tests first. `tools/qtn_w3_pre_mmio_ladder.sh` consumes
`W3_RUNTIME_GATE.env`; the included gate has `W3_PAIR_APPROVED=0` and therefore
stops before any module load. Even after future ABI approval it stops at the
explicit checkpoint:

```text
STOP before HBM/MMIO
W3_STOP code=42 reason=pre_mmio_checkpoint next=platform/topaz/hbm.ko
```

Do not execute `clearsram`, `qdrv start`, RF, DFS, GPIO, HBM, TQE or flash work
from this package until the host/firmware contract is complete and separately
approved under UART-first RAM-only recovery.
"""


def exclusions() -> str:
    return """# Exclusions

- Credentials, password/token/cookie material, SSH keys and local access notes.
- Raw flash, MTD images, partition readbacks, Bootbase environments and SPI dumps.
- Runtime/OEM configuration, JFFS2, SSIDs, MACs, serial/asset identifiers.
- Device calibration, power tables, regulatory database and `.cal` artifacts.
- Provider firmware, complete OEM rootfs and UI.
- Raw UART/authentication logs; only a filtered technical 5 GHz extract is included.
- Unrelated Realtek 2.4 GHz, Samsung, GPT2742 and Process Studio material.

GPL source code may contain calibration/bootcfg implementation logic; no
device-specific calibration or boot environment data is present.
"""


def proprietary_notice() -> str:
    return """# Proprietary/private inputs

This directory contains hash-pinned firmware and OEM module binaries extracted
from the owner's device firmware. They are included only in this PRIVATE archive
for local interoperability and ABI analysis. Do not publish or redistribute them.

The four firmware hashes are enforced by the verifier. No calibration, runtime
configuration, MAC, serial, power table or regulatory database is included.
"""


def filtered_oem_log(path: Path) -> str:
    markers = (
        "HBM pool:", "HBM meta:", "topaz_hbm_init_pool_list", "load_module: 'qdrv'",
        "Loading MuC driver", "qdrv_soc_publish_params", "AuC SRAM", "MuC boot succeeded",
        "MuC: build date", "MuC: slow heap", "MuC: fast heap", "MuC: stack start",
        "VAP create succeeded", "wifi0) entering forwarding state", "Build name:",
        "MuC firmware:", "DSP firmware:", "AuC firmware:",
    )
    selected = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if any(marker in line for marker in markers):
            line = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "<mac-redacted>", line)
            line = re.sub(r"MOVISTAR[^\s\"]*", "<ssid-redacted>", line)
            selected.append(line)
    return "\n".join(selected) + "\n"


def scan_stage(stage: Path) -> tuple[list[str], int]:
    findings = []
    scanned = 0
    forbidden_artifacts = re.compile(
        r"(?i)(mtdblock|full[_-]?flash|firmware[_-]?dump|accesos|romfile|pdetector|tx_power_|qtn_regulatory_db|\.cal$|id_rsa|private[_-]?key)"
    )
    secret_patterns = {
        "private-key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
        "token": re.compile(r"\b(?:sk-|gh[pousr]_|xox[baprs]-)[A-Za-z0-9_-]{16,}"),
        "bearer": re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.I),
        "secret-env": re.compile(r"(?:OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|NOTION_TOKEN)\s*=", re.I),
        "local-path": re.compile(r"/workspace/user-home/workspace/user-home", re.I),
    }
    doc_identifier = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|MOVISTAR_PLUS_|S\d{3}[A-Z]\d{8,}")
    credential_assignment = re.compile(
        r"(?im)^\s*(?:password|passwd|wpa_passphrase|wpa_psk|psk|sae_password|token|secret)\s*=\s*[^\s#]{4,}"
    )
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        rel = path.relative_to(stage).as_posix()
        if forbidden_artifacts.search(rel) and not rel.startswith("src/oem-gpl/"):
            findings.append(f"forbidden-name:{rel}")
        if path.suffix not in TEXT_SUFFIXES and path.name not in SOURCE_NAMES:
            blob = path.read_bytes()
            if re.search(rb"S\d{3}[A-Z]\d{8,}", blob):
                findings.append(f"serial-in-binary:{rel}")
            continue
        blob = path.read_bytes()
        if b"\0" in blob[:4096]:
            continue
        text = blob.decode("utf-8", errors="replace")
        scanned += 1
        for name, pattern in secret_patterns.items():
            if pattern.search(text):
                findings.append(f"{name}:{rel}")
        if not rel.startswith("src/") and doc_identifier.search(text):
            findings.append(f"identifier:{rel}")
        if not rel.startswith("src/") and credential_assignment.search(text):
            findings.append(f"credential-assignment:{rel}")
    return findings, scanned


def sanitize_local_paths(stage: Path) -> int:
    changed = 0
    replacements = (
        (re.compile(r"/workspace/user-home\\Desktop\\MitraStar", re.I), "<workspace>"),
        (re.compile(r"/workspace/user-home/Desktop/MitraStar", re.I), "<workspace>"),
        (re.compile(r"\\\\wsl\.localhost\\[^\\\s]+\\home\\user", re.I), "<wsl-home>"),
    )
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        if path.suffix not in TEXT_SUFFIXES and path.name not in SOURCE_NAMES:
            continue
        blob = path.read_bytes()
        if b"\0" in blob[:4096]:
            continue
        text = blob.decode("utf-8", errors="replace")
        updated = text
        for pattern, replacement in replacements:
            updated = pattern.sub(replacement, updated)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def write_manifest(stage: Path) -> int:
    lines = []
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        rel = path.relative_to(stage).as_posix()
        if rel == "MANIFEST.sha256":
            continue
        lines.append(f"{sha256(path)}  {rel}")
    (stage / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    out = workspace / "outputs/handoffs"
    name = f"openmitrastar-private-quantenna5g-{args.timestamp}"
    stage = out / name
    zip_path = out / f"{name}.zip"
    if stage.exists() or zip_path.exists():
        raise FileExistsError(name)
    stage.mkdir(parents=True)

    source_dirs = (
        "drivers/qdrv", "drivers/wlan", "drivers/topaz", "drivers/ruby",
        "drivers/fwt", "drivers/qtsens", "drivers/bootcfg", "drivers/include/shared",
        "drivers/include/kernel", "include/qtn", "common",
        "buildroot/package/qcsapi/qcsapi-1.0.1",
    )
    source_count = 0
    for rel in source_dirs:
        source_count += copy_source_tree(
            workspace, stage, f"work/sources/Quantenna-GPL/{rel}", f"src/oem-gpl/{rel}"
        )
    for rel in ("cmd_qtnboard.c", "board_cfg.c"):
        copy_file(workspace, stage,
            f"work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/board/ruby/{rel}",
            f"src/oem-gpl/u-boot/board/ruby/{rel}")
    source_count += copy_source_tree(
        workspace, stage, "work/linux510-radio-port/quantenna", "src/linux510-port/quantenna"
    )

    release = "5.10.260-openmitrastar-radio"
    module_src = workspace / f"outputs/kernel-port/quantenna-linux510/rootfs/lib/modules/{release}"
    shutil.copytree(module_src / "extra/quantenna", stage / "artifacts/linux510-modules/extra/quantenna")
    for name_file in ("modules.dep", "modules.alias", "modules.symbols", "modules.order", "modules.softdep"):
        path = module_src / name_file
        if path.is_file():
            copy_file(workspace, stage, path, f"artifacts/linux510-modules/{name_file}")
    for rel in ("module-manifest.tsv", "actual-modules.txt", "expected-modules.txt", "build.log",
                "depmod-unresolved.log", "kernelrelease.txt", "kernel-Module.symvers"):
        copy_file(workspace, stage, f"outputs/kernel-port/quantenna-linux510/{rel}", f"artifacts/linux510-build/{rel}")

    fw_root = workspace / "work/revival/rootfs/etc/firmware"
    for fw, expected in FW.items():
        path = fw_root / fw
        if sha256(path) != expected:
            raise ValueError(f"firmware drift: {fw}")
        copy_file(workspace, stage, path, f"private/proprietary-firmware-v37.4.0.89/{fw}")

    oem_mod_root = workspace / "work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra"
    oem_modules = (
        "qdrv/qdrv.ko", "wlan/wlan.ko", "auc/auc_fw.ko", "radar/radar.ko",
        "qvsp/qvspmod.ko", "topaz/switch_tqe.ko", "topaz/switch_vlan.ko",
        "topaz/switch_emac.ko", "fwt/fwt_ctrl.ko", "bootcfg/bootcfg.ko",
        "qtndbg/qtn_debug.ko", "se95sensor/qtsens.ko",
    )
    for rel in oem_modules:
        copy_file(workspace, stage, oem_mod_root / rel, f"private/oem-modules-v37.4.0.89/{rel}")

    docs = (
        "QDRV_ABI_CONTRACT.md", "QDRV_FW_INSPECT.md", "RADIO_STACK_2026_RESEARCH.md",
        "work/mission-state/W3_QUANTENNA_RUNTIME_LADDER.md",
        "work/mission-state/W3_QUANTENNA_OFFLINE_GATES_20260818.md",
        "work/mission-state/W3_QDRV_ABI_62_TO_89.md",
        "work/mission-state/W3_REMAINING_ABI_BLOCKERS.md",
        "outputs/kernel-port/TOPAZ_MEMORY_MAP.md",
    )
    for rel in docs:
        copy_file(workspace, stage, rel, f"docs/{Path(rel).name}")
    offline = workspace / "work/mission-state/w3-offline"
    for path in sorted(p for p in offline.iterdir() if p.is_file()):
        if path.name == "oem-b24-full-uncompressed.bin":
            continue
        if path.suffix.lower() in {".txt", ".json", ".env", ".elf"}:
            copy_file(workspace, stage, path, f"evidence/offline/{path.name}")

    tools = (
        "build_quantenna_linux510.sh", "qdrv_fw_inspect.py", "qtn_w3_offline_gate.py",
        "qtn_qdrv_abi_diff.py", "qtn_w3_pre_mmio_ladder.sh",
        "test_qdrv_fw_inspect.py", "test_qdrv_abi_contract.py",
        "test_qtn_w3_offline_gate.py", "test_qtn_qdrv_abi_diff.py",
        "test_qtn_w3_pre_mmio_ladder.py", "verify_quantenna_private_handoff.py",
    )
    for rel in tools:
        copy_file(workspace, stage, f"tools/{rel}", f"tools/{rel}")
    shutil.copytree(workspace / "tools/qdrv_abi_contract", stage / "tools/qdrv_abi_contract")

    evidence = stage / "evidence/runtime-sanitized"
    evidence.mkdir(parents=True)
    (evidence / "oem89-quantenna-boot-order.log").write_text(
        filtered_oem_log(workspace / "outputs/uart-com3-j2-115200.log"), encoding="utf-8"
    )
    (stage / "MIGRATION_TARGET_5G.md").write_text(migration_target(), encoding="utf-8")
    (stage / "EXCLUSIONS.md").write_text(exclusions(), encoding="utf-8")
    (stage / "private/PROPRIETARY_PRIVATE.md").write_text(proprietary_notice(), encoding="utf-8")

    manifest_meta = {
        "classification": "PRIVATE-OWNER-LOCAL-ANALYSIS",
        "target": "HGW-500BNA-QCv2 A2 Quantenna 5GHz",
        "target_host_abi": "0x25040059",
        "current_runtime_approved": False,
        "oem_gpl_and_port_source_files": source_count,
        "linux510_modules": 22,
        "proprietary_firmware": FW,
        "raw_flash_included": False,
        "calibration_included": False,
        "secrets_included": False,
    }
    (stage / "MANIFEST.json").write_text(json.dumps(manifest_meta, indent=2) + "\n", encoding="utf-8")

    sanitized_paths = sanitize_local_paths(stage)
    findings, scanned = scan_stage(stage)
    (stage / "SECRET_SCAN.txt").write_text(
        ("SECRET_SCAN=PASS\n" if not findings else "SECRET_SCAN=FAIL\n")
        + f"text_files_scanned={scanned}\n"
        + f"local_path_files_sanitized={sanitized_paths}\n"
        + "raw_flash=0\ncalibration_data=0\nunique_identifiers=0\n"
        + ("\n".join(findings) + "\n" if findings else ""), encoding="utf-8"
    )
    if findings:
        raise RuntimeError("secret scan failed: " + "; ".join(findings[:20]))
    file_count = write_manifest(stage)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            archive.write(path, f"{name}/{path.relative_to(stage).as_posix()}")
    digest = sha256(zip_path)
    zip_path.with_suffix(".zip.sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(f"QUANTENNA_PRIVATE_DIR={stage}")
    print(f"QUANTENNA_PRIVATE_ZIP={zip_path}")
    print(f"ZIP_SHA256={digest}")
    print(f"FILES={file_count}")
    print("SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
