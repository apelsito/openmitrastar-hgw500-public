#!/usr/bin/env python3
"""Build F170 from F169 with hardware-native API reads and gated apply."""
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
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f169-lyoko-foundation/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f169-lyoko-foundation-LZMA-OFFLINE-NO-FLASH"
FOUNDATION = ROOT / "versions/lyoko-foundation-1.0"
OVERLAY = FOUNDATION / "overlay"
ASSETS = ROOT / "outputs/kernel-port/f170-lyoko-foundation-runtime-fix-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build"
BASE = "openmitrastar-linux510-q3-persistent-f170-lyoko-foundation-runtime-fix-LZMA-OFFLINE-NO-FLASH"
PRODUCT_VERSION = "lyoko-foundation-1.0-f170"
ASSETS_SCHEMA = "openmitrastar.f170-lyoko-foundation-assets/v1"
DIFF_SCHEMA = "openmitrastar.f170-foundation-rootfs-diff/v1"
REMOVE_PATHS: tuple[str, ...] = ()
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    return f"{WS_ROOT}/{path.resolve().relative_to(ROOT.resolve()).as_posix()}"


def overlay_build_id() -> str:
    digest = hashlib.sha256()
    digest.update(sha256(SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").encode("ascii"))
    for relative in sorted(REMOVE_PATHS):
        digest.update(b"REMOVE\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\n")
    for path in sorted(item for item in OVERLAY.rglob("*") if item.is_file()):
        digest.update(path.relative_to(OVERLAY).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def run_wsl(script: str, timeout: int = 900) -> None:
    result = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, check=False,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    if result.stdout:
        print(result.stdout, end="")


def prepare_assets() -> dict[str, object]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    source_rootfs = SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs"
    build_id = overlay_build_id()
    for relative in REMOVE_PATHS:
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise SystemExit(f"unsafe rootfs removal path: {relative!r}")
    remove_commands = "\n".join(f'rm -f "$stage/new/{relative}"' for relative in REMOVE_PATHS)
    target_rootfs = ASSETS / "rootfs-product-xz-128k.squashfs"
    inventory_path = ASSETS / "rootfs-diff.json"
    shell = f"""
set -eu
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
source_sq={shlex.quote(wsl_path(source_rootfs))}
overlay={shlex.quote(wsl_path(OVERLAY))}
target_sq={shlex.quote(wsl_path(target_rootfs))}
inventory={shlex.quote(wsl_path(inventory_path))}
unsquashfs -no-progress -d "$stage/base" "$source_sq" >/dev/null
cp -a "$stage/base" "$stage/new"
cp -a "$overlay/." "$stage/new/"
{remove_commands}
find "$stage/new" -type d -exec chmod 0755 {{}} +
chmod 01777 "$stage/new/tmp"
chmod 0755 "$stage/new/usr/libexec/openmitrastar/om-api-v1" \
  "$stage/new/usr/libexec/openmitrastar/om-oem-cgi" \
  "$stage/new/usr/sbin/om-config-transaction" "$stage/new/usr/sbin/om-ssh" \
  "$stage/new/etc/init.d/S44-oem-web" "$stage/new/etc/init.d/S90-ready"
[ ! -e "$stage/new/usr/sbin/om-radioctl" ] || chmod 0755 "$stage/new/usr/sbin/om-radioctl"
[ ! -e "$stage/new/usr/sbin/om-package-api" ] || chmod 0755 "$stage/new/usr/sbin/om-package-api"
find "$stage/new/www/api/v1" -type f -exec chmod 0755 {{}} +
[ ! -e "$stage/new/www/dashboard.cgi" ] || chmod 0755 "$stage/new/www/dashboard.cgi"
[ ! -e "$stage/new/usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key" ] || chmod 0600 "$stage/new/usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key"
[ ! -e "$stage/new/usr/share/openmitrastar/device-identity/dropbear_ed25519_host_key" ] || chmod 0600 "$stage/new/usr/share/openmitrastar/device-identity/dropbear_ed25519_host_key"
[ ! -e "$stage/new/usr/share/openmitrastar/device-identity/web_password.sha256" ] || chmod 0600 "$stage/new/usr/share/openmitrastar/device-identity/web_password.sha256"
find "$stage/new/www" -type f ! -path '*/api/v1/*' ! -name '*.cgi' -exec chmod 0644 {{}} +
find "$stage/new/www" -maxdepth 1 -type f -name '*.cgi' -exec chmod 0755 {{}} +
[ ! -e "$stage/new/usr/bin/lyoko-sysinfo" ] || chmod 0755 "$stage/new/usr/bin/lyoko-sysinfo"
[ ! -e "$stage/new/usr/bin/lyoko-pkg" ] || chmod 0755 "$stage/new/usr/bin/lyoko-pkg"
[ ! -e "$stage/new/usr/bin/lyoko-ed25519-verify" ] || chmod 0755 "$stage/new/usr/bin/lyoko-ed25519-verify"
[ ! -e "$stage/new/usr/libexec/lyoko/pkgbox" ] || chmod 0755 "$stage/new/usr/libexec/lyoko/pkgbox"
[ ! -e "$stage/new/usr/libexec/lyoko/busybox" ] || chmod 0755 "$stage/new/usr/libexec/lyoko/busybox"
[ ! -e "$stage/new/etc/init.d/S31-spi-probe" ] || chmod 0755 "$stage/new/etc/init.d/S31-spi-probe"
[ ! -e "$stage/new/etc/init.d/S43-web-credential" ] || chmod 0755 "$stage/new/etc/init.d/S43-web-credential"
[ ! -e "$stage/new/etc/init.d/S33-multicast-policy" ] || chmod 0755 "$stage/new/etc/init.d/S33-multicast-policy"
[ ! -e "$stage/new/usr/sbin/om-multicast-policy" ] || chmod 0755 "$stage/new/usr/sbin/om-multicast-policy"
[ ! -e "$stage/new/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/diagnostics/qtn-topaz-spi-probe.ko" ] || chmod 0644 "$stage/new/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/diagnostics/qtn-topaz-spi-probe.ko"
[ ! -d "$stage/new/etc/lyoko" ] || find "$stage/new/etc/lyoko" -type f -exec chmod 0644 {{}} +
[ ! -d "$stage/new/etc/openmitrastar/features" ] || find "$stage/new/etc/openmitrastar/features" -type f -exec chmod 0644 {{}} +
[ ! -d "$stage/new/usr/share/lyoko" ] || find "$stage/new/usr/share/lyoko" -type f -exec chmod 0644 {{}} +
sed -i 's/^OPENMITRASTAR_PRODUCT_VERSION=.*/OPENMITRASTAR_PRODUCT_VERSION={PRODUCT_VERSION}/' "$stage/new/etc/openmitrastar/release"
if grep -q '^OPENMITRASTAR_BUILD_ID=' "$stage/new/etc/openmitrastar/release"; then sed -i 's/^OPENMITRASTAR_BUILD_ID=.*/OPENMITRASTAR_BUILD_ID={build_id}/' "$stage/new/etc/openmitrastar/release"; else printf '%s\n' 'OPENMITRASTAR_BUILD_ID={build_id}' >>"$stage/new/etc/openmitrastar/release"; fi
grep -q '^OPENMITRASTAR_API_VERSION=' "$stage/new/etc/openmitrastar/release" || printf '%s\n' 'OPENMITRASTAR_API_VERSION=v1' >>"$stage/new/etc/openmitrastar/release"
grep -q '^OPENMITRASTAR_UI_VERSION=' "$stage/new/etc/openmitrastar/release" || printf '%s\n' 'OPENMITRASTAR_UI_VERSION=foundation-1.0' >>"$stage/new/etc/openmitrastar/release"
chmod 0644 "$stage/new/etc/openmitrastar/release" "$stage/new/etc/minihttpd-oem.conf"
python3 - "$stage/base" "$stage/new" "$inventory" <<'PY'
import hashlib, json, os, stat, sys
from pathlib import Path
base, new, output = map(Path, sys.argv[1:])
def inventory(root):
    result = {{}}
    for item in sorted(root.rglob('*')):
        rel = item.relative_to(root).as_posix(); mode = item.lstat().st_mode
        row = {{"mode": oct(stat.S_IMODE(mode)), "type": "other"}}
        if item.is_symlink(): row.update(type="symlink", target=os.readlink(item))
        elif item.is_file(): row.update(type="file", bytes=item.stat().st_size, sha256=hashlib.sha256(item.read_bytes()).hexdigest())
        elif item.is_dir(): row["type"] = "dir"
        result[rel] = row
    return result
old=inventory(base); cur=inventory(new)
changed=sorted(p for p in set(old)|set(cur) if old.get(p)!=cur.get(p))
Path(output).write_text(json.dumps({{"schema":"{DIFF_SCHEMA}","changed_paths":changed,"old":{{p:old.get(p) for p in changed}},"new":{{p:cur.get(p) for p in changed}}}},indent=2,sort_keys=True)+"\\n",encoding="ascii")
PY
find "$stage/new" -exec touch -h -d '@1785024000' {{}} +
rm -f "$target_sq"
mksquashfs "$stage/new" "$target_sq" -noappend -all-root -comp xz -b 131072 -no-xattrs -no-exports -all-time 1785024000 -mkfs-time 1785024000 -no-progress >/dev/null
unsquashfs -s "$target_sq" >"{shlex.quote(wsl_path(ASSETS / 'rootfs-product-xz-superblock.txt'))}"
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
        "schema": ASSETS_SCHEMA,
        "build_id": build_id,
        "source_rootfs": {"path": str(source_rootfs.relative_to(ROOT)), "sha256": sha256(source_rootfs)},
        "rootfs": {"path": str(target_rootfs.relative_to(ROOT)), "bytes": target_rootfs.stat().st_size, "sha256": sha256(target_rootfs)},
        "rootfs_diff": json.loads(inventory_path.read_text(encoding="ascii")),
        "hardware_actions": {"router": False, "uart": False, "flash": False},
        "removed_paths": list(REMOVE_PATHS),
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
        "schema": "openmitrastar.f170-lyoko-foundation-runtime-fix/v1",
        "classification": "F170_LYOKO_FOUNDATION_RUNTIME_FIX_FLASH_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"firmware": "F169", "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT))},
        "change_scope": {
            "api_reads": "use hostapd, hostapd-qtn, iwconfig-qtn, iwpriv-qtn and imported runtime config actually present on F169",
            "config_transactions": "safe no-op verification enabled; material changes remain feature-gated",
            "build_identity": f"deterministic {assets['build_id']}",
            "kernel_and_radios": "byte-identical to F167/F169",
        },
        "foundation_assets": assets,
        "physical_validation": {"status": "NOT_RUN", "required": "boot, stable SSH host key, dashboard, authenticated API v1 reads and no-op transaction"},
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
