#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out_root=${TOPAZ_BUILD_ROOT:-/home/user/openmitrastar-build}
out=${TOPAZ_KERNEL_OUT:-$out_root/realtek-rtl8192ee}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
module_src=${QTN_MODULE_SRC:-$root/work/linux510-radio-port/quantenna}
oem_root=${QTN_OEM_ROOTFS:-$root/outputs/kernel-port/mtd4-analysis/rootfs}
artifacts=${QTN_ARTIFACTS:-$root/outputs/kernel-port/quantenna-linux510}
bundle="$artifacts/rootfs"
log="$artifacts/build.log"
incremental=${QTN_INCREMENTAL:-0}
v89_pair=${OPENMITRASTAR_QDRV_V89_PAIR:-0}
switch_emac_port=${QTN_SWITCH_EMAC_PORT:-0}
jobs=${QTN_JOBS:-12}

case "$incremental" in
	0|1) ;;
	*) echo "QTN_INCREMENTAL must be 0 or 1" >&2; exit 3 ;;
esac
case "$v89_pair" in
	0|1) ;;
	*) echo "OPENMITRASTAR_QDRV_V89_PAIR must be 0 or 1" >&2; exit 3 ;;
esac
case "$switch_emac_port" in
	0|1) ;;
	*) echo "QTN_SWITCH_EMAC_PORT must be 0 or 1" >&2; exit 3 ;;
esac
case "$jobs" in
	''|*[!0-9]*|0) echo "QTN_JOBS must be a positive integer" >&2; exit 3 ;;
esac
if [ "$switch_emac_port" = 1 ] && [ "$v89_pair" != 1 ]; then
	echo "switch_emac profile requires OPENMITRASTAR_QDRV_V89_PAIR=1" >&2
	exit 3
fi

test -f "$src/Makefile"
test -f "$out/.config"
test -f "$out/Module.symvers"
test -x "${tc}gcc"
test -f "$module_src/Makefile"
case "$module_src" in "$root"/work/*) ;; *) exit 3 ;; esac
case "$out" in "$out_root"/*) ;; *) exit 3 ;; esac
case "$artifacts" in "$root"/outputs/*) ;; *) exit 3 ;; esac

release=$(make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	kernelrelease)
expected_release=${QTN_EXPECTED_RELEASE:-5.10.260-openmitrastar-radio}
test "$release" = "$expected_release"
for required in \
	'CONFIG_OPENMITRASTAR_QDRV_COMPAT=y' \
	'CONFIG_MODULE_UNLOAD=y' \
	'CONFIG_IPV6=y' \
	'CONFIG_NET_SCHED=y' \
	'CONFIG_I2C=y' \
	'CONFIG_GPIOLIB=y'; do
	grep -qx "$required" "$out/.config" || {
		echo "required Kconfig value missing: $required" >&2
		exit 4
	}
done

rm -rf -- "$artifacts"
mkdir -p "$artifacts" "$bundle/lib/modules/$release/extra/quantenna" \
	"$bundle/lib/firmware" "$bundle/etc"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_VERSION=1

if [ "$incremental" = 0 ]; then
	if [ "$switch_emac_port" = 0 ]; then
		# Remove optional-profile outputs too; Kbuild only cleans objects that
		# are present in the active obj-m graph.
		make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
			M="$module_src" OPENMITRASTAR_QDRV_V89_PAIR=1 \
			OPENMITRASTAR_SWITCH_EMAC_PORT=1 clean >/dev/null
	fi
	make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
		M="$module_src" OPENMITRASTAR_QDRV_V89_PAIR="$v89_pair" \
		OPENMITRASTAR_SWITCH_EMAC_PORT="$switch_emac_port" clean >/dev/null
fi
if ! make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	M="$module_src" OPENMITRASTAR_QDRV_V89_PAIR="$v89_pair" \
	OPENMITRASTAR_SWITCH_EMAC_PORT="$switch_emac_port" \
	-j"$jobs" modules >"$log" 2>&1; then
	tail -n 200 "$log" >&2
	exit 5
fi
if grep -Eq '(^|[[:space:]])(ERROR: modpost|error:|fatal error:)' "$log"; then
	echo "Quantenna build log contains a fatal diagnostic" >&2
	exit 6
fi

cat >"$artifacts/expected-modules.unsorted" <<'EOF'
platform/fwt/fwt_ctrl.ko
platform/qtsens/temp_sensor.ko
platform/ruby/board_compat.ko
platform/ruby/dmautil.ko
platform/ruby/gpio.ko
platform/ruby/iputil.ko
platform/ruby/qtn_platform_support.ko
platform/ruby/qtn_pm_qos_compat.ko
platform/ruby/runtime_compat.ko
platform/topaz/fwt_if.ko
platform/topaz/hbm.ko
platform/topaz/switch_tqe.ko
platform/topaz/switch_vlan.ko
platform/topaz/temp_sens.ko
platform/topaz/topaz_congest_queue.ko
qdrv/qdrv.ko
wlan/wlan.ko
wlan/wlan_ccmp.ko
wlan/wlan_scan_ap.ko
wlan/wlan_scan_sta.ko
wlan/wlan_tkip.ko
wlan/wlan_xauth.ko
EOF
if [ "$switch_emac_port" = 1 ]; then
	cat >>"$artifacts/expected-modules.unsorted" <<'EOF'
platform/ruby/emac_lib.ko
platform/topaz/dpi.ko
platform/topaz/switch_emac.ko
EOF
	expected_count=25
else
	expected_count=22
fi
sort "$artifacts/expected-modules.unsorted" >"$artifacts/expected-modules.txt"
rm "$artifacts/expected-modules.unsorted"

(cd "$module_src" && find . -type f -name '*.ko' -print | \
	sed 's#^\./##' | sort) >"$artifacts/actual-modules.txt"
diff -u "$artifacts/expected-modules.txt" "$artifacts/actual-modules.txt"
test "$(wc -l < "$artifacts/actual-modules.txt")" -eq "$expected_count"

while IFS= read -r rel; do
	destination="$bundle/lib/modules/$release/extra/quantenna/$rel"
	mkdir -p "$(dirname -- "$destination")"
	cp "$module_src/$rel" "$destination"
done <"$artifacts/actual-modules.txt"

cat >"$artifacts/build-profile.env" <<EOF
KERNEL_RELEASE=$release
MODULE_COUNT=$expected_count
OPENMITRASTAR_QDRV_V89_PAIR=$v89_pair
QTN_SWITCH_EMAC_PORT=$switch_emac_port
QTN_JOBS=$jobs
EOF
expected_vermagic="$release mod_unload ARC700"
printf 'module\tsha256\tsize\tvermagic\tdepends\n' \
	>"$artifacts/module-manifest.tsv"
while IFS= read -r rel; do
	module="$bundle/lib/modules/$release/extra/quantenna/$rel"
	"${tc}readelf" -h "$module" | grep -Eq 'Class:.*ELF32'
	"${tc}readelf" -h "$module" | grep -Eq 'Data:.*little endian'
	"${tc}readelf" -h "$module" | grep -Eq 'Machine:.*(ARC|ARCompact)'
	vermagic=$(/usr/sbin/modinfo -F vermagic "$module")
	test "$vermagic" = "$expected_vermagic" || {
		echo "vermagic mismatch: $rel: $vermagic" >&2
		exit 7
	}
	depends=$(/usr/sbin/modinfo -F depends "$module")
	hash=$(sha256sum "$module" | cut -d' ' -f1)
	size=$(wc -c <"$module")
	printf '%s\t%s\t%s\t%s\t%s\n' "$rel" "$hash" "$size" \
		"$vermagic" "$depends" >>"$artifacts/module-manifest.tsv"
done <"$artifacts/actual-modules.txt"

# modpost/depmod validate unresolved imports but do not reject two already
# linked modules exporting the same name.  The kernel module loader does, so
# detect that condition before an artifact can reach hardware.
printf 'symbol\tmodule\n' >"$artifacts/exported-symbols.tsv"
while IFS= read -r rel; do
	module="$bundle/lib/modules/$release/extra/quantenna/$rel"
	"${tc}readelf" -p __ksymtab_strings "$module" 2>/dev/null | \
		sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | \
		while IFS= read -r symbol; do
			test -n "$symbol" && printf '%s\t%s\n' "$symbol" "$rel"
		done >>"$artifacts/exported-symbols.tsv"
done <"$artifacts/actual-modules.txt"
tail -n +2 "$artifacts/exported-symbols.tsv" | sort -t "$(printf '\t')" \
	-k1,1 -k2,2 >"$artifacts/exported-symbols.sorted"
{
	printf 'symbol\tmodules\n'
	cut -f1 "$artifacts/exported-symbols.sorted" | sort | uniq -d | \
		while IFS= read -r symbol; do
			modules=$(awk -F '\t' -v symbol="$symbol" \
				'$1 == symbol { if (list != "") list = list ","; list = list $2 } END { print list }' \
				"$artifacts/exported-symbols.sorted")
			printf '%s\t%s\n' "$symbol" "$modules"
		done
} >"$artifacts/duplicate-exported-symbols.tsv"
rm "$artifacts/exported-symbols.sorted"
if test "$(wc -l < "$artifacts/duplicate-exported-symbols.tsv")" -ne 1; then
	echo "duplicate exported symbols detected:" >&2
	cat "$artifacts/duplicate-exported-symbols.tsv" >&2
	exit 9
fi

if grep -R -n -E 'dma_(alloc|free)_coherent\(NULL|dma_(map|unmap)_single\(NULL|dma_pool_create\([^,]+,[[:space:]]*NULL' \
	--include='*.c' --include='*.h' "$module_src" \
	>"$artifacts/null-dma-api-calls.txt"; then
	echo "Quantenna port still uses a NULL Linux DMA device" >&2
	cat "$artifacts/null-dma-api-calls.txt" >&2
	exit 11
fi
: >"$artifacts/null-dma-api-calls.txt"

if [ "$switch_emac_port" = 1 ]; then
	emac_lib_hash=$(awk -F '\t' '$1 == "platform/ruby/emac_lib.ko" {print $2}' \
		"$artifacts/module-manifest.tsv")
	dpi_hash=$(awk -F '\t' '$1 == "platform/topaz/dpi.ko" {print $2}' \
		"$artifacts/module-manifest.tsv")
	switch_emac_hash=$(awk -F '\t' '$1 == "platform/topaz/switch_emac.ko" {print $2}' \
		"$artifacts/module-manifest.tsv")
	test -n "$emac_lib_hash"
	test -n "$dpi_hash"
	test -n "$switch_emac_hash"
	switch_emac_depends=$(awk -F '\t' '$1 == "platform/topaz/switch_emac.ko" {print $5}' \
		"$artifacts/module-manifest.tsv")
	case ",$switch_emac_depends," in
		*,fwt_ctrl,*)
			echo "switch_emac must not depend on proprietary fwt_ctrl in the non-bonded port" >&2
			exit 10
			;;
	esac
	for consumer in wlan/wlan.ko qdrv/qdrv.ko; do
		consumer_depends=$(awk -F '\t' -v module="$consumer" '$1 == module {print $5}' \
			"$artifacts/module-manifest.tsv")
		case ",$consumer_depends," in
			*,fwt_ctrl,*)
				echo "$consumer must not import the proprietary fwt_ctrl module" >&2
				exit 12
				;;
		esac
	done
	cat >"$artifacts/switch-emac-port.env" <<EOF
EMAC_LIB_SHA256=$emac_lib_hash
DPI_SHA256=$dpi_hash
SWITCH_EMAC_SHA256=$switch_emac_hash
BOARD_EMAC0_REQUIRED=1
BOARD_EMAC1_REQUIRED=1
BOARD_PHY0=1
BOARD_PHY1=3
BOARD_RGMII_TIMING=0x81828282
MANAGEMENT_EMAC=1
MANAGEMENT_PHY=3
STANDBY_EMAC=0
MAC_SOURCE=dt-local-mac-address-fail-closed
PHYLIB_MODE=disabled-no-phy-profile
EMAC_BONDING=0
FWT_REMAPPER=compiled-out-nonbonded
HBM_IRQ=arc-default-domain-hwirq21
DMA_DEVICE=openmitrastar-qtn-dma-32bit
TRAFFIC_DIAGNOSTICS=first8-tx-rx-hbm-plus-8s-snapshots
RX_ROUTE=explicit-static-tqe-lhost-readback
RX_ALIGNMENT=net-ip-align-2-arc700
DESCRIPTOR_MODE=real-dmautil-dram-lab-fallback-required
RUNTIME_STATUS=offline-build-only
EOF
fi

copy_oem_firmware()
{
	name=$1
	expected=$2
	source="$oem_root/etc/firmware/$name"
	test -f "$source"
	echo "$expected  $source" | sha256sum -c - >/dev/null
	cp "$source" "$bundle/lib/firmware/$name"
}

copy_oem_firmware auc_driver.default.0.bin \
	e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af
copy_oem_firmware auc_driver.nomu.0.bin \
	c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6
copy_oem_firmware qtn_driver.qtn_ruby.0.bin \
	71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4
copy_oem_firmware rdsp_driver.0.bin \
	87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd

regdb="$oem_root/etc/qtn_regulatory_db.bin"
regdb_sha=2263cc2407d6e0d1543aa55bd7d2b9b98598301c59b4d3dca40701132f044365
test -f "$regdb"
echo "$regdb_sha  $regdb" | sha256sum -c - >/dev/null
cp "$regdb" "$bundle/etc/qtn_regulatory_db.bin"
ln -s ../lib/firmware "$bundle/etc/firmware"

(cd "$bundle" && sha256sum lib/firmware/*.bin \
	etc/qtn_regulatory_db.bin) >"$artifacts/oem-firmware-manifest.sha256"
cat >"$artifacts/OEM-FIRMWARE-LOCAL-ONLY.txt" <<'EOF'
These Quantenna firmware files were extracted from the owner's OEM image.
They are immutable, hash-pinned local inputs and are not redistribution assets.
Device-specific calibration and MAC data are intentionally not included here.
EOF

module_dir="$bundle/lib/modules/$release"
sed 's#^#extra/quantenna/#' "$artifacts/actual-modules.txt" \
	>"$module_dir/modules.order"
cp "$out/modules.builtin" "$module_dir/modules.builtin"
cp "$out/modules.builtin.modinfo" "$module_dir/modules.builtin.modinfo"
if ! /usr/sbin/depmod -e -F "$out/System.map" -b "$bundle" "$release" \
	2>"$artifacts/depmod-unresolved.log"; then
	cat "$artifacts/depmod-unresolved.log" >&2
	exit 8
fi
if test -s "$artifacts/depmod-unresolved.log"; then
	cat "$artifacts/depmod-unresolved.log" >&2
	exit 8
fi
grep -Fq 'extra/quantenna/qdrv/qdrv.ko:' \
	"$bundle/lib/modules/$release/modules.dep"
grep -Fq 'extra/quantenna/wlan/wlan.ko:' \
	"$bundle/lib/modules/$release/modules.dep"
if [ "$switch_emac_port" = 1 ]; then
	grep -Fq 'extra/quantenna/platform/topaz/switch_emac.ko:' \
		"$bundle/lib/modules/$release/modules.dep"
fi

cp "$out/Module.symvers" "$artifacts/kernel-Module.symvers"
printf '%s\n' "$release" >"$artifacts/kernelrelease.txt"
(cd "$bundle" && find . -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +)
(cd "$bundle" && tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
	--owner=0 --group=0 --numeric-owner -cf - .) | gzip -n > \
	"$artifacts/quantenna-rootfs-overlay.tar.gz"

checksum_files="module-manifest.tsv exported-symbols.tsv duplicate-exported-symbols.tsv null-dma-api-calls.txt oem-firmware-manifest.sha256 kernel-Module.symvers depmod-unresolved.log quantenna-rootfs-overlay.tar.gz build-profile.env"
if [ "$switch_emac_port" = 1 ]; then
	checksum_files="$checksum_files switch-emac-port.env"
fi
(cd "$artifacts" && sha256sum $checksum_files >SHA256SUMS)

printf 'QUANTENNA_LINUX510_BUILD_PASS release=%s modules=%s switch_emac=%s\n' \
	"$release" "$expected_count" "$switch_emac_port"
