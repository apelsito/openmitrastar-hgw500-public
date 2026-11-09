#!/bin/sh
set -eu

profile=${1:-stage0}
head_wdt=${TOPAZ_HEAD_WDT:-1}
boot_trace=${TOPAZ_BOOT_TRACE:-0}
mmu_entry_probe=${TOPAZ_MMU_ENTRY_PROBE:-0}
pack_flash_artifacts=${TOPAZ_PACK_FLASH_ARTIFACTS:-0}
incremental=${TOPAZ_INCREMENTAL:-0}
case "$profile" in
	stage0|recovery|engineering|release|ramssh) ;;
	*) echo "usage: $0 {stage0|recovery|engineering|release|ramssh}" >&2; exit 2 ;;
esac
if [ "$profile" = ramssh ] && [ "$pack_flash_artifacts" = 1 ]; then
	echo "ramssh is RAM-only; flash artifact packaging is forbidden" >&2
	exit 2
fi
case "$pack_flash_artifacts" in
	0|1) ;;
	*) echo "TOPAZ_PACK_FLASH_ARTIFACTS must be 0 or 1" >&2; exit 2 ;;
esac
case "$incremental" in
	0|1) ;;
	*) echo "TOPAZ_INCREMENTAL must be 0 or 1" >&2; exit 2 ;;
esac
case "$boot_trace" in
	0|1) ;;
	*) echo "TOPAZ_BOOT_TRACE must be 0 or 1" >&2; exit 2 ;;
esac
case "$mmu_entry_probe" in
	0|1) ;;
	*) echo "TOPAZ_MMU_ENTRY_PROBE must be 0 or 1" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out_root=${TOPAZ_BUILD_ROOT:-/home/user/openmitrastar-build}
out="$out_root/$profile"
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
overlay="$root/work/kernel-port/linux-5.10"
configs="$root/work/kernel-port/configs"
artifacts="$root/outputs/kernel-port"
webformat_template="$root/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"

test -f "$src/Makefile"
test -x "${tc}gcc"
case "$out" in "$out_root"/*) ;; *) exit 3 ;; esac
if [ "$incremental" = 0 ]; then
	rm -rf -- "$out"
fi
mkdir -p "$out" "$artifacts"

# Pin every timestamp and identity that enters the kernel/uImage artifacts.
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_VERSION=1

# Apply the reviewable out-of-tree port overlay to the disposable WSL tree.
sh "$root/tools/apply_topaz_linux_510_overlay.sh" "$src"

if [ "$profile" = stage0 ] || [ "$profile" = recovery ] || \
   [ "$profile" = engineering ] || [ "$profile" = ramssh ]; then
	init_root="$out_root/$profile-initramfs-root"
	init_cpio="$out_root/$profile-initramfs.cpio"
	case "$init_root" in "$out_root"/*) ;; *) exit 3 ;; esac
	rm -rf -- "$init_root"
	mkdir -p "$init_root/dev" "$init_root/proc" "$init_root/sys"
	if [ "$profile" = ramssh ]; then
		ramssh_builder=${RAMSSH_ROOTFS_BUILDER:-$root/work/ssh-emulation/build-ramssh-rootfs.sh}
		SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
		sh "$ramssh_builder" \
			"$init_root" "$init_cpio"
	else
		init_source=stage0_init.c
		[ "$profile" = recovery ] && init_source=recovery_init.c
		[ "$profile" = engineering ] && init_source=storage_probe_init.c
		"${tc}gcc" -static -Os -s -Wall -Wextra \
			-o "$init_root/init" "$root/work/kernel-port/initramfs/$init_source"
		find "$init_root" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
		(cd "$init_root" && find . -print0 | sort -z | \
			cpio --reproducible --null -o --format=newc > "$init_cpio")
	fi

fi

if [ "$profile" = stage0 ] || [ "$profile" = recovery ]; then
	make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" tinyconfig
	cfg="$src/scripts/config --file $out/.config"
	$cfg --enable EXPERT --enable EMBEDDED --enable PRINTK --enable BINFMT_ELF \
		--enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$init_cpio" \
		--enable ISA_ARCOMPACT --disable ISA_ARCV2 --enable ARC_CPU_750D \
		--disable ARC_CPU_770 --disable ARC_CPU_HS --enable ARC_MMU_V2 \
		--disable ARC_MMU_V3 --disable ARC_MMU_V4 --enable ARC_PAGE_SIZE_8K \
		--set-val LINUX_LINK_BASE 0x8493a000 --set-val LINUX_RAM_BASE 0x8493a000 \
		--set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_stage0 \
		--enable QTN_TOPAZ_IRQCHIP --disable SMP --enable PREEMPT_NONE \
		--disable PREEMPT --disable PREEMPT_VOLUNTARY --set-val HZ 100 \
		--enable TTY --enable SERIAL_8250 --enable SERIAL_8250_CONSOLE \
		--set-val SERIAL_8250_NR_UARTS 1 --set-val SERIAL_8250_RUNTIME_UARTS 1 \
		--enable SERIAL_8250_DW --enable SERIAL_OF_PLATFORM \
		--enable DEVTMPFS --enable DEVTMPFS_MOUNT --enable PROC_FS \
		--enable SYSFS --enable CC_OPTIMIZE_FOR_SIZE --disable MODULES \
		--enable QTN_TOPAZ_EARLY_WDT_CANARY \
		--disable NET --disable BLOCK
	if [ "$head_wdt" = 1 ]; then
		$cfg --enable QTN_TOPAZ_HEAD_WDT_CANARY
	else
		$cfg --disable QTN_TOPAZ_HEAD_WDT_CANARY
	fi
	if [ "$profile" = recovery ]; then
		$cfg --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_recovery \
			--enable BLOCK --enable MTD --enable MTD_OF_PARTS \
			--enable MTD_CHAR --enable MTD_ROM --enable MTD_PHYSMAP \
			--enable MTD_PHYSMAP_OF --enable NEW_LEDS --enable LEDS_CLASS \
			--enable QTN_TOPAZ_RECOVERY
	fi
else
	if [ "$profile" = ramssh ]; then
		(cd "$src" && ARCH=arc CROSS_COMPILE="$tc" scripts/kconfig/merge_config.sh \
			-n -r -O "$out" "$configs/topaz-common.fragment" \
			"$configs/topaz-network.fragment" \
			"$configs/topaz-ramssh.fragment")
	else
		(cd "$src" && ARCH=arc CROSS_COMPILE="$tc" scripts/kconfig/merge_config.sh \
			-n -r -O "$out" "$configs/topaz-common.fragment" \
			"$configs/topaz-storage.fragment" "$configs/topaz-network.fragment" \
			"$configs/topaz-$profile.fragment")
	fi
	if [ "$profile" = engineering ] || [ "$profile" = ramssh ]; then
		cfg="$src/scripts/config --file $out/.config"
		$cfg --enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$init_cpio"
	fi
fi

# Diagnostic head canaries are a profile-independent build choice.  Applying
# this only to stage0/recovery left ramssh carrying intentional halt paths even
# when TOPAZ_HEAD_WDT=0 was requested.
cfg="$src/scripts/config --file $out/.config"
if [ "$head_wdt" = 1 ]; then
	$cfg --enable QTN_TOPAZ_HEAD_WDT_CANARY
else
	$cfg --disable QTN_TOPAZ_HEAD_WDT_CANARY
fi
if [ "$boot_trace" = 1 ]; then
	$cfg --enable OPENMITRASTAR_BOOT_TRACE
else
	$cfg --disable OPENMITRASTAR_BOOT_TRACE
fi
if [ "$mmu_entry_probe" = 1 ]; then
	$cfg --enable OPENMITRASTAR_MMU_ENTRY_PROBE
else
	$cfg --disable OPENMITRASTAR_MMU_ENTRY_PROBE
fi

make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j4 uImage.bin

if [ "$profile" = ramssh ]; then
	base="linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO"
else
	base="linux-5.10.260-topaz-$profile-NO-GO"
fi
cp "$out/.config" "$artifacts/$base.config"
cp "$out/vmlinux" "$artifacts/$base.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$artifacts/$base.uImage"
if [ "$profile" = ramssh ]; then
	cp "$init_cpio" "$artifacts/$base.initramfs.cpio"
	cp /home/user/openmitrastar-ramssh-keys/client_ed25519.pub \
		"$artifacts/$base.client_ed25519.pub"
fi

if { [ "$profile" = stage0 ] || [ "$profile" = recovery ]; } &&
   [ "$pack_flash_artifacts" = 1 ]; then
	python3 "$root/tools/repack_uimage_oem_arc.py" \
		"$artifacts/$base.uImage" "$artifacts/$base-oem-arc19.uImage"
	python3 "$root/tools/pack_topaz_webformat.py" \
		"$artifacts/$base.uImage" "$webformat_template" \
		"$artifacts/$base-webformat.bin"
fi

if { [ "$profile" = stage0 ] || [ "$profile" = recovery ]; } &&
   [ "$pack_flash_artifacts" = 1 ]; then
	sha256sum "$artifacts/$base.config" "$artifacts/$base.vmlinux" \
		"$artifacts/$base.uImage" "$artifacts/$base-oem-arc19.uImage" \
		"$artifacts/$base-webformat.bin" |
		tee "$artifacts/$base.sha256"
elif [ "$profile" = ramssh ]; then
	sha256sum "$artifacts/$base.config" "$artifacts/$base.vmlinux" \
		"$artifacts/$base.uImage" "$artifacts/$base.initramfs.cpio" \
		"$artifacts/$base.client_ed25519.pub" | \
		tee "$artifacts/$base.sha256"
else
	sha256sum "$artifacts/$base.config" "$artifacts/$base.vmlinux" \
		"$artifacts/$base.uImage" | tee "$artifacts/$base.sha256"
fi
