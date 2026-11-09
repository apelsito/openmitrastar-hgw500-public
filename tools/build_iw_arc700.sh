#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
jobs=${TOPAZ_JOBS:-12}
owrt=${OPENWRT_ROOT:-/home/user/router-emulation/openwrt}
iw_src=${IW_SOURCE:-$owrt/build_dir/target-arm_cortex-a7_musl_eabi/iw-tiny/iw-6.17}
nl_src=${LIBNL_TINY_SOURCE:-$owrt/build_dir/target-arm_cortex-a7_musl_eabi/libnl-tiny-2025.12.02~40493a65}
build=${IW_ARC_BUILD_ROOT:-/home/user/openmitrastar-build/iw-arc700}
iw_build="$build/iw-src"
nl_build="$build/libnl-tiny"
out="$root/outputs/kernel-port/realtek-control-plane"
sysroot=${ARC_NOATOMIC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
test "$jobs" -gt 0
test -f "$iw_src/Makefile"
test -f "$nl_src/CMakeLists.txt"
test -d "$sysroot/usr/include"
test -x "${tc}gcc"
test -x "${tc}ar"

mkdir -p "$build" "$nl_build" "$out"

nl_sources='attr cache cache_mngt error genl genl_ctrl genl_family genl_mngt handlers msg nl object socket unl'
nl_objects=''
for name in $nl_sources; do
	object="$nl_build/$name.o"
	"${tc}gcc" --sysroot="$sysroot" -Os -g0 -mno-atomic \
		-fno-stack-protector -ffunction-sections -fdata-sections \
		-D_GNU_SOURCE -I"$nl_src/include" -c "$nl_src/$name.c" -o "$object"
	nl_objects="$nl_objects $object"
done
# shellcheck disable=SC2086
"${tc}ar" rcs "$nl_build/libnl-tiny.a" $nl_objects

if [ ! -d "$iw_build" ]; then
	cp -a "$iw_src" "$iw_build"
fi
make -s -C "$iw_build" NO_PKG_CONFIG=1 clean
printf 'const char iw_version[] = "6.17-openmitrastar";\n' > \
	"$iw_build/version.c"
make -C "$iw_build" -j"$jobs" \
	CC="${tc}gcc" \
	CFLAGS="--sysroot=$sysroot -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -I$nl_src/include -DCONFIG_LIBNL20 -D_GNU_SOURCE" \
	LDFLAGS="--sysroot=$sysroot -static -Wl,--gc-sections" \
	NO_PKG_CONFIG=1 \
	LIBS="-lm $nl_build/libnl-tiny.a" V=1

cp "$iw_build/iw" "$out/iw"
"${tc}readelf" -h "$out/iw" | grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
"${tc}readelf" -l "$out/iw" | grep -qv 'Requesting program interpreter'
if "${tc}objdump" -d "$out/iw" | grep -Eq '\b(llock|scond)\b'; then
	echo 'iw unexpectedly contains unsupported ARC atomics' >&2
	exit 3
fi
sha256sum "$out/iw" > "$out/SHA256SUMS"
printf 'IW_ARC700_BUILD_PASS bytes=%s sha256=' "$(wc -c < "$out/iw")"
cut -d' ' -f1 "$out/SHA256SUMS"
