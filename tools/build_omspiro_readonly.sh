#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out=${TOPAZ_RADIOHW_BUILD:-/home/user/openmitrastar-build/radiohw-probe}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
source_dir="$root/work/linux510-radio-port/omspiro"
build_dir=/home/user/openmitrastar-build/omspiro-readonly
dest="$root/outputs/kernel-port/omspiro-readonly-RAM-ONLY-NO-FLASH"

test -f "$src/Makefile"
test -f "$out/.config"
test -f "$source_dir/omspiro.c"
test -x "${tc}gcc"
release=$(cat "$out/include/config/kernel.release")
test "$release" = "5.10.260-openmitrastar-radiohw"

rm -rf "$build_dir"
mkdir -p "$build_dir" "$dest"
cp "$source_dir/omspiro.c" "$source_dir/Makefile" "$build_dir/"
make -C "$src" O="$out" M="$build_dir" ARCH=arc CROSS_COMPILE="$tc" modules

module="$build_dir/omspiro.ko"
test -s "$module"
"${tc}readelf" -h "$module" | grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
/usr/sbin/modinfo -F vermagic "$module" | grep -Fq "$release"

# The binary may import read-side primitives only. These source gates also
# ensure no user-controlled physical address, write handler, ioctl, or mmap.
grep -Fq 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' "$source_dir/omspiro.c"
grep -Fq '#define OMSPIRO_PHYS_BASE 0x90000000UL' "$source_dir/omspiro.c"
grep -Fq '#define OMSPIRO_SIZE      0x01000000UL' "$source_dir/omspiro.c"
grep -Fq '.mode = 0400' "$source_dir/omspiro.c"
for forbidden in '.write =' '.unlocked_ioctl =' '.compat_ioctl =' '.mmap ='; do
	if grep -Fq "$forbidden" "$source_dir/omspiro.c"; then
		echo "forbidden fops member: $forbidden" >&2
		exit 8
	fi
done
if "${tc}nm" -u "$module" | grep -Eq 'copy_from_user|_copy_from_user|ioremap_prot|remap_pfn_range'; then
	echo "forbidden imported mutation/mapping primitive" >&2
	exit 8
fi

cp "$module" "$dest/omspiro.ko"
sha256sum "$dest/omspiro.ko" > "$dest/SHA256SUMS.txt"
cat > "$dest/manifest.json" <<EOF
{
  "schema": "openmitrastar.omspiro-readonly/v1",
  "classification": "RAM-ONLY-NO-FLASH",
  "candidate_eligible": false,
  "kernel_release": "$release",
  "compatible": "mitrastar,hgw-500bna-qcv2",
  "physical_base": "0x90000000",
  "size": 16777216,
  "device": "/dev/omspiro",
  "mode": "0400",
  "sha256": "$(sha256sum "$dest/omspiro.ko" | awk '{print $1}')"
}
EOF
echo "OMSPIRO_BUILD_PASS module=$dest/omspiro.ko sha256=$(sha256sum "$dest/omspiro.ko" | awk '{print $1}')"
