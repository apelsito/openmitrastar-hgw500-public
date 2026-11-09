#!/bin/sh
set -eu

artifact=${1:-}
kernel_out=${TOPAZ_KERNEL_OUT:-/home/user/openmitrastar-build/radiohw-probe}
expected_release=${QTN_EXPECTED_RELEASE:-5.10.260-openmitrastar-radiohw}

test -n "$artifact"
test -d "$artifact"
test -f "$artifact/SHA256SUMS"
test -f "$artifact/module-manifest.tsv"
test -f "$artifact/actual-modules.txt"
test -f "$artifact/expected-modules.txt"
test -f "$artifact/kernelrelease.txt"
test -f "$artifact/kernel-Module.symvers"
test -f "$kernel_out/Module.symvers"

release=$(cat "$artifact/kernelrelease.txt")
test "$release" = "$expected_release"

(cd "$artifact" && sha256sum -c SHA256SUMS)
cmp "$artifact/expected-modules.txt" "$artifact/actual-modules.txt"
module_count=$(wc -l < "$artifact/actual-modules.txt")
case "$module_count" in
	22|25) ;;
	*) echo "unsupported Quantenna module count: $module_count" >&2; exit 3 ;;
esac
test "$(wc -l < "$artifact/module-manifest.tsv")" -eq $((module_count + 1))
test ! -s "$artifact/depmod-unresolved.log"
cmp "$kernel_out/Module.symvers" "$artifact/kernel-Module.symvers"
if grep -Eq '(^|[[:space:]])(ERROR: modpost|error:|fatal error:)' \
	"$artifact/build.log"; then
	echo "fatal diagnostic found in build.log" >&2
	exit 4
fi

if [ "$module_count" -eq 25 ]; then
	grep -qx 'platform/ruby/emac_lib.ko' "$artifact/actual-modules.txt"
	grep -qx 'platform/topaz/dpi.ko' "$artifact/actual-modules.txt"
	grep -qx 'platform/topaz/switch_emac.ko' "$artifact/actual-modules.txt"
	test -f "$artifact/switch-emac-port.env"
	grep -qx 'BOARD_PHY0=1' "$artifact/switch-emac-port.env"
	grep -qx 'BOARD_PHY1=3' "$artifact/switch-emac-port.env"
	grep -qx 'BOARD_RGMII_TIMING=0x81828282' \
		"$artifact/switch-emac-port.env"
	grep -qx 'MAC_SOURCE=dt-local-mac-address-fail-closed' \
		"$artifact/switch-emac-port.env"
	grep -qx 'PHYLIB_MODE=disabled-no-phy-profile' \
		"$artifact/switch-emac-port.env"
	grep -qx 'DESCRIPTOR_MODE=real-dmautil-dram-lab-fallback-required' \
		"$artifact/switch-emac-port.env"
else
	! grep -qE 'emac_lib\.ko|/dpi\.ko|switch_emac\.ko' \
		"$artifact/actual-modules.txt"
fi

tab=$(printf '\t')
while IFS="$tab" read -r rel hash size vermagic depends; do
	test "$rel" != module || continue
	module="$artifact/rootfs/lib/modules/$release/extra/quantenna/$rel"
	test -f "$module"
	test "$(wc -c < "$module")" -eq "$size"
	test "$(sha256sum "$module" | cut -d' ' -f1)" = "$hash"
	test "$(/usr/sbin/modinfo -F vermagic "$module")" = "$vermagic"
done < "$artifact/module-manifest.tsv"

test "$(find "$artifact/rootfs/lib/modules/$release/extra/quantenna" \
	-type f -name '*.ko' | wc -l)" -eq "$module_count"
if [ "$module_count" -eq 25 ]; then
	grep -Fq 'extra/quantenna/platform/topaz/switch_emac.ko:' \
		"$artifact/rootfs/lib/modules/$release/modules.dep"
	emac_lib_hash=$(awk -F '\t' '$1 == "platform/ruby/emac_lib.ko" {print $2}' \
		"$artifact/module-manifest.tsv")
	dpi_hash=$(awk -F '\t' '$1 == "platform/topaz/dpi.ko" {print $2}' \
		"$artifact/module-manifest.tsv")
	switch_emac_hash=$(awk -F '\t' '$1 == "platform/topaz/switch_emac.ko" {print $2}' \
		"$artifact/module-manifest.tsv")
	grep -qx "EMAC_LIB_SHA256=$emac_lib_hash" "$artifact/switch-emac-port.env"
	grep -qx "DPI_SHA256=$dpi_hash" "$artifact/switch-emac-port.env"
	grep -qx "SWITCH_EMAC_SHA256=$switch_emac_hash" \
		"$artifact/switch-emac-port.env"
fi

printf 'QUANTENNA_LINUX510_ARTIFACT_VERIFY_PASS release=%s modules=%s\n' \
	"$release" "$module_count"
