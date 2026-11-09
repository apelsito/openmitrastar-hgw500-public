#!/usr/bin/env python3
"""Build the F168-2G read-only TX diagnostic candidate from installed F167.

F168 deliberately changes no kernel or radio module bytes.  It enables four
existing, target-gated and bounded RTL8192EE diagnostics in the product loader:

* BE enqueue/completion summaries (rtl_pci)
* TX ring closure/RP-WP diagnostics (rtl8192ee)
* TX descriptor/rate/AMPDU sampling (rtl8192ee)
* OEM firmware TX report sampling (rtl8192ee)

The resulting SquashFS remains read-only.  This builder is offline-only: it
does not contact the router, open UART, reboot, or write flash.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path

import compose_f164_squashfs_product as engine


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f167-emac-ownership-fix/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f167-emac-ownership-fix-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f168-2g-tx-diag-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f168-2g-tx-diag-from-f167/build"
BASE = "openmitrastar-linux510-q3-persistent-f168-2g-tx-diag-from-f167-LZMA-OFFLINE-NO-FLASH"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
LOADER_ENTRY = "usr/sbin/om-radio-modules"

REPLACEMENTS = (
    (
        b"hgw500_tx_reclaim_poll=1\"",
        b"hgw500_tx_reclaim_poll=1 hgw500_be_tx_summary=1\"",
    ),
    (b"hgw500_tx_close_diag=0", b"hgw500_tx_close_diag=1"),
    (b"hgw500_tx_rate_trace=0", b"hgw500_tx_rate_trace=1"),
    (
        b"hgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=Y; do",
        b"hgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=Y \\\n\t\t\thgw500_be_tx_summary=Y; do",
    ),
    (b"hgw500_tx_close_diag=N", b"hgw500_tx_close_diag=Y"),
    (b"hgw500_tx_rate_trace=N", b"hgw500_tx_rate_trace=Y"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def windows_to_wsl(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    return f"{WS_ROOT}/{relative}"


def run_wsl(script: str, *, capture: bool = False, timeout: int = 900) -> bytes:
    proc = subprocess.run(
        [
            "wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash",
            "--noprofile", "--norc", "-c", script,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise SystemExit((proc.stderr or proc.stdout).decode("utf-8", errors="replace"))
    if not capture and proc.stdout:
        print(proc.stdout.decode("utf-8", errors="replace"), end="")
    return proc.stdout


def patch_loader(data: bytes) -> tuple[bytes, dict[str, object]]:
    patched = data
    changes: list[dict[str, object]] = []
    for old, new in REPLACEMENTS:
        count = patched.count(old)
        if count != 1:
            raise SystemExit(
                f"F168 expected one loader marker {old!r}, found {count}"
            )
        patched = patched.replace(old, new, 1)
        changes.append({
            "old": old.decode("ascii"),
            "new": new.decode("ascii"),
            "count": 1,
        })
    return patched, {
        "entry": LOADER_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched),
        "old_sha256": sha256_bytes(data),
        "new_sha256": sha256_bytes(patched),
        "changes": changes,
    }


def prepare_assets() -> dict[str, object]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    source_rootfs = SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs"
    if not source_rootfs.is_file():
        raise SystemExit(f"missing F167 rootfs: {source_rootfs}")

    source_rootfs_wsl = windows_to_wsl(source_rootfs)
    loader = run_wsl(
        f"unsquashfs -cat {shlex.quote(source_rootfs_wsl)} {shlex.quote(LOADER_ENTRY)}",
        capture=True,
    )
    patched_loader, patch_report = patch_loader(loader)
    patched_loader_path = ASSETS / "om-radio-modules.f168"
    patched_loader_path.write_bytes(patched_loader)

    target_rootfs = ASSETS / "rootfs-product-xz-128k.squashfs"
    inventory_path = ASSETS / "rootfs-diff.json"
    superblock_path = ASSETS / "rootfs-product-xz-superblock.txt"
    shell = f"""
set -eu
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
source_sq={shlex.quote(source_rootfs_wsl)}
patched_loader={shlex.quote(windows_to_wsl(patched_loader_path))}
target_sq={shlex.quote(windows_to_wsl(target_rootfs))}
inventory={shlex.quote(windows_to_wsl(inventory_path))}
superblock={shlex.quote(windows_to_wsl(superblock_path))}
unsquashfs -no-progress -d "$stage/base" "$source_sq" >/dev/null
cp -a "$stage/base" "$stage/new"
cp "$patched_loader" "$stage/new/{LOADER_ENTRY}"
chmod 0755 "$stage/new/{LOADER_ENTRY}"
python3 - "$stage/base" "$stage/new" "$inventory" <<'PY'
import hashlib, json, os, stat, sys
from pathlib import Path

base, new, output = map(Path, sys.argv[1:])

def inventory(root):
    result = {{}}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        item = {{"mode": oct(stat.S_IMODE(mode)), "type": "other"}}
        if path.is_symlink():
            item.update(type="symlink", target=os.readlink(path))
        elif path.is_file():
            item.update(
                type="file",
                bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        elif path.is_dir():
            item["type"] = "dir"
        result[rel] = item
    return result

old = inventory(base)
cur = inventory(new)
changed = sorted(path for path in set(old) | set(cur) if old.get(path) != cur.get(path))
report = {{
    "schema": "openmitrastar.f168-rootfs-diff/v1",
    "changed_paths": changed,
    "only_loader_changed": changed == ["{LOADER_ENTRY}"],
    "old": {{path: old.get(path) for path in changed}},
    "new": {{path: cur.get(path) for path in changed}},
}}
Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="ascii")
if not report["only_loader_changed"]:
    raise SystemExit(f"unexpected rootfs changes: {{changed}}")
PY
mksquashfs "$stage/new" "$target_sq" -noappend -all-root -comp xz -b 131072 \
  -no-xattrs -no-exports -all-time 1785024000 -mkfs-time 1785024000 \
  -no-progress >/dev/null
unsquashfs -s "$target_sq" > "$superblock"
"""
    run_wsl(shell, timeout=900)

    copies = {
        "kernel-squashfs.uncompressed.uImage": ".uncompressed.uImage",
        "kernel-squashfs.raw.bin": ".kernel.raw.bin",
        "kernel-squashfs.lzma": ".kernel.lzma",
        "kernel-squashfs.config": ".config",
        "topaz_mitrastar_squashfs.dtb": ".dtb",
        "kernel-squashfs.vmlinux": ".vmlinux",
    }
    for target_name, suffix in copies.items():
        source = SOURCE_BUILD / f"{SOURCE_BASE}{suffix}"
        if not source.is_file():
            raise SystemExit(f"missing F167 artifact: {source}")
        shutil.copy2(source, ASSETS / target_name)

    report = {
        "schema": "openmitrastar.f168-2g-tx-diag-assets/v1",
        "source_rootfs": {
            "path": str(source_rootfs.relative_to(ROOT)),
            "bytes": source_rootfs.stat().st_size,
            "sha256": sha256(source_rootfs),
        },
        "patched_rootfs": {
            "path": str(target_rootfs.relative_to(ROOT)),
            "bytes": target_rootfs.stat().st_size,
            "sha256": sha256(target_rootfs),
        },
        "loader_patch": patch_report,
        "rootfs_diff": json.loads(inventory_path.read_text(encoding="ascii")),
        "kernel_and_modules": "byte-identical to F167",
        "hardware_actions": {
            "router_contact": False,
            "uart": False,
            "reboot": False,
            "mtd_write": False,
        },
    }
    (ASSETS / "assets-manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    return report


@contextlib.contextmanager
def variant_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    assets = prepare_assets()
    with variant_context():
        rc = engine.main()
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source_manifest = SOURCE_BUILD / "manifest.json"
    manifest.update({
        "schema": "openmitrastar.f168-2g-tx-diag-from-f167/v1",
        "classification": "F168_2G_TX_DIAGNOSTIC_FLASH_CANDIDATE_UNVALIDATED",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "base": "installed F167 EMAC ownership telemetry candidate",
            "build_dir": str(SOURCE_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest),
            "webformat_sha256": json.loads(
                source_manifest.read_text(encoding="ascii")
            )["artifacts"]["webformat"]["sha256"],
        },
        "change_scope": {
            "rootfs_loader_only": [
                "rtl_pci hgw500_be_tx_summary=1",
                "rtl8192ee hgw500_tx_close_diag=1",
                "rtl8192ee hgw500_tx_rate_trace=1",
            ],
            "kernel": "byte-identical to F167",
            "radio2g_modules": "byte-identical to F167",
            "radio2g_rates_crypto": "unchanged: forced MCS7, hardware crypto, AMPDU policy and fabricated ACK policy preserved",
            "emac": "byte-identical to F167",
            "rootfs_payload": "all paths byte-identical except usr/sbin/om-radio-modules",
            "radio5_quantenna": "byte-identical to F167",
            "bridge_security_regulatory": "unchanged from F167",
        },
        "diagnostics": {
            "OMRTLBE": "bounded BE enqueue/completion byte, packet and queue summaries",
            "OMRTLTXCLOSE": "sample closed=0 events with software/hardware RP-WP and OWN",
            "OMRTLRA_tx_desc": "sample descriptor rate, AMPDU, bandwidth and fallback policy",
            "OMRTLRA_fw_report": "existing firmware report remains disabled to avoid adding a report-request side effect",
        },
        "rootfs_patch": assets,
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "repeat controlled F167/F168 32 MiB bidirectional tests and correlate OMRTLBE/OMRTLTXCLOSE/OMRTLRA with EMAC counters",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "mtd0_mtd1_mtd2_mtd3_mtd5": "must remain unchanged",
            "mtd6": "logical rootfs_live view, never a physical write target",
            "builder_contacted_hardware": False,
        },
    })
    manifest["contracts"]["hardware_boot"] = "NOT_RUN"
    manifest["contracts"]["flash"] = False
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
