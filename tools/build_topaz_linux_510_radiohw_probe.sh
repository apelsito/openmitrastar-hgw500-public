#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out_root=${TOPAZ_BUILD_ROOT:-/home/user/openmitrastar-build}
base="$out_root/ramssh"
out="$out_root/radiohw-probe"
init_cpio="$out_root/ramssh-initramfs.cpio"
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
fragment="$root/work/kernel-port/configs/topaz-realtek.fragment"
artifacts=${RADIOHW_ARTIFACTS:-$root/outputs/kernel-port/radiohw-probe}
template="$root/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
tftp=${RADIOHW_TFTP:-$root/work/tftp/omvl/linux510-radiohw-pci-probe-webformat.bin}
incremental=${RADIOHW_INCREMENTAL:-1}
case "$incremental" in 0|1) ;; *) exit 3 ;; esac

for required in "$src/Makefile" "$base/.config" "$init_cpio" \
	"$fragment" "$template"; do
	test -f "$required" || { echo "missing input: $required" >&2; exit 2; }
done
test -x "${tc}gcc"
case "$out" in "$out_root"/*) ;; *) exit 3 ;; esac
case "$artifacts" in "$root"/outputs/kernel-port/*) ;; *) exit 3 ;; esac
case "$tftp" in "$root"/work/tftp/omvl/*) ;; *) exit 3 ;; esac

if [ "$incremental" = 0 ] || [ ! -f "$out/.config" ]; then
	rm -rf -- "$out"
	mkdir -p "$out"
	cp "$base/.config" "$out/base.config"
else
	test -f "$out/base.config"
fi
mkdir -p "$artifacts"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=radiohw-probe
export KBUILD_BUILD_VERSION=1

sh "$root/tools/apply_topaz_linux_510_overlay.sh" "$src"
if [ "$incremental" = 0 ] || [ ! -f "$out/.config" ]; then
	(
		cd "$src"
		ARCH=arc CROSS_COMPILE="$tc" scripts/kconfig/merge_config.sh \
			-n -r -O "$out" "$out/base.config" "$fragment"
	)
fi
cfg="$src/scripts/config --file $out/.config"
$cfg --set-str LOCALVERSION '-openmitrastar-radiohw' \
	--enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$init_cpio" \
	--set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_ramssh \
	--disable QTN_TOPAZ_HEAD_WDT_CANARY \
	--disable OPENMITRASTAR_BOOT_TRACE \
	--disable OPENMITRASTAR_MMU_ENTRY_PROBE
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig

for required in \
	'CONFIG_PCI=y' \
	'CONFIG_PCIE_QTN_TOPAZ=y' \
	'CONFIG_OPENMITRASTAR_QDRV_COMPAT=y' \
	'CONFIG_MODULES=y' \
	'CONFIG_MODULE_UNLOAD=y' \
	'CONFIG_CFG80211=m' \
	'CONFIG_MAC80211=m' \
	'CONFIG_RTL8192EE=m'; do
	grep -qx "$required" "$out/.config" || {
		echo "missing config: $required" >&2
		exit 4
	}
done

jobs=${TOPAZ_JOBS:-12}
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	-j"$jobs" uImage.bin

base_name=linux-5.10.260-openmitrastar-radiohw-pci-probe-RAM-ONLY
cp "$out/.config" "$artifacts/$base_name.config"
cp "$out/vmlinux" "$artifacts/$base_name.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$artifacts/$base_name.uImage"
python3 "$root/tools/pack_topaz_webformat.py" \
	"$artifacts/$base_name.uImage" "$template" "$tftp"
sha256sum "$artifacts/$base_name.config" "$artifacts/$base_name.vmlinux" \
	"$artifacts/$base_name.uImage" "$tftp" >"$artifacts/SHA256SUMS"
printf 'RADIOHW_PCI_PROBE_BUILD_PASS image=%s bytes=%s\n' \
	"$tftp" "$(wc -c <"$tftp")"
