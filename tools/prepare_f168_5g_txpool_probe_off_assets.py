#!/usr/bin/env python3
"""Prepare F168 SquashFS assets from F167 with qdrv TX-pool probing off."""
from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
F167 = ROOT / "work/mission-state/q3-persistent-composite-f167-emac-ownership-fix/build"
F167_BASE = "openmitrastar-linux510-q3-persistent-f167-emac-ownership-fix-LZMA-OFFLINE-NO-FLASH"
MODULES = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-txpool-probe-off-f168-20260901"
NEW_QDRV = MODULES / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
OLD_QDRV_SHA = "0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff"
NEW_QDRV_SHA = "ed5314b5f24e6ae4f3dd07ef1efc57c68e4246c9e3fdf055657f80c5798f7f26"
OUT = ROOT / "outputs/kernel-port/f168-5g-txpool-probe-off-20260901"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
STAGE = "/home/user/openmitrastar-build/f168-5g-txpool-probe-off-root"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_wsl(script: str) -> None:
    proc = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout or f"WSL failed rc={proc.returncode}")
    if proc.stdout:
        print(proc.stdout, end="")


def main() -> int:
    if sha256(NEW_QDRV) != NEW_QDRV_SHA:
        raise SystemExit("F168 qdrv hash mismatch; rebuild the pinned module first")
    OUT.mkdir(parents=True, exist_ok=True)
    for src_name, dst_name in (
        (f"{F167_BASE}.uncompressed.uImage", "kernel-squashfs.uncompressed.uImage"),
        (f"{F167_BASE}.kernel.raw.bin", "kernel-squashfs.raw.bin"),
        (f"{F167_BASE}.kernel.lzma", "kernel-squashfs.lzma"),
        (f"{F167_BASE}.config", "kernel-squashfs.config"),
        (f"{F167_BASE}.dtb", "topaz_mitrastar_squashfs.dtb"),
        (f"{F167_BASE}.vmlinux", "kernel-squashfs.vmlinux"),
    ):
        shutil.copy2(F167 / src_name, OUT / dst_name)

    image = F167 / f"{F167_BASE}.rootfs.squashfs"
    image_wsl = f"{WS_ROOT}/{image.relative_to(ROOT).as_posix()}"
    qdrv_wsl = f"{WS_ROOT}/{NEW_QDRV.relative_to(ROOT).as_posix()}"
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    shell = f"""
set -eu
image={shlex.quote(image_wsl)}
qdrv={shlex.quote(qdrv_wsl)}
out={shlex.quote(out_wsl)}
stage={shlex.quote(STAGE)}
rm -rf "$stage"
mkdir -p "$stage"
unsquashfs -d "$stage" "$image" > "$out/rootfs-extract.log"
target="$stage/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko"
test "$(sha256sum "$target" | cut -d' ' -f1)" = {OLD_QDRV_SHA}
cp "$qdrv" "$target"
start="$stage/usr/sbin/om-radio5-start"
contract="$stage/usr/share/openmitrastar/radio5g/driver-contract.env"
hashes="$stage/usr/share/openmitrastar/radio5g/artifacts.sha256"
sed -i 's/{OLD_QDRV_SHA}/{NEW_QDRV_SHA}/g' "$start" "$contract" "$hashes"
start_sha=$(sha256sum "$start" | cut -d' ' -f1)
contract_sha=$(sha256sum "$contract" | cut -d' ' -f1)
awk -v start_sha="$start_sha" -v contract_sha="$contract_sha" '
$2 == "/usr/sbin/om-radio5-start" {{ print start_sha "  " $2; next }}
$2 == "/usr/share/openmitrastar/radio5g/driver-contract.env" {{ print contract_sha "  " $2; next }}
{{ print }}' "$hashes" > "$hashes.new"
mv "$hashes.new" "$hashes"
grep -qx 'QDRV_SHA256={NEW_QDRV_SHA}' "$contract"
grep -q 'expected_qdrv_sha={NEW_QDRV_SHA}' "$start"
grep -q 'fwt_ctrl=absent' "$start"
! grep -Eq 'load_module fwt_ctrl|modprobe .*fwt_ctrl|insmod .*fwt_ctrl' "$start"
mksquashfs "$stage" "$out/rootfs-product-xz-128k.squashfs" -noappend -all-root -comp xz -b 131072 -no-xattrs -no-exports -all-time 1785024000 -mkfs-time 1785024000 -no-progress > "$out/rootfs-build.log"
unsquashfs -s "$out/rootfs-product-xz-128k.squashfs" > "$out/rootfs-superblock.txt"
"""
    run_wsl(shell)
    manifest = {
        "schema": "openmitrastar.f168-5g-txpool-probe-off-assets/v1",
        "source_firmware": str((F167 / f"{F167_BASE}.webformat.bin").relative_to(ROOT)),
        "source_rootfs_sha256": sha256(image),
        "qdrv": {"old_sha256": OLD_QDRV_SHA, "new_sha256": NEW_QDRV_SHA, "bytes": NEW_QDRV.stat().st_size},
        "kernel_byte_identical_to_f167": True,
        "rootfs_change_scope": ["qdrv.ko", "om-radio5-start qdrv hash", "driver-contract.env", "artifacts.sha256"],
        "fwt_ctrl_policy": "module retained as an artifact but never loaded; lifecycle remains disabled",
        "artifacts": {},
    }
    for path in OUT.iterdir():
        if path.is_file() and path.name != "assets-manifest.json":
            manifest["artifacts"][path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    (OUT / "assets-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
