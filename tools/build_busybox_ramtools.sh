#!/bin/sh
set -eu

# Build a no-atomic ARC700 BusyBox used only from RAM.  It provides both
# sha256sum and insmod without depending on the rescue initramfs applet set.

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=${RAMTOOLS_BUSYBOX_SOURCE:-/home/user/openmitrastar-ssh-lab/busybox-1.38.0}
build_tree=${RAMTOOLS_BUSYBOX_BUILD:-/home/user/openmitrastar-build/busybox-ramtools-src}
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
jobs=${TOPAZ_JOBS:-12}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
binary="$build_tree/busybox"

case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
test "$jobs" -gt 0
test -f "$source_tree/Makefile"
test -f "$source_tree/.config"
test -x "$kernel_src/scripts/config"
test -x "${tc}objdump"

validate()
{
	test -x "$binary" || return 1
	grep -qx 'CONFIG_STATIC=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_SHA256SUM=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_INSMOD=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_FEATURE_CMDLINE_MODULE_OPTIONS=y' \
		"$build_tree/.config" || return 1
	grep -qx 'CONFIG_FEATURE_MD5_SHA1_SUM_CHECK=y' \
		"$build_tree/.config" || return 1
	strings "$binary" | grep -qx sha256sum || return 1
	strings "$binary" | grep -qx insmod || return 1
	if "${tc}objdump" -d "$binary" | grep -Eq '\b(llock|scond)\b'; then
		return 1
	fi
}

if ! validate; then
	if [ ! -d "$build_tree" ]; then
		cp -a "$source_tree" "$build_tree"
	fi
	make -s -C "$build_tree" mrproper
	cp "$source_tree/.config" "$build_tree/.config"
	"$kernel_src/scripts/config" --file "$build_tree/.config" \
		--enable SHA256SUM --enable INSMOD \
		--enable FEATURE_CMDLINE_MODULE_OPTIONS \
		--enable FEATURE_MD5_SHA1_SUM_CHECK
	yes '' | make -s -C "$build_tree" oldconfig >/dev/null
	make -C "$build_tree" -j"$jobs" busybox
	validate
fi

printf 'RAMTOOLS_BUSYBOX_PASS sha256='
sha256sum "$binary" | cut -d' ' -f1
