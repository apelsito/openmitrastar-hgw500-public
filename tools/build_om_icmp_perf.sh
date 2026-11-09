#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sysroot=${ARC_NOATOMIC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
out="$root/outputs/kernel-port/realtek-perf-v4"

mkdir -p "$out"
"${tc}gcc" --sysroot="$sysroot" -Os -g0 -mno-atomic \
	-fno-stack-protector -static -Wl,--gc-sections \
	"$root/tools/om_icmp_perf.c" -o "$out/om_icmp_perf"
"${tc}readelf" -h "$out/om_icmp_perf" | \
	grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
"${tc}readelf" -l "$out/om_icmp_perf" | \
	grep -qv 'Requesting program interpreter'
if "${tc}objdump" -d "$out/om_icmp_perf" | grep -Eq '\b(llock|scond)\b'; then
	echo 'om_icmp_perf contains unsupported ARC atomics' >&2
	exit 3
fi
sha256sum "$out/om_icmp_perf" > "$out/om_icmp_perf.sha256"
printf 'OM_ICMP_PERF_BUILD_PASS bytes=%s sha256=' "$(wc -c < "$out/om_icmp_perf")"
cut -d' ' -f1 "$out/om_icmp_perf.sha256"
