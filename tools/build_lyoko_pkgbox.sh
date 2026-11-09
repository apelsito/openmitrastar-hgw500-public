#!/bin/sh
set -eu

# Build a narrow static ARC700 BusyBox for inspecting IPK containers. This is
# an offline artifact only; it is not installed into firmware by this script.

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=${LYOKO_BUSYBOX_SOURCE:-/home/user/openmitrastar-ssh-lab/busybox-1.38.0}
build_tree=${LYOKO_PKGBOX_BUILD:-/home/user/openmitrastar-build/busybox-lyoko-pkgbox}
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
jobs=${TOPAZ_JOBS:-12}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
out="$root/outputs/packages/lyoko-pkgbox"
binary="$build_tree/busybox"

case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
[ "$jobs" -gt 0 ]
test -f "$source_tree/Makefile"
test -f "$source_tree/.config"
test -x "$kernel_src/scripts/config"
test -x "${tc}objdump"
case "$out" in "$root"/*) ;; *) exit 3 ;; esac

required_applets='ar tar gzip gunzip sha256sum sha512sum awk sed grep cut head wc dd mkdir rm cp mv chmod'
forbidden_applets='flash_eraseall flashcp nanddump nandwrite mtd_debug mount umount wget tftp telnet telnetd reboot poweroff'

validate()
{
	test -x "$binary" || return 1
	test -f "$build_tree/include/applet_tables.h" || return 1
	grep -qx 'CONFIG_STATIC=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_BUSYBOX=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_AR=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_TAR=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_GZIP=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_GUNZIP=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_SHA256SUM=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_SHA512SUM=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_WC=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_DD=y' "$build_tree/.config" || return 1
	for applet in $required_applets; do
		grep -Fq "\"$applet\" \"\\0\"" "$build_tree/include/applet_tables.h" || return 1
	done
	for applet in $forbidden_applets; do
		if grep -Fq "\"$applet\" \"\\0\"" "$build_tree/include/applet_tables.h"; then return 1; fi
	done
	if "${tc}objdump" -d "$binary" | grep -Eq '\b(llock|scond)\b'; then return 1; fi
	"${tc}readelf" -h "$binary" | grep -q 'ARC700, v4 ABI'
}

if ! validate; then
	if [ ! -d "$build_tree" ]; then cp -a "$source_tree" "$build_tree"; fi
	make -s -C "$build_tree" mrproper
	cp "$source_tree/.config" "$build_tree/.config"
	cfg="$kernel_src/scripts/config --file $build_tree/.config"
	$cfg --enable STATIC --enable STATIC_LIBGCC --enable BUSYBOX \
		--enable AR --enable FEATURE_AR_LONG_FILENAMES \
		--disable FEATURE_AR_CREATE \
		--enable TAR --enable GZIP --enable GUNZIP --enable SHA256SUM --enable SHA512SUM \
		--enable FEATURE_MD5_SHA1_SUM_CHECK \
		--enable AWK --enable SED --enable GREP --enable CUT --enable HEAD --enable WC --enable DD \
		--enable MKDIR --enable RM --enable CP --enable MV --enable CHMOD \
		--disable FLASH_ERASEALL --disable FLASHCP --disable NANDDUMP \
		--disable NANDWRITE --disable MOUNT --disable UMOUNT \
		--disable WGET --disable TFTP --disable TELNET --disable TELNETD \
		--disable REBOOT --disable POWEROFF
	yes '' | make -s -C "$build_tree" oldconfig >/dev/null
	make -C "$build_tree" -j"$jobs" busybox
	validate
fi

mkdir -p "$out"
cp "$binary" "$out/lyoko-pkgbox"
cp "$build_tree/.config" "$out/busybox.config"
cp "$build_tree/include/applet_tables.h" "$out/applet_tables.h"
chmod 0755 "$out/lyoko-pkgbox"
sha256sum "$out/lyoko-pkgbox" "$out/busybox.config" "$out/applet_tables.h" >"$out/SHA256SUMS"
cat >"$out/manifest.json" <<EOF
{
  "schema": "lyoko.pkgbox/v1",
  "classification": "OFFLINE_RUNTIME_TOOL_NOT_INSTALLED",
  "architecture": "arc700_uclibc_lyoko_v1",
  "artifact": "lyoko-pkgbox",
  "bytes": $(wc -c <"$out/lyoko-pkgbox"),
  "sha256": "$(sha256sum "$out/lyoko-pkgbox" | cut -d' ' -f1)",
  "required_applets": ["ar", "tar", "gzip", "gunzip", "sha256sum", "sha512sum", "awk", "sed", "grep", "cut", "head", "wc", "dd", "mkdir", "rm", "cp", "mv", "chmod"],
  "multicall_invocation": true,
  "network_fetch": false,
  "flash_tools": false,
  "dynamic_install_enabled": false,
  "hardware_actions": {"router": false, "uart": false, "mtd": false}
}
EOF
printf 'LYOKO_PKGBOX_BUILD_PASS sha256='
sha256sum "$out/lyoko-pkgbox" | cut -d' ' -f1
