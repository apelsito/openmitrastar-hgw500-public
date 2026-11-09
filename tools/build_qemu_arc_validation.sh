#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out=${QEMU_ARC_BUILD_ROOT:-/home/user/openmitrastar-build/qemu-arc-validation}
qemu=${QEMU_ARC_BIN:-/home/user/qemu-arc-build2/qemu-system-arc}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
artifacts="$root/outputs/kernel-port"
overlay="$root/work/kernel-port/linux-5.10"
init_root="${out}-initramfs-root"
init_cpio="${out}-initramfs.cpio"

test -f "$src/Makefile"
test -x "${tc}gcc"
test -x "$qemu"
case "$out" in /home/user/openmitrastar-build/*) ;; *) exit 3 ;; esac
rm -rf -- "$out" "$init_root"
mkdir -p "$out" "$init_root/dev" "$init_root/proc" "$init_root/sys" "$artifacts"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=qemu-validator
export KBUILD_BUILD_VERSION=1

cp "$overlay/arch/arc/boot/dts/qemu_arc700_validation.dts" \
	"$src/arch/arc/boot/dts/"
"${tc}gcc" -static -Os -s -Wall -Wextra \
	-o "$init_root/init" \
	"$root/work/kernel-port/initramfs/qemu_validation_init.c"
find "$init_root" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
(cd "$init_root" && find . -print0 | sort -z | \
	cpio --reproducible --null -o --format=newc > "$init_cpio")

make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" tinyconfig
cfg="$src/scripts/config --file $out/.config"
$cfg --enable EXPERT --enable EMBEDDED --enable PRINTK --enable BINFMT_ELF \
	--enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$init_cpio" \
	--enable ISA_ARCOMPACT --disable ISA_ARCV2 --disable ARC_CPU_750D \
	--enable ARC_CPU_770 --enable ARC_MMU_V3 --disable ARC_MMU_V2 \
	--enable ARC_PAGE_SIZE_8K --set-val LINUX_LINK_BASE 0x80000000 \
	--set-val LINUX_RAM_BASE 0x80000000 \
	--set-str ARC_BUILTIN_DTB_NAME qemu_arc700_validation \
	--disable SMP --enable PREEMPT_NONE --disable PREEMPT \
	--disable PREEMPT_VOLUNTARY --set-val HZ 100 \
	--enable TTY --enable SERIAL_8250 --enable SERIAL_8250_CONSOLE \
	--set-val SERIAL_8250_NR_UARTS 1 --set-val SERIAL_8250_RUNTIME_UARTS 1 \
	--enable SERIAL_OF_PLATFORM --enable DEVTMPFS --enable DEVTMPFS_MOUNT \
	--enable PROC_FS --enable SYSFS --enable CC_OPTIMIZE_FOR_SIZE \
	--disable MODULES --disable NET --disable BLOCK

make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j4 vmlinux

base=linux-5.10.260-qemu-arc700-validation
cp "$out/.config" "$artifacts/$base.config"
cp "$out/vmlinux" "$artifacts/$base.vmlinux"
sha256sum "$artifacts/$base.config" "$artifacts/$base.vmlinux" | \
	tee "$artifacts/$base.sha256"

log="$artifacts/$base.serial.log"
set +e
timeout 20s "$qemu" -M arc-sim -cpu arc700 -m 3G -display none \
	-monitor none -no-reboot -serial stdio -kernel "$out/vmlinux" \
	>"$log" 2>&1
qemu_status=$?
set -e
printf 'QEMU_STATUS=%s\n' "$qemu_status" >>"$log"
grep -q 'OpenMitraStar QEMU validation twin is alive' "$log"
printf 'QEMU validation marker reached (timeout status %s expected after PID 1 pause).\n' \
	"$qemu_status"
