#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
base=/home/user/openmitrastar-build/realtek-rtl8192ee
out=/home/user/openmitrastar-build/radio-integration-qemu
rootfs=/home/user/openmitrastar-build/radio-integration-rootfs
cpio=/home/user/openmitrastar-build/radio-integration-initramfs.cpio
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
artifacts="$root/outputs/kernel-port/radio-integration-qemu"
builder="$root/work/ssh-emulation/build-radio-integration-rootfs.sh"
dropbear_builder="$root/tools/build_dropbear_radio_multiuser.sh"
dropbear_artifacts="$root/outputs/kernel-port/dropbear-radio-multiuser"
release=5.10.260-openmitrastar-radio
incremental=${RADIO_QEMU_INCREMENTAL:-0}
case "$incremental" in 0|1) ;; *) exit 3 ;; esac

for required in "$src/Makefile" "$base/.config" "$base/System.map" \
	"$builder" "$dropbear_builder"; do
	test -f "$required" || { echo "missing QEMU build input: $required" >&2; exit 2; }
done
test -x "${tc}gcc"
grep -qx 'CONFIG_HARDENED_USERCOPY=y' "$base/.config"
case "$out" in /home/user/openmitrastar-build/*) ;; *) exit 3 ;; esac
case "$rootfs" in /home/user/openmitrastar-build/*) ;; *) exit 3 ;; esac
case "$artifacts" in "$root"/outputs/*) ;; *) exit 3 ;; esac

if test "$incremental" = 0; then
	rm -rf -- "$out"
	mkdir -p "$out"
	cp "$base/.config" "$out/.config"
else
	test -f "$out/.config"
fi
rm -rf -- "$rootfs" "$artifacts"
rm -f -- "$cpio"
mkdir -p "$artifacts"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=qemu-radio-gate
export KBUILD_BUILD_VERSION=1

cfg="$src/scripts/config --file $out/.config"
$cfg --set-str LOCALVERSION '-openmitrastar-radio' \
	--enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$cpio" \
	--set-str ARC_BUILTIN_DTB_NAME qemu_arc700_validation \
	--set-val LINUX_LINK_BASE 0x80000000 \
	--set-val LINUX_RAM_BASE 0x80000000 \
	--enable OPENMITRASTAR_QEMU_NO_ZOL \
	--enable OPENMITRASTAR_QEMU_ENABLE_MMU \
	--enable ARC_MMU_V2 --disable ARC_MMU_V3 \
	--enable ARC_PAGE_SIZE_8K \
	--enable NET_CORE \
	--enable VIRTIO_MENU --enable VIRTIO --enable VIRTIO_MMIO \
	--enable VIRTIO_NET \
	--enable BINFMT_SCRIPT --enable UNIX98_PTYS \
	--enable EPOLL --enable SIGNALFD --enable TIMERFD --enable EVENTFD \
	--disable HARDENED_USERCOPY --disable MTD --disable BLOCK

make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
for required in \
	'CONFIG_LOCALVERSION="-openmitrastar-radio"' \
	'CONFIG_MODULES=y' \
	'CONFIG_MODULE_UNLOAD=y' \
	'CONFIG_OPENMITRASTAR_QDRV_COMPAT=y' \
	'CONFIG_OPENMITRASTAR_QEMU_NO_ZOL=y' \
	'CONFIG_OPENMITRASTAR_QEMU_ENABLE_MMU=y' \
	'CONFIG_NET_CORE=y' \
	'CONFIG_VIRTIO_MMIO=y' \
	'CONFIG_VIRTIO_NET=y' \
	'CONFIG_PCI=y' \
	'CONFIG_PCIE_QTN_TOPAZ=y'; do
	grep -qx "$required" "$out/.config" || {
		echo "required QEMU Kconfig value missing: $required" >&2
		exit 4
	}
done
grep -qx '# CONFIG_MTD is not set' "$out/.config"
grep -qx '# CONFIG_BLOCK is not set' "$out/.config"
grep -qx '# CONFIG_HARDENED_USERCOPY is not set' "$out/.config"

if ! test -x "$dropbear_artifacts/dropbearmulti"; then
	sh "$dropbear_builder"
fi
(cd "$dropbear_artifacts" && sha256sum -c SHA256SUMS)
if strings "$dropbear_artifacts/dropbearmulti" | \
	grep -q 'Non-multiuser Dropbear requires a non-multiuser kernel'; then
	echo 'cached Dropbear radio artifact is single-user' >&2
	exit 5
fi
sh "$builder" "$rootfs" "$cpio" "$out/.config"
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j4 vmlinux \
	>"$artifacts/build.log" 2>&1

actual_release=$(make -s -C "$src" O="$out" ARCH=arc \
	CROSS_COMPILE="$tc" kernelrelease)
test "$actual_release" = "$release"
"${tc}readelf" -h "$out/vmlinux" | grep -Eq 'Class:.*ELF32'
"${tc}readelf" -h "$out/vmlinux" | grep -Eq 'Machine:.*(ARC|ARCompact)'

base_name=linux-5.10.260-openmitrastar-radio-integration-QEMU-ONLY
cp "$out/.config" "$artifacts/$base_name.config"
cp "$out/vmlinux" "$artifacts/$base_name.vmlinux"
cp "$cpio" "$artifacts/$base_name.initramfs.cpio"
printf '%s\n' "$release" >"$artifacts/kernelrelease.txt"
(cd "$rootfs" && tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
	--owner=0 --group=0 --numeric-owner -cf - .) | gzip -n > \
	"$artifacts/$base_name.rootfs.tar.gz"
(cd "$artifacts" && sha256sum "$base_name.config" \
	"$base_name.vmlinux" "$base_name.initramfs.cpio" \
	"$base_name.rootfs.tar.gz" >SHA256SUMS)

printf 'RADIO_INTEGRATION_QEMU_BUILD_PASS release=%s\n' "$release"
