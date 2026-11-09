#!/bin/sh
set -eu

# Offline-only builder for the narrow ARC700 toolbox consumed by the volatile
# L2 bridge stage.  It performs no network fetch and produces no flash image.

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=${L2_BUSYBOX_SOURCE:-/home/user/openmitrastar-ssh-lab/busybox-1.38.0}
build_tree=${L2_BUSYBOX_BUILD:-/home/user/openmitrastar-build/busybox-l2-tools-src}
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
jobs=${TOPAZ_JOBS:-12}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
out="$root/outputs/kernel-port/l2-bridge-stage"
binary="$build_tree/busybox"

case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
[ "$jobs" -gt 0 ]
test -f "$source_tree/Makefile"
test -f "$source_tree/.config"
test -x "$kernel_src/scripts/config"
test -x "${tc}objdump"
case "$out" in "$root"/*) ;; *) exit 3 ;; esac

required_applets='brctl ifconfig route udhcpc sha256sum grep ls cat echo chmod sleep id uname mkdir pidof'
forbidden_applets='flash_eraseall flashcp nanddump nandwrite mtd_debug mount umount wget tftp telnet telnetd'

validate()
{
	test -x "$binary" || return 1
	test -f "$build_tree/include/applet_tables.h" || return 1
	grep -qx 'CONFIG_STATIC=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_BRCTL=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_FEATURE_BRCTL_FANCY=y' "$build_tree/.config" || return 1
	grep -qx 'CONFIG_UDHCPC=y' "$build_tree/.config" || return 1
	for applet in $required_applets; do
		grep -Fq "\"$applet\" \"\\0\"" \
			"$build_tree/include/applet_tables.h" || return 1
	done
	for applet in $forbidden_applets; do
		if grep -Fq "\"$applet\" \"\\0\"" \
			"$build_tree/include/applet_tables.h"; then return 1; fi
	done
	if "${tc}objdump" -d "$binary" | grep -Eq '\b(llock|scond)\b'; then
		return 1
	fi
	"${tc}readelf" -h "$binary" | grep -q 'ARC700, v4 ABI'
}

if ! validate; then
	if [ ! -d "$build_tree" ]; then cp -a "$source_tree" "$build_tree"; fi
	make -s -C "$build_tree" mrproper
	cp "$source_tree/.config" "$build_tree/.config"
	cfg="$kernel_src/scripts/config --file $build_tree/.config"
	$cfg --enable STATIC --enable STATIC_LIBGCC \
		--enable BRCTL --enable FEATURE_BRCTL_FANCY --enable FEATURE_BRCTL_SHOW \
		--enable IFCONFIG --enable FEATURE_IFCONFIG_STATUS --enable FEATURE_IFCONFIG_HW \
		--enable ROUTE --enable UDHCPC --enable SHA256SUM --enable GREP \
		--enable LS --enable CAT --enable ECHO --enable CHMOD --enable SLEEP \
		--enable ID --enable UNAME --enable MKDIR --enable PIDOF \
		--disable FLASH_ERASEALL --disable FLASHCP --disable NANDDUMP \
		--disable NANDWRITE --disable MOUNT --disable UMOUNT --disable WGET \
		--disable TFTP --disable TELNET --disable TELNETD
	yes '' | make -s -C "$build_tree" oldconfig >/dev/null
	make -C "$build_tree" -j"$jobs" busybox
	validate
fi

mkdir -p "$out"
cp "$binary" "$out/ram_l2_tools"
cp "$build_tree/.config" "$out/busybox.config"
chmod 0755 "$out/ram_l2_tools"
sha256sum "$out/ram_l2_tools" "$out/busybox.config" > "$out/SHA256SUMS"
cat > "$out/manifest.json" <<EOF
{
  "schema": "openmitrastar.l2-toolbox/v1",
  "classification": "RAM-ONLY-NO-FLASH",
  "candidate_eligible": false,
  "artifact": "ram_l2_tools",
  "sha256": "$(sha256sum "$out/ram_l2_tools" | cut -d' ' -f1)",
  "config": "busybox.config",
  "config_sha256": "$(sha256sum "$out/busybox.config" | cut -d' ' -f1)",
  "flash_supported": false,
  "persistent_writes_supported": false
}
EOF
printf 'OML2_TOOLBOX_BUILD_PASS sha256='
sha256sum "$out/ram_l2_tools" | cut -d' ' -f1
