#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out_root=${TOPAZ_BUILD_ROOT:-/home/user/openmitrastar-build}
out="$out_root/realtek-rtl8192ee"
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
configs="$root/work/kernel-port/configs"
artifacts="$root/outputs/kernel-port/realtek-rtl8192ee-linux510"
cache="$root/work/linux510-radio-port/realtek/firmware"
bundle="$artifacts/rootfs"
log="$artifacts/build.log"

firmware_commit=646f159690e2e00fdb829faeed35e23217ac944c
firmware_sha=c6e5beeeb2a716ce417a9ede5974d0876b18ebf0368c195da8a181f6ba6d9b4b
license_sha=a61351665b4f264f6c631364f85b907d8f8f41f8b369533ef4021765f9f3b62e
firmware_url="https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/rtlwifi/rtl8192eefw.bin?id=$firmware_commit"
license_url="https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/LICENCE.rtlwifi_firmware.txt?id=$firmware_commit"

test -f "$src/Makefile"
test -x "${tc}gcc"
case "$out" in "$out_root"/*) ;; *) exit 3 ;; esac
case "$artifacts" in "$root"/outputs/*) ;; *) exit 3 ;; esac

rm -rf -- "$out" "$artifacts"
mkdir -p "$out" "$artifacts" "$cache/rtlwifi"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_VERSION=1

sh "$root/tools/apply_topaz_linux_510_overlay.sh" "$src"

(cd "$src" && ARCH=arc CROSS_COMPILE="$tc" scripts/kconfig/merge_config.sh \
	-n -r -O "$out" "$configs/topaz-common.fragment" \
	"$configs/topaz-network.fragment" "$configs/topaz-realtek.fragment")

make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig

for required in \
	'CONFIG_ARC_PLAT_TOPAZ=y' \
	'CONFIG_OPENMITRASTAR_QDRV_COMPAT=y' \
	'CONFIG_IPV6=y' \
	'CONFIG_NET_SCHED=y' \
	'CONFIG_I2C=y' \
	'CONFIG_GPIOLIB=y' \
	'CONFIG_PCI=y' \
	'CONFIG_PCIE_QTN_TOPAZ=y' \
	'CONFIG_CFG80211=m' \
	'CONFIG_MAC80211=m' \
	'CONFIG_RTLWIFI=m' \
	'CONFIG_RTLWIFI_PCI=m' \
	'CONFIG_RTLBTCOEXIST=m' \
	'CONFIG_RTL8192EE=m'; do
	grep -qx "$required" "$out/.config" || {
		echo "required Kconfig value missing: $required" >&2
		exit 4
	}
done
grep -qx '# CONFIG_PCI_MSI is not set' "$out/.config"
grep -qx 'CONFIG_CFG80211_CERTIFICATION_ONUS=y' "$out/.config"
grep -qx '# CONFIG_CFG80211_REQUIRE_SIGNED_REGDB is not set' "$out/.config"

if ! make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j4 \
	uImage.bin modules >"$log" 2>&1; then
	tail -n 200 "$log" >&2
	exit 6
fi

release=$(make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	kernelrelease)
stage="$out/modules-stage"
mkdir -p "$stage"
if ! make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	INSTALL_MOD_PATH="$stage" DEPMOD=/bin/true modules_install \
	>>"$log" 2>&1; then
	tail -n 200 "$log" >&2
	exit 7
fi

fetch_verified()
{
	url=$1
	destination=$2
	expected=$3
	tmp="$destination.tmp"
	rm -f -- "$tmp"
	curl -fL --retry 3 --connect-timeout 15 "$url" -o "$tmp"
	echo "$expected  $tmp" | sha256sum -c -
	mv -f -- "$tmp" "$destination"
}

firmware="$cache/rtlwifi/rtl8192eefw.bin"
license="$cache/LICENCE.rtlwifi_firmware.txt"
if ! echo "$firmware_sha  $firmware" | sha256sum -c - >/dev/null 2>&1; then
	fetch_verified "$firmware_url" "$firmware" "$firmware_sha"
fi
if ! echo "$license_sha  $license" | sha256sum -c - >/dev/null 2>&1; then
	fetch_verified "$license_url" "$license" "$license_sha"
fi

mkdir -p "$bundle/lib/modules" "$bundle/lib/firmware/rtlwifi" \
	"$bundle/usr/share/licenses/rtl8192ee"
cp -a "$stage/lib/modules/$release" "$bundle/lib/modules/"
cp "$firmware" "$bundle/lib/firmware/rtlwifi/rtl8192eefw.bin"
cp "$license" \
	"$bundle/usr/share/licenses/rtl8192ee/LICENCE.rtlwifi_firmware.txt"

rtl="$bundle/lib/modules/$release/kernel/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/rtl8192ee.ko"
test -f "$rtl"
"${tc}readelf" -h "$rtl" | grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
/usr/sbin/modinfo -F alias "$rtl" | grep -Eqi 'pci:.*v000010ECd0000818B'
test "$(/usr/sbin/modinfo -F firmware "$rtl")" = 'rtlwifi/rtl8192eefw.bin'
/usr/sbin/modinfo -F vermagic "$rtl" | grep -Fq "$release"

/usr/sbin/depmod -b "$bundle" "$release"
grep -Fq 'rtl8192ee.ko:' "$bundle/lib/modules/$release/modules.dep"
for module in cfg80211.ko mac80211.ko rtlwifi.ko rtl_pci.ko \
	btcoexist.ko rtl8192ee.ko; do
	find "$bundle/lib/modules/$release" -type f -name "$module" | grep -q . || {
		echo "dependency module missing: $module" >&2
		exit 5
	}
done

cp "$out/.config" "$artifacts/linux-5.10.260-topaz-radio.config"
cp "$out/vmlinux" "$artifacts/linux-5.10.260-topaz-radio.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" \
	"$artifacts/linux-5.10.260-topaz-radio-NO-FLASH.uImage"
printf '%s\n' "$release" > "$artifacts/kernelrelease.txt"
printf '%s\n' "$firmware_commit" > "$artifacts/linux-firmware-commit.txt"

(cd "$bundle" && find . -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +)
(cd "$bundle" && tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
	--owner=0 --group=0 --numeric-owner -cf - .) | gzip -n > \
	"$artifacts/rtl8192ee-rootfs-overlay.tar.gz"

(cd "$artifacts" && sha256sum \
	linux-5.10.260-topaz-radio.config \
	linux-5.10.260-topaz-radio.vmlinux \
	linux-5.10.260-topaz-radio-NO-FLASH.uImage \
	rtl8192ee-rootfs-overlay.tar.gz \
	rootfs/lib/firmware/rtlwifi/rtl8192eefw.bin \
	rootfs/usr/share/licenses/rtl8192ee/LICENCE.rtlwifi_firmware.txt > \
	SHA256SUMS)

printf 'REALTEK_RTL8192EE_LINUX510_BUILD_PASS release=%s\n' "$release"
