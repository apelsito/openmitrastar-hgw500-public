#!/bin/sh
set -eu

# Offline-only builder. It never opens the router, UART, TFTP or flash.
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source="$root/tools/om_bridge_fdb_nolibc.c"
test_source="$root/tools/test_om_bridge_fdb_nolibc.py"
out="$root/outputs/kernel-port/realtek-loop/bridge-fdb-discriminator-RAM-ONLY-NO-FLASH"
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
binary="$out/om_bridge_fdb"
tmp="$out/.om_bridge_fdb.tmp"

test -f "$source"
test -f "$test_source"
test -x "${tc}gcc"
test -x "${tc}strip"
test -x "${tc}readelf"
test -x "${tc}objdump"
mkdir -p "$out"
rm -f "$tmp"

"${tc}gcc" -Os -mcpu=arc700 -mno-atomic -fno-stack-protector \
	-fno-builtin -fno-pic -fno-pie -no-pie -ffreestanding -nostdlib \
	-static -Wl,-e,_start -Wl,--build-id=none -s "$source" -o "$tmp"
"${tc}strip" "$tmp"
chmod 0755 "$tmp"

"${tc}readelf" -h "$tmp" | grep -q 'Machine:.*ARCompact'
"${tc}readelf" -h "$tmp" | grep -q 'ARC700, v4 ABI'
if ! "${tc}readelf" -d "$tmp" 2>&1 | grep -q 'There is no dynamic section'; then
	echo 'unexpected dynamic section' >&2
	exit 1
fi
if "${tc}objdump" -d "$tmp" | grep -Eq '\b(llock|scond)\b'; then
	echo 'unsupported ARC atomic instruction found' >&2
	exit 1
fi
for marker in OMFDB_SUM arc700-nolibc-readonly brforward-record-size; do
	strings "$tmp" | grep -Fq "$marker"
done

mv "$tmp" "$binary"
binary_sha=$(sha256sum "$binary" | awk '{print $1}')
source_sha=$(sha256sum "$source" | awk '{print $1}')
test_sha=$(sha256sum "$test_source" | awk '{print $1}')
bytes=$(wc -c <"$binary" | tr -d ' ')

cat >"$out/manifest.json" <<EOF
{
  "schema": "openmitrastar.bridge-fdb-discriminator/v1",
  "classification": "RAM-ONLY-NO-FLASH",
  "target": "mitrastar,hgw-500bna-qcv2",
  "artifact": "om_bridge_fdb",
  "binary_sha256": "$binary_sha",
  "binary_bytes": $bytes,
  "source": "tools/om_bridge_fdb_nolibc.c",
  "source_sha256": "$source_sha",
  "test_source_sha256": "$test_sha",
  "runtime": "arc700-syscall-only-no-libc-no-tls-no-atomics",
  "commands": ["dump br0", "lookup br0 MAC"],
  "mutates_network": false,
  "flash_supported": false,
  "hardware_validation": "pending"
}
EOF
(
	cd "$out"
	sha256sum om_bridge_fdb manifest.json >SHA256SUMS
)
printf 'OMFDB_BUILD_PASS sha256=%s bytes=%s\n' "$binary_sha" "$bytes"
