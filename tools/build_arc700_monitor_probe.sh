#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sysroot=${ARC_NOATOMIC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
out="$root/outputs/kernel-port/realtek-control-plane"

mkdir -p "$out"
"${tc}gcc" --sysroot="$sysroot" -Os -g0 -mno-atomic \
	-fno-stack-protector -static -Wl,--gc-sections \
	"$root/tools/arc700_monitor_probe.c" -o "$out/monitor_probe"
"${tc}readelf" -h "$out/monitor_probe" | \
	grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
"${tc}readelf" -l "$out/monitor_probe" | \
	grep -qv 'Requesting program interpreter'
if "${tc}objdump" -d "$out/monitor_probe" | grep -Eq '\b(llock|scond)\b'; then
	echo 'monitor probe contains unsupported ARC atomics' >&2
	exit 3
fi
sha256sum "$out/monitor_probe" > "$out/monitor_probe.sha256"
printf 'MONITOR_PROBE_BUILD_PASS bytes=%s sha256=' \
	"$(wc -c < "$out/monitor_probe")"
cut -d' ' -f1 "$out/monitor_probe.sha256"
