#!/usr/bin/env python3
"""Build the F304 API-contract layer from the exact installed F301 runtime."""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import zlib

import compose_f164_squashfs_product as compose
from build_f196_device_personalized import verify_embedded_key
from init_lyoko_device_host_key import (
    DEFAULT_ROOT,
    DEFAULT_TOOL,
    DEVICE_RE,
    inspect_key,
    restrict_acl,
    wsl_path,
)


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_SOURCE = ROOT / "versions/lyoko-foundation-6.7.1-f304-api-contract/overlay"
PRODUCT_VERSION = "lyoko-foundation-6.7.1-f304-api-contract-device"
ROOTFS_WINDOW = 0x460000
ROOTFS_OFFSET = 0x180000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000
SLOT_SIZE = 0x7A0000
SOURCE_DATE_EPOCH = 1785024000

EXPECTED_ROOTFS_DIFFERENCES = {
    "etc/openmitrastar/release",
    "usr/libexec/openmitrastar/om-api-v1",
}
EXPECTED_ROOTFS_DIRECTORY_CHANGES: set[str] = set()
EXPECTED_ROOTFS_CHANGES = EXPECTED_ROOTFS_DIFFERENCES | EXPECTED_ROOTFS_DIRECTORY_CHANGES

EXPECTED_MODES = {
    "etc/openmitrastar/release": 0o644,
    "usr/libexec/openmitrastar/om-api-v1": 0o755,
}

FRONTEND_ASSETS = {
    "LYOKO_UI_DASHBOARD_HTML_SHA256": "usr/share/openmitrastar/web/dashboard.html",
    "LYOKO_UI_APP_JS_SHA256": "www/app.js",
    "LYOKO_UI_APP_CSS_SHA256": "www/app.css",
    "LYOKO_UI_CAPABILITIES_CSS_SHA256": "www/capabilities.css",
    "LYOKO_UI_LAYOUT_FIXES_CSS_SHA256": "www/layout-fixes.css",
    "LYOKO_UI_LOGIN_HTML_SHA256": "www/login.html",
    "LYOKO_UI_LOGIN_CSS_SHA256": "www/login.css",
}

RADIO_EXACT_FILES = {
    "etc/init.d/S35-radio-modules",
    "etc/init.d/S50-radio-ap",
    "etc/init.d/S53-qtn-calibration",
    "etc/init.d/S54-qtn-mac",
    "etc/init.d/S55-radio5-ap",
    "etc/openmitrastar/oem-parity.conf",
    "usr/sbin/hostapd",
    "usr/sbin/hostapd-cli-qtn",
    "usr/sbin/hostapd-qtn",
    "usr/sbin/hostapd_cli",
    "usr/sbin/om-qtnctl",
    "usr/sbin/om-radio-credential-check",
    "usr/sbin/om-radio-modules",
    "usr/sbin/om-radio-start",
    "usr/sbin/om-radio-stop",
    "usr/sbin/om-radio2g-toggle",
    "usr/sbin/om-radio5-payload-verify",
    "usr/sbin/om-radio5-start",
    "usr/sbin/om-radio5-stop",
    "usr/sbin/om-radio5g-toggle",
    "usr/sbin/om-radioctl",
    "usr/sbin/om-rtlctl",
}

RADIO_EXACT_PREFIXES = (
    "etc/power_tables/",
    "etc/openmitrastar/features/q3-radio5-",
    "etc/openmitrastar/features/qtn-",
    "etc/openmitrastar/features/rtl-",
    "lib/firmware/",
    "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/",
    "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/",
    "usr/share/openmitrastar/qtn/",
    "usr/share/openmitrastar/radio2g/",
    "usr/share/openmitrastar/radio5g/",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        result[name] = digest
    return result


def require_hashed_input(directory: Path, name: str, sums: dict[str, str]) -> Path:
    path = directory / name
    if not path.is_file():
        raise SystemExit(f"missing F304 input: {path}")
    if sums.get(name) != sha256(path):
        raise SystemExit(f"input hash mismatch: {path}")
    return path


def run_wsl(script: str, distro: str, timeout: int = 900) -> str:
    proc = subprocess.run(
        ["wsl.exe", "-d", distro, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout or f"WSL failed rc={proc.returncode}")
    return proc.stdout or ""


def extract_rootfs(rootfs: Path, destination: Path, distro: str) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    run_wsl(
        "set -eu; "
        f"mkdir -p {shlex.quote(wsl_path(destination.parent))}; "
        f"unsquashfs -no-progress -d {shlex.quote(wsl_path(destination))} "
        f"{shlex.quote(wsl_path(rootfs))} >/dev/null",
        distro,
    )


def tree_inventory(root: Path, distro: str) -> dict[str, dict[str, object]]:
    script = f"""
python3 - {shlex.quote(wsl_path(root))} <<'PY'
import hashlib, json, os, stat, sys
from pathlib import Path
root = Path(sys.argv[1])
result = {{}}
for item in sorted(root.rglob('*')):
    rel = item.relative_to(root).as_posix()
    mode = stat.S_IMODE(item.lstat().st_mode)
    row = {{"mode": mode, "type": "other"}}
    if item.is_symlink():
        row.update(type="symlink", target=os.readlink(item))
    elif item.is_file():
        row.update(type="file", bytes=item.stat().st_size, sha256=hashlib.sha256(item.read_bytes()).hexdigest())
    elif item.is_dir():
        row["type"] = "dir"
    result[rel] = row
print(json.dumps(result, sort_keys=True))
PY
"""
    return json.loads(run_wsl(script, distro))


def file_hashes(inventory: dict[str, dict[str, object]]) -> dict[str, str]:
    return {
        name: str(row["sha256"])
        for name, row in inventory.items()
        if row.get("type") == "file"
    }


def radio_hashes(all_hashes: dict[str, str]) -> dict[str, str]:
    return {
        name: digest
        for name, digest in all_hashes.items()
        if name in RADIO_EXACT_FILES or name.startswith(RADIO_EXACT_PREFIXES)
    }


def map_digest(values: dict[str, str]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def symbolic_mode(value: str) -> int:
    mode = 0
    for index, bit in enumerate((0o400, 0o200, 0o100, 0o040, 0o020, 0o010, 0o004, 0o002, 0o001), start=1):
        if len(value) > index and value[index] != "-":
            mode |= bit
    if len(value) > 9 and value[9] in ("t", "T"):
        mode |= stat.S_ISVTX
    return mode


def squashfs_modes(rootfs: Path, distro: str) -> dict[str, int]:
    output = run_wsl(f"unsquashfs -ll {shlex.quote(wsl_path(rootfs))}", distro)
    result: dict[str, int] = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or not fields[5].startswith("squashfs-root/"):
            continue
        result[fields[5].removeprefix("squashfs-root/")] = symbolic_mode(fields[0])
    return result


def overlay_build_id(source_rootfs: Path) -> str:
    digest = hashlib.sha256(sha256(source_rootfs).encode("ascii"))
    for path in sorted(item for item in FOUNDATION_SOURCE.rglob("*") if item.is_file()):
        digest.update(path.relative_to(FOUNDATION_SOURCE).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def validate_source_overlay() -> None:
    actual = {
        path.relative_to(FOUNDATION_SOURCE).as_posix()
        for path in FOUNDATION_SOURCE.rglob("*")
        if path.is_file()
    }
    expected = EXPECTED_ROOTFS_DIFFERENCES - {"etc/openmitrastar/release"}
    if actual != expected:
        raise SystemExit(f"unexpected F304 source overlay paths: {sorted(actual ^ expected)}")
    for path in FOUNDATION_SOURCE.rglob("*"):
        if not path.is_file() or path.suffix == ".ko":
            continue
        text = path.read_text(encoding="utf-8")
        if "rootfs_live_bytes\":6422528" in text:
            raise SystemExit(f"stale rootfs size constant in F304 source: {path}")


def build_rootfs(
    source_rootfs: Path,
    target_rootfs: Path,
    base_tree: Path,
    final_tree: Path,
    inventory_path: Path,
    superblock_path: Path,
    distro: str,
) -> dict[str, object]:
    build_id = overlay_build_id(source_rootfs)
    mode_commands = "\n".join(
        f"chmod {mode:04o} \"$stage/new/{name}\""
        for name, mode in sorted(EXPECTED_MODES.items())
    )
    shell = f"""
set -eu
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
source_sq={shlex.quote(wsl_path(source_rootfs))}
overlay={shlex.quote(wsl_path(FOUNDATION_SOURCE))}
target_sq={shlex.quote(wsl_path(target_rootfs))}
base_out={shlex.quote(wsl_path(base_tree))}
final_out={shlex.quote(wsl_path(final_tree))}
inventory={shlex.quote(wsl_path(inventory_path))}
superblock={shlex.quote(wsl_path(superblock_path))}
unsquashfs -no-progress -d "$stage/base" "$source_sq" >/dev/null
cp -a "$stage/base" "$stage/new"
cp -a "$overlay/." "$stage/new/"
find "$stage/new" -type d -exec chmod 0755 {{}} +
chmod 01777 "$stage/new/tmp"
sed -i 's/^OPENMITRASTAR_PRODUCT_VERSION=.*/OPENMITRASTAR_PRODUCT_VERSION={PRODUCT_VERSION}/' "$stage/new/etc/openmitrastar/release"
sed -i 's/^OPENMITRASTAR_BUILD_ID=.*/OPENMITRASTAR_BUILD_ID={build_id}/' "$stage/new/etc/openmitrastar/release"
sed -i 's/^OPENMITRASTAR_UI_VERSION=.*/OPENMITRASTAR_UI_VERSION=6.6.1/' "$stage/new/etc/openmitrastar/release"
: <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
replacements = (
    ('redirect /dashboard.html', 'redirect /dashboard.cgi'),
    ('Location: /dashboard.html', 'Location: /dashboard.cgi'),
    ('''\tcase "$endpoint" in
\tsysinfo.cgi) title='Información del equipo'; view='system' ;;''',
     '''\tcase "$endpoint" in
\tdashboard.cgi) title='Lyoko'; view='dashboard' ;;
\tsysinfo.cgi) title='Información del equipo'; view='system' ;;'''),
    ('''\tpage_shell_start "$title" "$view"
''',
     '''\tif [ "$view" = dashboard ]; then
\t\thtml_headers
\t\tprintf '\\r\\n'
\t\tcat /usr/share/openmitrastar/web/dashboard.html
\t\treturn
\tfi
\tpage_shell_start "$title" "$view"
'''),
    ('sysinfo.cgi|wifi24g.cgi|wifi5g.cgi|wifi5g_sta.cgi|lan.cgi|advanced.cgi|wifi5g_adv.cgi|wizard_help.cgi|wps24_info.cgi|wps5g_info.cgi)',
     'dashboard.cgi|sysinfo.cgi|wifi24g.cgi|wifi5g.cgi|wifi5g_sta.cgi|lan.cgi|advanced.cgi|wifi5g_adv.cgi|wizard_help.cgi|wps24_info.cgi|wps5g_info.cgi)'),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f'om-oem-cgi dashboard patch anchor matched {{text.count(old)}} times: {{old[:60]}}')
    text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
PY
{mode_commands}
python3 - "$stage/new" <<'PY'
import hashlib, sys
from pathlib import Path
root = Path(sys.argv[1])
values = {{}}
for line in (root / 'etc/lyoko/frontend.env').read_text(encoding='ascii').splitlines():
    if '=' in line:
        key, value = line.split('=', 1); values[key] = value
assets = {json.dumps(FRONTEND_ASSETS, sort_keys=True)}
total = 0
for key, relative in assets.items():
    path = root / relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if values.get(key) != digest:
        raise SystemExit(f'frontend hash mismatch {{key}}: {{digest}} != {{values.get(key)}}')
    total += path.stat().st_size
if int(values.get('LYOKO_UI_ASSET_BYTES', '-1')) != total:
    raise SystemExit(f'frontend asset byte mismatch {{total}}')
if values.get('LYOKO_UI_VERSION') != '6.6.1':
    raise SystemExit('frontend version mismatch')
if values.get('LYOKO_UI_SOURCE') != 'lyoko-foundation-6.6.1-f301-f300-capability-truth':
    raise SystemExit('frontend source mismatch')
PY
python3 - "$stage/base" "$stage/new" "$inventory" <<'PY'
import hashlib, json, os, stat, sys
from pathlib import Path
base, new, output = map(Path, sys.argv[1:])
def inventory(root):
    result = {{}}
    for item in sorted(root.rglob('*')):
        rel = item.relative_to(root).as_posix(); mode = stat.S_IMODE(item.lstat().st_mode)
        row = {{"mode": mode, "type": "other"}}
        if item.is_symlink(): row.update(type="symlink", target=os.readlink(item))
        elif item.is_file(): row.update(type="file", bytes=item.stat().st_size, sha256=hashlib.sha256(item.read_bytes()).hexdigest())
        elif item.is_dir(): row["type"] = "dir"
        result[rel] = row
    return result
old=inventory(base); cur=inventory(new)
changed=sorted(p for p in set(old)|set(cur) if old.get(p)!=cur.get(p))
Path(output).write_text(json.dumps({{"schema":"openmitrastar.f304-api-rootfs-diff/v1","changed_paths":changed,"old":{{p:old.get(p) for p in changed}},"new":{{p:cur.get(p) for p in changed}}}},indent=2,sort_keys=True)+"\\n",encoding="ascii")
PY
find "$stage/new" -exec touch -h -d '@{SOURCE_DATE_EPOCH}' {{}} +
rm -f "$target_sq"
mksquashfs "$stage/new" "$target_sq" -noappend -all-root -comp xz -b 131072 -no-xattrs -no-exports -all-time {SOURCE_DATE_EPOCH} -mkfs-time {SOURCE_DATE_EPOCH} -no-progress >/dev/null
rm -rf "$base_out" "$final_out"
cp -a "$stage/base" "$base_out"
unsquashfs -no-progress -d "$final_out" "$target_sq" >/dev/null
unsquashfs -s "$target_sq" >"$superblock"
"""
    run_wsl(shell, distro)
    diff = json.loads(inventory_path.read_text(encoding="ascii"))
    changed = set(diff["changed_paths"])
    if changed != EXPECTED_ROOTFS_CHANGES:
        raise SystemExit(f"F304 changed unexpected rootfs paths: {sorted(changed ^ EXPECTED_ROOTFS_CHANGES)}")
    return {
        "schema": "openmitrastar.f304-api-assets/v1",
        "build_id": build_id,
        "source_rootfs": {"sha256": sha256(source_rootfs)},
        "rootfs": {"bytes": target_rootfs.stat().st_size, "sha256": sha256(target_rootfs)},
        "rootfs_diff": diff,
        "hardware_actions": {"router": False, "uart": False, "ssh": False, "tftp": False, "flash": False},
    }


def validate_frontend(root: Path) -> None:
    values = {}
    for line in (root / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    total = 0
    for key, relative in FRONTEND_ASSETS.items():
        path = root / relative
        if values.get(key) != sha256(path):
            raise SystemExit(f"packaged frontend hash mismatch: {key}")
        total += path.stat().st_size
    if int(values.get("LYOKO_UI_ASSET_BYTES", -1)) != total:
        raise SystemExit("packaged frontend byte total mismatch")


def validate_runtime_text(root: Path, distro: str) -> None:
    script = f"""
python3 - {shlex.quote(wsl_path(root))} <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
bad = []
for path in root.rglob('*'):
    if path.is_symlink() or not path.is_file():
        continue
    data = path.read_bytes()
    if b'\\0' in data:
        continue
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        continue
    if 'F298' in text or 'F293 pendiente' in text:
        bad.append(path.relative_to(root).as_posix())
if bad:
    raise SystemExit('stale runtime labels: ' + ', '.join(bad))
PY
"""
    run_wsl(script, distro)


def compose_image(assets: Path, output: Path, base: str) -> None:
    names = ("ASSETS", "OUT", "BASE", "ROOTFS_WINDOW")
    old = {name: getattr(compose, name) for name in names}
    try:
        compose.ASSETS = assets
        compose.OUT = output
        compose.BASE = base
        compose.ROOTFS_WINDOW = ROOTFS_WINDOW
        if compose.main():
            raise SystemExit("F304 image composition failed")
    finally:
        for name, value in old.items():
            setattr(compose, name, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="hgw500bna-qcv2-a2-primary")
    parser.add_argument("--identity-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--private-output-root", type=Path, default=Path.home() / ".openmitrastar/devices")
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--dropbearkey", default=DEFAULT_TOOL)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if not DEVICE_RE.fullmatch(args.device_id):
        raise SystemExit("invalid --device-id")
    validate_source_overlay()

    private_root = args.private_output_root.resolve()
    firmware_root = private_root / args.device_id / "firmware"
    f301 = firmware_root / "f301-device-bound"
    f301_base = f"openmitrastar-linux510-f301-{args.device_id}-PRIVATE-NO-FLASH"
    f301_manifest = json.loads((f301 / "manifest.json").read_text(encoding="ascii"))
    f301_sums = load_sums(f301 / "SHA256SUMS")

    device_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((device_dir / "identity.json").read_text(encoding="utf-8"))
    key = device_dir / "dropbear_ed25519_host_key"
    public_key = (device_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    if inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")
    if identity["fingerprint"] != f301_manifest["device_identity"]["fingerprint"]:
        raise SystemExit("private identity does not match F301")

    final_out = firmware_root / "f304-device-bound"
    if final_out.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if final_out.exists():
        if final_out.name != "f304-device-bound" or final_out.parent != firmware_root:
            raise SystemExit(f"unsafe replacement target: {final_out}")
        shutil.rmtree(final_out)

    scratch = ROOT / ".codex_tmp" / f"f304-device-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)

    def cleanup() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup)
    assets = scratch / "assets"
    output = scratch / "build"
    base_tree = scratch / "f301-rootfs"
    final_tree = scratch / "f304-rootfs"
    assets.mkdir(parents=True, exist_ok=True)

    kernel_copies = {
        ".uncompressed.uImage": "kernel-squashfs.uncompressed.uImage",
        ".kernel.raw.bin": "kernel-squashfs.raw.bin",
        ".kernel.lzma": "kernel-squashfs.lzma",
        ".config": "kernel-squashfs.config",
        ".dtb": "topaz_mitrastar_squashfs.dtb",
        ".vmlinux": "kernel-squashfs.vmlinux",
    }
    for suffix, target_name in kernel_copies.items():
        source_name = f"{f301_base}{suffix}"
        shutil.copy2(require_hashed_input(f301, source_name, f301_sums), assets / target_name)
    source_rootfs = require_hashed_input(f301, f"{f301_base}.rootfs.squashfs", f301_sums)
    target_rootfs = assets / "rootfs-product-xz-128k.squashfs"
    assets_report = build_rootfs(
        source_rootfs,
        target_rootfs,
        base_tree,
        final_tree,
        assets / "rootfs-diff.json",
        assets / "rootfs-product-xz-superblock.txt",
        args.distro,
    )
    base_inventory = tree_inventory(base_tree, args.distro)
    final_inventory = tree_inventory(final_tree, args.distro)
    packed_modes = squashfs_modes(target_rootfs, args.distro)
    for name, expected_mode in EXPECTED_MODES.items():
        actual_mode = packed_modes[name]
        if actual_mode != expected_mode:
            raise SystemExit(f"F304 packaged mode mismatch {name}: {actual_mode:o} != {expected_mode:o}")
    validate_frontend(final_tree)
    validate_runtime_text(final_tree, args.distro)

    f301_radio = radio_hashes(file_hashes(base_inventory))
    f304_radio = radio_hashes(file_hashes(final_inventory))
    if not f301_radio or f304_radio != f301_radio:
        raise SystemExit("F304 radio modules, firmware, scripts or configuration differ from F301")

    base = f"openmitrastar-linux510-f304-{args.device_id}-PRIVATE-NO-FLASH"
    compose_image(assets, output, base)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    rootfs = output / f"{base}.rootfs.squashfs"
    verify_embedded_key(rootfs, identity["fingerprint"], args.distro, args.dropbearkey, scratch)

    for suffix in kernel_copies:
        if sha256(output / f"{base}{suffix}") != sha256(f301 / f"{f301_base}{suffix}"):
            raise SystemExit(f"F304 kernel-side artifact differs from F301: {suffix}")
    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    if candidate_data[ROOTFS_OFFSET:] != rootfs.read_bytes():
        raise SystemExit("F304 candidate does not embed the corrected F304 rootfs")
    full_slot = candidate_data + b"\xff" * (SLOT_SIZE - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F304 candidate overlaps or initializes lyoko_store")

    manifest.update({
        "schema": "openmitrastar.f304-api-contract-offline/v1",
        "classification": "PRIVATE_DEVICE_BOUND_OFFLINE_API_CANDIDATE",
        "candidate_eligible": False,
        "release_eligible": False,
        "flash_supported": False,
        "device_identity": f301_manifest["device_identity"],
        "web_identity": f301_manifest["web_identity"],
        "web_security": f301_manifest["web_security"],
        "source": {
            "kernel_and_runtime_base": "exact installed and physically accepted F301",
            "overlay": "versions/lyoko-foundation-6.7.1-f304-api-contract/overlay",
            "f301_kernel_lzma_sha256": f301_manifest["artifacts"]["kernel_lzma"]["sha256"],
            "f301_rootfs_sha256": f301_manifest["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "binary_contract": f301_manifest["binary_contract"],
        "inherited_f301_contracts": f301_manifest["contracts"],
        "native_qtn_control": f301_manifest["native_qtn_control"],
        "native_rtl_control": f301_manifest["native_rtl_control"],
        "config_apply": f301_manifest["config_apply"],
        "transaction_hardening": f301_manifest["transaction_hardening"],
        "dfs_observability": f301_manifest["dfs_observability"],
        "network_observability": f301_manifest["network_observability"],
        "hardware_provenance": f301_manifest["hardware_provenance"],
        "package_catalog": f301_manifest["package_catalog"],
        "package_runtime_fix": f301_manifest["package_runtime_fix"],
        "opkg_compatibility": f301_manifest["opkg_compatibility"],
        "led_control": f301_manifest["led_control"],
        "config_store": f301_manifest["config_store"],
        "transaction_review": f301_manifest.get("transaction_review", {}),
        "package_web": f301_manifest.get("package_web", {}),
        "hardware_inventory": f301_manifest["hardware_inventory"],
        "developer_console": {
            **f301_manifest["developer_console"],
            "firmware_line": "F304 API offline",
            "api_contract": "canonical PATCH radios path plus explicit volatile and fail-closed metadata",
        },
        "store_protection_observer": f301_manifest["store_protection_observer"],
        "multicast_certification": f301_manifest["multicast_certification"],
        "api_contract": {
            "schema": "lyoko.api.audit/v1",
            "base": "F301",
            "canonical_radio_patch": True,
            "legacy_stage_alias": True,
            "dfs_write_enabled": False,
            "firmware_write_api": False,
            "persistent_config_writes": False,
            "persistent_package_writes": False,
            "package_install_scope": "ram-only and feature-gated",
            "rootfs_size_source": "/proc/mtd",
            "hardware_status": "NOT_RUN",
        },
        "foundation_assets": assets_report,
        "integration": {
            "additional_kernel_changes": [],
            "additional_rootfs_changes": sorted(EXPECTED_ROOTFS_CHANGES),
            "f301_kernel_artifacts_byte_identical": True,
            "f301_rootfs_is_functional_base": True,
            "f304_overlay_path_count": len(EXPECTED_ROOTFS_DIFFERENCES) - 1,
            "radio_payload_file_count": len(f301_radio),
            "radio_payload_sha256": map_digest(f301_radio),
            "radio_payload_byte_identical_to_f301": True,
            "stale_runtime_labels_absent": True,
            "packaged_modes_verified": {name: f"{mode:04o}" for name, mode in sorted(EXPECTED_MODES.items())},
        },
        "change_scope": {
            "kernel_datapath": "byte-identical to physically accepted F301",
            "rootfs_base": "exact F301 rootfs",
            "rootfs_overlay": "API-only F304 corrections; frontend, radio controls, packages and hardware payload remain byte-identical to F301",
            "private_identity": "same device-bound Ed25519 identity and web credential contract as F301",
            "radio_modules_firmware_config": "byte-identical to F301",
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "not requested in this task; candidate remains offline and non-flashable",
        },
        "storage": {
            **f301_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": f301_manifest["spi_probe"],
        "safety": {
            "normal_write_target": "mtd4/linux_live only after a separate physical gate",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs view; never a physical write target",
            "hardware_actions": "none; offline build only",
        },
    })
    manifest["layout"]["mtd_mapping"] = f301_manifest["layout"]["mtd_mapping"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f304").write_text(
        f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n"
    )
    restrict_acl(final_out, directory=True)
    for path in final_out.iterdir():
        if path.is_file():
            restrict_acl(path, directory=False)

    print(json.dumps({
        "status": "PASS",
        "classification": manifest["classification"],
        "output": str(final_out),
        "candidate": str(final_out / manifest["artifacts"]["webformat"]["file"]),
        "bytes": manifest["artifacts"]["webformat"]["bytes"],
        "sha256": manifest["artifacts"]["webformat"]["sha256"],
        "full_slot_crc32": f"{zlib.crc32(full_slot) & 0xffffffff:08x}",
        "full_slot_sha256": hashlib.sha256(full_slot).hexdigest(),
        "kernel_sha256": manifest["artifacts"]["kernel_lzma"]["sha256"],
        "rootfs_sha256": manifest["artifacts"]["rootfs_squashfs"]["sha256"],
        "radio_payload_files": len(f301_radio),
        "hardware_actions": {"router": False, "uart": False, "ssh": False, "tftp": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
