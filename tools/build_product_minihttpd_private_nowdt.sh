#!/bin/sh

# Rebuild the private POSIX-timer product candidate with the W4 CGI runtime and
# no early watchdog canary. The PSK is read from an explicit private file and
# is never printed or written to a manifest.
set +x
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
core="$workspace/work/mission-state/w5-product-ram-candidate/scripts/build_product_ram_candidate.sh"
rootfs="$workspace/work/mission-state/w4-rootfs-product/build/openmitrastar-product-rootfs-v1.squashfs"
rootfs_manifest="$workspace/work/mission-state/w4-rootfs-product/build/manifest.json"
psk_file=${OM_PRODUCT_PRIVATE_PSK_FILE:-$workspace/work/mission-state/.openmitrastar-lab.psk}
artifact_dir="$workspace/work/mission-state/f3-product-minihttpd-private-nowdt/build"
build_root=${OM_PRODUCT_PRIVATE_NOWDT_BUILD_ROOT:-/home/user/openmitrastar-build/product-minihttpd-private-nowdt}
base=openmitrastar-linux510-product-minihttpd-posix-private-nowdt-v1
tftp="$workspace/work/tftp/omvl/linux510-product-minihttpd-posix-private-nowdt-v1-RAM-ONLY.bin"

for required in "$core" "$rootfs" "$rootfs_manifest" "$psk_file"; do
	[ -f "$required" ] || { printf 'missing private candidate input: %s\n' "$required" >&2; exit 3; }
done
[ ! -L "$psk_file" ] || { echo 'private PSK input must not be a symlink' >&2; exit 3; }
case "$build_root" in /home/user/openmitrastar-build/*) ;; *) echo "unsafe private build root: $build_root" >&2; exit 2 ;; esac

python3 - "$rootfs" "$rootfs_manifest" <<'PY'
import hashlib, json, sys
from pathlib import Path

rootfs, manifest_path = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
sha = hashlib.sha256(rootfs.read_bytes()).hexdigest()
if manifest.get("rootfs", {}).get("sha256") != sha:
    raise SystemExit("private candidate rootfs/manifest mismatch")
if manifest.get("inputs", {}).get("cgi_firmware_receiver_sha256") != "588a917d1c3d77a757e800fbb04db7661a52799d4309cb1753afcd7f9617d3b5":
    raise SystemExit("private candidate lacks the pinned firmware receiver")
if manifest.get("runtime", {}).get("api", {}).get("server") != "mini_httpd/1.19-static-no-ssl":
    raise SystemExit("private candidate lacks the pinned mini_httpd runtime")
PY

private_psk=$(python3 - "$psk_file" <<'PY'
from pathlib import Path
import sys

raw = Path(sys.argv[1]).read_bytes()
if b"\x00" in raw:
    raise SystemExit("private PSK file contains NUL")
try:
    value = raw.decode("ascii").rstrip("\r\n")
except UnicodeDecodeError:
    raise SystemExit("private PSK file is not ASCII")
print(value, end="")
PY
)

unset OM_PRODUCT_WDT_FRAGMENT || true
OM_PRODUCT_RAM_ARTIFACT_DIR="$artifact_dir" \
OM_PRODUCT_RAM_BASENAME="$base" \
OM_PRODUCT_TFTP_OUTPUT="$tftp" \
OM_PRODUCT_RAM_BUILD_ROOT="$build_root" \
OM_PRODUCT_ROOTFS_IMAGE="$rootfs" \
OM_PRODUCT_ROOTFS_MANIFEST="$rootfs_manifest" \
OM_PRODUCT_PRIVATE_BUILD=1 \
OM_PRODUCT_PRIVATE_PSK="$private_psk" \
sh "$core"
unset private_psk OM_PRODUCT_PRIVATE_PSK

python3 - "$artifact_dir/manifest.json" "$rootfs_manifest" <<'PY'
import hashlib, json, sys
from pathlib import Path

candidate_path, rootfs_manifest_path = map(Path, sys.argv[1:])
candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
rootfs = json.loads(rootfs_manifest_path.read_text(encoding="utf-8"))
if candidate.get("private_build") is not True:
    raise SystemExit("private candidate manifest lost private_build")
if candidate.get("product_watchdog", {}).get("enabled") is not False:
    raise SystemExit("private no-WDT candidate unexpectedly enabled watchdog")
if candidate.get("kernel_integration_gates", {}).get("posix_timers") is not True:
    raise SystemExit("private no-WDT candidate lacks POSIX timers")
candidate["cgi_runtime"] = {
    "overlay_manifest_sha256": rootfs["inputs"]["cgi_overlay_manifest_sha256"],
    "product_stamp_sha256": rootfs["inputs"]["cgi_product_stamp_sha256"],
    "dispatcher_sha256": rootfs["inputs"]["cgi_dispatcher_sha256"],
    "mini_httpd_sha256": rootfs["inputs"]["cgi_mini_httpd_sha256"],
    "firmware_receiver_sha256": rootfs["inputs"]["cgi_firmware_receiver_sha256"],
    "firmware_receiver_path": "/usr/libexec/openmitrastar/om-firmware-recv",
    "firmware_staging": "validation-only-volatile-no-flash-no-reboot",
}
candidate["offline_gates"] = {
    "rootfs_reproducible": True,
    "kernel_two_isolated_builds_reproducible": True,
    "cgi_runtime_bound": True,
    "watchdog_disabled": True,
    "hardware_ram_boot_exact_image": "pending",
}
candidate["candidate_eligible"] = False
candidate["flash_supported"] = False
candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf 'OMPRODUCT_PRIVATE_NOWDT_BUILD_PASS sha256=%s bytes=%s receiver=588a917d1c3d77a757e800fbb04db7661a52799d4309cb1753afcd7f9617d3b5 watchdog=0\n' \
	"$(sha256sum "$artifact_dir/$base.webformat.bin" | cut -d' ' -f1)" \
	"$(wc -c <"$artifact_dir/$base.webformat.bin")"
