#!/usr/bin/env python3
"""Build the F169 Lyoko Foundation image from the proven F167 baseline."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

import compose_f164_squashfs_product as engine


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f167-emac-ownership-fix/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f167-emac-ownership-fix-LZMA-OFFLINE-NO-FLASH"
FOUNDATION = ROOT / "versions/lyoko-foundation-1.0"
OVERLAY = FOUNDATION / "overlay"
ASSETS = ROOT / "outputs/kernel-port/f169-lyoko-foundation-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f169-lyoko-foundation/build"
BASE = "openmitrastar-linux510-q3-persistent-f169-lyoko-foundation-LZMA-OFFLINE-NO-FLASH"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    return f"{WS_ROOT}/{path.resolve().relative_to(ROOT.resolve()).as_posix()}"


def run_wsl(script: str, timeout: int = 900) -> None:
    result = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    if result.stdout:
        print(result.stdout, end="")


def prepare_assets() -> dict[str, object]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    source_rootfs = SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs"
    if not source_rootfs.is_file():
        raise SystemExit(f"missing F167 rootfs: {source_rootfs}")
    host_key = OVERLAY / "usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key"
    if not host_key.is_file() or host_key.stat().st_size < 64:
        raise SystemExit("missing stable device SSH host key")

    target_rootfs = ASSETS / "rootfs-product-xz-128k.squashfs"
    inventory_path = ASSETS / "rootfs-diff.json"
    superblock_path = ASSETS / "rootfs-product-xz-superblock.txt"
    shell = f"""
set -eu
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
source_sq={shlex.quote(wsl_path(source_rootfs))}
overlay={shlex.quote(wsl_path(OVERLAY))}
target_sq={shlex.quote(wsl_path(target_rootfs))}
inventory={shlex.quote(wsl_path(inventory_path))}
superblock={shlex.quote(wsl_path(superblock_path))}
unsquashfs -no-progress -d "$stage/base" "$source_sq" >/dev/null
cp -a "$stage/base" "$stage/new"
cp -a "$overlay/." "$stage/new/"
find "$stage/new" -type d -exec chmod 0755 {{}} +
chmod 01777 "$stage/new/tmp"
chmod 0755 "$stage/new/usr/libexec/openmitrastar/om-api-v1" \
  "$stage/new/usr/libexec/openmitrastar/om-oem-cgi" \
  "$stage/new/usr/sbin/om-config-transaction" "$stage/new/usr/sbin/om-ssh" \
  "$stage/new/etc/init.d/S44-oem-web"
find "$stage/new/www/api/v1" -type f -exec chmod 0755 {{}} +
chmod 0600 "$stage/new/usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key"
chmod 0644 "$stage/new/www/dashboard.html" "$stage/new/www/app.css" \
  "$stage/new/www/app.js" "$stage/new/www/assets/logo.svg" \
  "$stage/new/etc/minihttpd-oem.conf" "$stage/new/etc/openmitrastar/release"
sed -i 's/^OPENMITRASTAR_PRODUCT_VERSION=.*/OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-1.0-f169/' "$stage/new/etc/openmitrastar/release"
grep -q '^OPENMITRASTAR_API_VERSION=' "$stage/new/etc/openmitrastar/release" || printf '%s\n' 'OPENMITRASTAR_API_VERSION=v1' >>"$stage/new/etc/openmitrastar/release"
grep -q '^OPENMITRASTAR_UI_VERSION=' "$stage/new/etc/openmitrastar/release" || printf '%s\n' 'OPENMITRASTAR_UI_VERSION=foundation-1.0' >>"$stage/new/etc/openmitrastar/release"
python3 - "$stage/base" "$stage/new" "$inventory" <<'PY'
import hashlib, json, os, stat, sys
from pathlib import Path
base, new, output = map(Path, sys.argv[1:])
def inventory(root):
    result = {{}}
    for item in sorted(root.rglob('*')):
        rel = item.relative_to(root).as_posix()
        mode = item.lstat().st_mode
        row = {{"mode": oct(stat.S_IMODE(mode)), "type": "other"}}
        if item.is_symlink(): row.update(type="symlink", target=os.readlink(item))
        elif item.is_file(): row.update(type="file", bytes=item.stat().st_size, sha256=hashlib.sha256(item.read_bytes()).hexdigest())
        elif item.is_dir(): row["type"] = "dir"
        result[rel] = row
    return result
old=inventory(base); cur=inventory(new)
changed=sorted(path for path in set(old)|set(cur) if old.get(path)!=cur.get(path))
Path(output).write_text(json.dumps({{"schema":"openmitrastar.f169-foundation-rootfs-diff/v1","changed_paths":changed,"old":{{p:old.get(p) for p in changed}},"new":{{p:cur.get(p) for p in changed}}}},indent=2,sort_keys=True)+"\\n",encoding="ascii")
PY
find "$stage/new" -exec touch -h -d '@1785024000' {{}} +
rm -f "$target_sq"
mksquashfs "$stage/new" "$target_sq" -noappend -all-root -comp xz -b 131072 -no-xattrs -no-exports -all-time 1785024000 -mkfs-time 1785024000 -no-progress >/dev/null
unsquashfs -s "$target_sq" >"$superblock"
"""
    run_wsl(shell)

    copies = {
        ".uncompressed.uImage": "kernel-squashfs.uncompressed.uImage",
        ".kernel.raw.bin": "kernel-squashfs.raw.bin",
        ".kernel.lzma": "kernel-squashfs.lzma",
        ".config": "kernel-squashfs.config",
        ".dtb": "topaz_mitrastar_squashfs.dtb",
        ".vmlinux": "kernel-squashfs.vmlinux",
    }
    for suffix, target in copies.items():
        shutil.copy2(SOURCE_BUILD / f"{SOURCE_BASE}{suffix}", ASSETS / target)

    report = {
        "schema": "openmitrastar.f169-lyoko-foundation-assets/v1",
        "source_rootfs": {"path": str(source_rootfs.relative_to(ROOT)), "sha256": sha256(source_rootfs)},
        "rootfs": {"path": str(target_rootfs.relative_to(ROOT)), "bytes": target_rootfs.stat().st_size, "sha256": sha256(target_rootfs)},
        "rootfs_diff": json.loads(inventory_path.read_text(encoding="ascii")),
        "stable_ssh_host_key": {"installed": True, "sha256": sha256(host_key), "private": True},
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }
    (ASSETS / "assets-manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return report


@contextlib.contextmanager
def variant_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.ASSETS = ASSETS; engine.OUT = OUT; engine.BASE = BASE
        yield
    finally:
        for name, value in old.items(): setattr(engine, name, value)


def main() -> int:
    assets = prepare_assets()
    with variant_context():
        rc = engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f169-lyoko-foundation/v1",
        "classification": "F169_LYOKO_FOUNDATION_FLASH_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "change_scope": {
            "base": "F167 exact SquashFS plus corrected EMAC telemetry",
            "web": "Lyoko Foundation 1.0 Normal/Advanced/Developer dashboard",
            "api": "authenticated /api/v1 read model and staged radio transactions",
            "ssh": "stable device-specific Ed25519 host identity bundled as fallback",
            "kernel_and_radios": "byte-identical to F167",
        },
        "source": {
            "firmware": "F167",
            "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT)),
        },
        "foundation_assets": assets,
        "physical_validation": {"status": "NOT_RUN", "required": "boot, login, all GET endpoints, stage/apply/rollback no-op, both radio control planes"},
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
