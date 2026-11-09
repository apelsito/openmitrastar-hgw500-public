#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
source="$root/tools/om_qtn_mac_import.c"
service_root="$root/work/mission-state/w3-qtn-mac-import/rootfs"
omspiro="$root/outputs/kernel-port/omspiro-readonly-RAM-ONLY-NO-FLASH/omspiro.ko"
out="$root/outputs/kernel-port/openmitrastar-q3-qtn-mac-import-20260821"
stage="$out/rootfs"
build=/home/user/openmitrastar-build/qtn-mac-import
release=5.10.260-openmitrastar-radiohw

test -f "$source"
test -x "${tc}gcc"
test -x "${tc}strip"
test -f "$omspiro"
test "$(sha256sum "$omspiro" | awk '{print $1}')" = \
	7e00484816f37496f263e22e1bb286d8383681f1af4ad5629cd49ca97d659201

rm -rf "$out"
mkdir -p "$build" "$stage/usr/sbin" "$stage/etc/init.d" \
	"$stage/lib/modules/$release/openmitrastar/identity" \
	"$stage/usr/share/openmitrastar/qtn-mac-import"

"${tc}gcc" -static -Os -Wall -Wextra -Werror -mcpu=arc700 \
	"$source" -o "$build/om-qtn-mac-import"
"${tc}strip" "$build/om-qtn-mac-import"
cp "$build/om-qtn-mac-import" "$stage/usr/sbin/om-qtn-mac-import"
cp "$omspiro" "$stage/lib/modules/$release/openmitrastar/identity/omspiro.ko"
cp "$service_root/etc/init.d/S24-qtn-mac-import" "$stage/etc/init.d/S24-qtn-mac-import"

helper_sha=$(sha256sum "$stage/usr/sbin/om-qtn-mac-import" | awk '{print $1}')
omspiro_sha=$(sha256sum "$omspiro" | awk '{print $1}')
sed -e "s/@HELPER_SHA256@/$helper_sha/" \
	-e "s/@OMSPIRO_SHA256@/$omspiro_sha/" \
	"$service_root/usr/share/openmitrastar/qtn-mac-import/runtime.env.in" \
	>"$stage/usr/share/openmitrastar/qtn-mac-import/runtime.env"

chmod 0755 "$stage/usr/sbin/om-qtn-mac-import" \
	"$stage/etc/init.d/S24-qtn-mac-import"
chmod 0600 "$stage/usr/share/openmitrastar/qtn-mac-import/runtime.env"
chmod 0644 "$stage/lib/modules/$release/openmitrastar/identity/omspiro.ko"

SOURCE_DATE_EPOCH=1785024000
export SOURCE_DATE_EPOCH
find "$stage" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
	-czf "$out/openmitrastar-q3-qtn-mac-import-overlay.tar.gz" -C "$stage" .

(
	cd "$out"
	find rootfs -type f -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS
	sha256sum openmitrastar-q3-qtn-mac-import-overlay.tar.gz >>SHA256SUMS
)

cat >"$out/manifest.json" <<EOF
{
  "schema": "openmitrastar.qtn-mac-import/v1",
  "classification": "PRODUCT-READ-ONLY-IDENTITY-IMPORT",
  "compatible": "mitrastar,hgw-500bna-qcv2",
  "kernel_release": "$release",
  "source": "/dev/omspiro",
  "source_mode": "0400",
  "primary_offset": "0x00020000",
  "backup_offset": "0x00030000",
  "environment_bytes": 65536,
  "crc_region_end": "0x00006000",
  "identity_keys": ["ethaddr", "wifiaddr"],
  "identity_invariant": "wifiaddr=ethaddr+1",
  "output": "/run/openmitrastar/secrets/qtn-mac0addr",
  "output_mode": "0600",
  "helper_sha256": "$helper_sha",
  "omspiro_sha256": "$omspiro_sha",
  "flash_write_paths": 0
}
EOF

echo "Q3_QTN_MAC_IMPORT_BUILD_PASS helper_sha256=$helper_sha omspiro_sha256=$omspiro_sha"
