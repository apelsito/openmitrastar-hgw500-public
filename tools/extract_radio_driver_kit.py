#!/usr/bin/env python3
"""Build a reproducible, offline radio-driver reverse-engineering kit."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOTFS = ROOT / "work" / "revival" / "rootfs"
OUT = ROOT / "outputs" / "radio-driver-kit-0.7"
READELF = ROOT / "work" / "toolchains" / "arc-uclibc" / "arc-arc700-linux-uclibc" / "bin" / "arc-linux-readelf"

PATHS = [
    "lib/modules/2.6.35.12/extra/qdrv/qdrv.ko",
    "lib/modules/2.6.35.12/extra/rtl8192cd.ko",
    "lib/modules/2.6.35.12/extra/wlan/wlan.ko",
    "lib/modules/2.6.35.12/extra/radar/radar.ko",
    "lib/modules/2.6.35.12/extra/qvsp/qvspmod.ko",
    "lib/modules/2.6.35.12/extra/auc/auc_fw.ko",
    "lib/modules/2.6.35.12/extra/pcie2/host/quantenna/qdpc-host.ko",
    "etc/firmware/qtn_driver.qtn_ruby.0.bin",
    "etc/firmware/auc_driver.nomu.0.bin",
    "etc/firmware/auc_driver.default.0.bin",
    "etc/firmware/rdsp_driver.0.bin",
    "etc/power_tables/tx_power_QSR1000_es.txt",
    "etc/power_tables/power_table.conf",
    "etc/default_config.txt",
    "etc/init.d/S50Wireless",
    "etc/init.d/S55qwe",
    "scripts/load-qdrv",
    "lib/wlan/wlan1.sh",
    "sbin/call_qcsapi",
    "lib/libcall_qcsapi.so.1.0.1",
    "lib/libqcsapi.so.1.0.1",
]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def strings(path: Path, minimum: int = 5) -> list[str]:
    pattern = rb"[\x20-\x7e]{%d,}" % minimum
    return [m.decode("ascii", errors="ignore") for m in re.findall(pattern, path.read_bytes())]

def wsl_path(path: Path) -> str:
    p = path.resolve().as_posix()
    return f"/mnt/{p[0].lower()}{p[2:]}"

def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    payload = OUT / "payload"
    analysis = OUT / "analysis"
    payload.mkdir(parents=True)
    analysis.mkdir(parents=True)
    inventory = []
    for relative in PATHS:
        src = ROOTFS / relative
        if not src.exists():
            raise FileNotFoundError(src)
        dst = payload / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        inventory.append({"path": relative, "size": src.stat().st_size, "sha256": sha256(src)})
        if src.suffix in {".ko", ".so"} or ".so." in src.name or src.name == "call_qcsapi":
            printable = strings(src)
            (analysis / f"{src.name}.strings.txt").write_text("\n".join(printable) + "\n", encoding="utf-8")
            try:
                result = subprocess.run(
                    ["wsl", wsl_path(READELF), "-h", "-S", "-s", wsl_path(src)],
                    capture_output=True, text=True, check=False, timeout=60,
                )
                (analysis / f"{src.name}.readelf.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
            except (OSError, subprocess.TimeoutExpired) as exc:
                (analysis / f"{src.name}.readelf.txt").write_text(f"readelf unavailable: {exc}\n", encoding="utf-8")
    lib = ROOTFS / "lib/libcall_qcsapi.so.1.0.1"
    commands = sorted({s for s in strings(lib) if re.fullmatch(r"(?:get|set|show|start|stop)_[A-Za-z0-9_]+", s)})
    (analysis / "qcsapi-command-map.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    (OUT / "inventory.json").write_text(json.dumps({"files": inventory, "qcsapi_commands": len(commands)}, indent=2), encoding="utf-8")
    report = f"""# OpenMitraStar radio driver reverse engineering kit

Generated offline from the verified HGW-500BNA-QCv2 firmware rootfs.

## Result

- Quantenna 5 GHz: `qdrv.ko` + `wlan.ko` + `radar.ko` + MuC/AuC/DSP firmware.
- Realtek 2.4 GHz: `rtl8192cd.ko`, reached through the Quantenna PCIe host driver.
- Control plane: `call_qcsapi`, `libcall_qcsapi`, `libqcsapi` and {len(commands)} recovered command names.
- Calibration/regulatory evidence: ES QSR1000 power table preserved byte-for-byte.
- Every extracted artifact has size and SHA-256 in `inventory.json`.

## Layout

- `payload/`: exact binaries, firmware, power tables and boot scripts.
- `analysis/*.strings.txt`: printable-string extraction for static triage.
- `analysis/*.readelf.txt`: ELF headers, sections and available symbols.
- `analysis/qcsapi-command-map.txt`: recovered callable command names.

## Engineering conclusion

The production path is to preserve this OEM radio ABI and wrap verified QCSAPI
operations. Replacing `qdrv` requires a separate modern-kernel/qtnfmac lab path,
PCI identity proof, firmware ABI matching, calibration loading and DFS validation.
Do not write raw qdrv sysfs controls or calibration partitions from the web UI.
"""
    (OUT / "README.md").write_text(report, encoding="utf-8")
    print(f"created {OUT} ({len(inventory)} files, {len(commands)} QCSAPI commands)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
