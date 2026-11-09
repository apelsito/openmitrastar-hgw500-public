#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sysroot=${ARC_NOATOMIC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
out="$root/outputs/kernel-port/realtek-control-plane"

mkdir -p "$out"
"${tc}gcc" --sysroot="$sysroot" -Os -g0 -mno-atomic \
	-fno-stack-protector -static -Wl,--gc-sections \
	"$root/tools/arc700_pci_resource_read.c" -o "$out/pci_resource_read"
"${tc}readelf" -h "$out/pci_resource_read" | \
	grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
"${tc}readelf" -l "$out/pci_resource_read" | \
	grep -qv 'Requesting program interpreter'
if "${tc}objdump" -d "$out/pci_resource_read" | grep -Eq '\b(llock|scond)\b'; then
	echo 'PCI resource reader contains unsupported ARC atomics' >&2
	exit 3
fi
sha256sum "$out/pci_resource_read" > "$out/pci_resource_read.sha256"
printf 'PCI_RESOURCE_READ_BUILD_PASS bytes=%s sha256=' \
	"$(wc -c < "$out/pci_resource_read")"
cut -d' ' -f1 "$out/pci_resource_read.sha256"
