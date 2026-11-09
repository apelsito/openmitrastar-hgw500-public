#!/bin/sh
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
core="$workspace/work/mission-state/w5-product-ram-candidate/scripts/build_product_ram_candidate.sh"
src_config="$workspace/work/mission-state/f5-safe2g-gzipinit/build/openmitrastar-linux510-f5-safe2g-gzipinit-v1.config"
rootfs_image="$workspace/work/mission-state/f5-safe2g-rootfs/build/openmitrastar-product-rootfs-safe2g-v1.squashfs"
rootfs_manifest="$workspace/work/mission-state/f5-safe2g-rootfs/build/manifest.json"
lane="$workspace/work/mission-state/f5-safe2g-emacresync-gzipinit"
build="$lane/build"
base_config="$lane/openmitrastar-linux510-f5-safe2g-emacresync-gzipinit-v1.base.config"
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
build_root=${OM_F5_SAFE2G_EMACRESYNC_BUILD_ROOT:-/home/user/openmitrastar-build/f5-safe2g-emacresync-gzipinit}
base=openmitrastar-linux510-f5-safe2g-emacresync-gzipinit-v1
tftp="$workspace/work/tftp/omvl/$base.webformat.bin"

for required in "$core" "$src_config" "$rootfs_image" "$rootfs_manifest" \
	"$kernel_src/scripts/config"; do
	[ -e "$required" ] || { echo "missing input: $required" >&2; exit 3; }
done
case "$build_root" in /home/user/openmitrastar-build/*) ;; *) echo "unsafe build root: $build_root" >&2; exit 2 ;; esac

rm -rf -- "$lane"
mkdir -p "$lane" "$build"
cp "$src_config" "$base_config"

cfg="$kernel_src/scripts/config --file $base_config"
$cfg --enable RD_GZIP
$cfg --disable INITRAMFS_COMPRESSION_NONE
$cfg --enable INITRAMFS_COMPRESSION_GZIP

OM_PRODUCT_ROOTFS_IMAGE="$rootfs_image" \
OM_PRODUCT_ROOTFS_MANIFEST="$rootfs_manifest" \
OM_PRODUCT_RAM_ARTIFACT_DIR="$build" \
OM_PRODUCT_RAM_BASENAME="$base" \
OM_PRODUCT_RAM_BUILD_ROOT="$build_root" \
OM_PRODUCT_KERNEL_CONFIG="$base_config" \
OM_PRODUCT_TFTP_OUTPUT="$tftp" \
OM_PRODUCT_RAM_FAST=1 \
sh "$core"

grep -qx 'CONFIG_RD_GZIP=y' "$build/$base.config"
grep -qx 'CONFIG_INITRAMFS_COMPRESSION_GZIP=y' "$build/$base.config"
grep -qx '# CONFIG_INITRAMFS_COMPRESSION_NONE is not set' "$build/$base.config"
grep -q 'OMPRODUCT_ENTROPY_LOCAL_OK source=jitterentropy_rng' "$build/$base.initramfs.cpio"
grep -q 'OMSSH_READY port=$port auth=ed25519-key-only forwarding=disabled' "$build/$base.initramfs.cpio"

python3 - "$build/bootbase-contract.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
if not report.get("accepted_by_contract"):
    raise SystemExit("gzip-init F5 safe2g-emacresync rejected by Bootbase contract")
if report.get("header", {}).get("compression") != 0:
    raise SystemExit("gzip-init F5 safe2g-emacresync must keep Bootbase compression=0")
if int(report.get("header", {}).get("payload_size")) > 0x7A0000:
    raise SystemExit("gzip-init F5 safe2g-emacresync payload exceeds linux_live")
PY

python3 - "$rootfs_manifest" "$build/manifest.json" <<'PY'
import json
import sys

rootfs = json.load(open(sys.argv[1], encoding="utf-8"))
candidate = json.load(open(sys.argv[2], encoding="utf-8"))
expected = rootfs.get("inputs", {}).get("bootstrap_authorized_key_fingerprint")
actual = candidate.get("source_rootfs_bootstrap_authorized_key_fingerprint")
if not expected or not actual or expected != actual:
    raise SystemExit("gzip-init F5 safe2g-emacresync bootstrap SSH key fingerprint mismatch")
PY

sha256sum "$build/$base.initramfs.cpio" "$build/$base.config" \
	"$build/$base.vmlinux" "$build/$base.uImage" "$build/$base.dtb" \
	"$build/$base.webformat.bin" "$tftp" >"$build/SHA256SUMS"

printf 'OMF5_SAFE2G_EMACRESYNC_GZIPINIT_BUILD_PASS web_sha256=%s web_bytes=%s tftp=%s\n' \
	"$(sha256sum "$build/$base.webformat.bin" | cut -d' ' -f1)" \
	"$(wc -c <"$build/$base.webformat.bin")" "$tftp"

