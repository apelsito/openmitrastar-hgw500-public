#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
baseline=${OM_LED5G_BASELINE:-$root/outputs/kernel-port/quantenna-linux510-radiohw-qdrv-sequential-20260819}
artifacts=${OM_LED5G_ARTIFACTS:-$root/outputs/kernel-port/hgw500-controls-5g-postbaseline-20260819}
stage=${OM_LED5G_STAGE:-/home/user/openmitrastar-build/hgw500-controls-5g-postbaseline-20260819}
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
kernel_out=${TOPAZ_KERNEL_OUT:-/home/user/openmitrastar-build/radiohw-probe}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
patch="$root/outputs/kernel-port/hgw500-controls-5g/openmitrastar-wlan5g-led-carrier.patch"
evidence="$root/outputs/kernel-port/hgw500-controls-5g/OEM_WLAN5G_LED_EVIDENCE.md"
release=5.10.260-openmitrastar-radiohw

baseline_qdrv_sha=32956592ad32a6eadf12632e84495acaa18dd668184959c23acee0b8d0e31000
baseline_manifest_sha=2cbafb7ca596db1a35b21191f40df7a2404f5af53647a9424091bf218e9f8ac8
patch_sha=37a2f89e4b1fbda1edd9a751d05b959dd03d43575cc5868229b813e607f09d07
recovery_preimage_sha=244abf7b4ecda1213ac26d12e76bbc3c3409298c5966fa89617d4258a2be3a06
dts_preimage_sha=69718c1f26451abf2dcfe9ead090659f3714e65997319529c5eed7b5d1a1f548
qdrv_vap_preimage_sha=c65d0190b1ee9a17271b9f677614d33ab0c2024c1d0397e55e126b312eea5d7c
qdrv_wlan_hrflags_sha=8ddbd4e89af7a6e80b815aa002a982ec9035215eecef2e2e5ed92a7c21c6ea05

sha_of()
{
	sha256sum "$1" | cut -d' ' -f1
}

require_hash()
{
	file=$1
	expected=$2
	test -f "$file" || { echo "missing input: $file" >&2; exit 2; }
	actual=$(sha_of "$file")
	test "$actual" = "$expected" || {
		echo "hash mismatch: $file expected=$expected actual=$actual" >&2
		exit 3
	}
}

case "$artifacts" in
	"$root"/outputs/kernel-port/hgw500-controls-5g-postbaseline-*) ;;
	*) echo "unsafe artifact path: $artifacts" >&2; exit 3 ;;
esac
case "$stage" in
	/home/user/openmitrastar-build/hgw500-controls-5g-postbaseline-*) ;;
	*) echo "unsafe stage path: $stage" >&2; exit 3 ;;
esac

baseline_qdrv="$baseline/rootfs/lib/modules/$release/extra/quantenna/qdrv/qdrv.ko"
require_hash "$baseline_qdrv" "$baseline_qdrv_sha"
require_hash "$baseline/module-manifest.tsv" "$baseline_manifest_sha"
require_hash "$patch" "$patch_sha"
require_hash "$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" "$recovery_preimage_sha"
require_hash "$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" "$dts_preimage_sha"
require_hash "$root/work/linux510-radio-port/quantenna/qdrv/qdrv_vap.c" "$qdrv_vap_preimage_sha"
require_hash "$root/work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c" "$qdrv_wlan_hrflags_sha"
grep -Fq 'OMQDRVHR stage=deferred reason=no-vap' \
	"$root/work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
test -f "$kernel_src/Makefile"
test -f "$kernel_out/.config"
test -f "$kernel_out/Module.symvers"
test -x "${tc}gcc"

rm -rf -- "$stage" "$artifacts"
mkdir -p "$stage/work/kernel-port/linux-5.10/drivers/misc" \
	"$stage/work/kernel-port/linux-5.10/arch/arc/boot/dts" \
	"$stage/work/linux510-radio-port" "$stage/work/sources" \
	"$artifacts/controls" "$artifacts/logs"
cp "$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" \
	"$stage/work/kernel-port/linux-5.10/drivers/misc/"
cp "$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" \
	"$stage/work/kernel-port/linux-5.10/arch/arc/boot/dts/"
cp -a "$root/work/linux510-radio-port/quantenna" \
	"$stage/work/linux510-radio-port/"
ln -s "$root/work/sources/Quantenna-GPL" \
	"$stage/work/sources/Quantenna-GPL"

git -C "$stage" apply --whitespace=error-all "$patch"
grep -Fq 'openmitrastar:green:wlan5g' \
	"$stage/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"
grep -Fq 'mitrastar,wlan5g-led-pin = <1>;' \
	"$stage/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
grep -Fq 'OMQDRVLED stage=ap-state' \
	"$stage/work/linux510-radio-port/quantenna/qdrv/qdrv_vap.c"
grep -Fq 'OMQDRVHR stage=deferred reason=no-vap' \
	"$stage/work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"

# Hard-link the immutable kernel source tree, then break links only for the two
# patched files. All generated files go to a separate O= directory.
mkdir -p "$stage/kernel-src"
cp -al "$kernel_src/." "$stage/kernel-src/"
rm -f "$stage/kernel-src/drivers/misc/qtn-topaz-recovery.c" \
	"$stage/kernel-src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
cp "$stage/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" \
	"$stage/kernel-src/drivers/misc/"
cp "$stage/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" \
	"$stage/kernel-src/arch/arc/boot/dts/"
mkdir -p "$stage/kernel-out"
cp "$kernel_out/.config" "$stage/kernel-out/.config"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=led5g-postbaseline
export KBUILD_BUILD_VERSION=1
canonical_stage=/openmitrastar/hgw500-controls-5g-postbaseline
repro_flags="-fdebug-prefix-map=$stage=$canonical_stage -fmacro-prefix-map=$stage=$canonical_stage"

make -C "$stage/kernel-src" O="$stage/kernel-out" ARCH=arc \
	CROSS_COMPILE="$tc" KCFLAGS="$repro_flags" olddefconfig \
	>"$artifacts/logs/kernel-olddefconfig.log" 2>&1
make -C "$stage/kernel-src" O="$stage/kernel-out" ARCH=arc \
	CROSS_COMPILE="$tc" KCFLAGS="$repro_flags" -j4 \
	drivers/misc/qtn-topaz-recovery.o \
	>"$artifacts/logs/kernel-object.log" 2>&1
make -C "$stage/kernel-src" O="$stage/kernel-out" ARCH=arc \
	CROSS_COMPILE="$tc" KCFLAGS="$repro_flags" -j4 \
	topaz_mitrastar_ramssh.dtb \
	>"$artifacts/logs/kernel-dtb.log" 2>&1

module_stage="$stage/work/linux510-radio-port/quantenna"
rm -f "$module_stage/qdrv/qdrv_vap.o" "$module_stage/qdrv/qdrv.o" \
	"$module_stage/qdrv/qdrv.ko" "$module_stage/qdrv/qdrv.mod" \
	"$module_stage/qdrv/qdrv.mod.c" "$module_stage/qdrv/qdrv.mod.o"
make -C "$kernel_src" O="$kernel_out" ARCH=arc CROSS_COMPILE="$tc" \
	M="$module_stage" OPENMITRASTAR_QDRV_V89_PAIR=1 \
	OPENMITRASTAR_SWITCH_EMAC_PORT=1 KCFLAGS="$repro_flags" -j4 modules \
	>"$artifacts/logs/qdrv-postbaseline.log" 2>&1
post_qdrv="$module_stage/qdrv/qdrv.ko"
test -f "$post_qdrv"
"${tc}readelf" -h "$post_qdrv" | grep -Eq 'Machine:.*(ARC|ARCompact)'
/usr/sbin/modinfo -F vermagic "$post_qdrv" | \
	grep -qx "$release mod_unload ARC700"
"${tc}strings" "$post_qdrv" | grep -Fq 'OMQDRVHR stage=deferred reason=no-vap'
"${tc}strings" "$post_qdrv" | grep -Fq 'OMQDRVLED stage=ap-state'

# Build the post-baseline package from an immutable copy of the approved W3
# baseline, replacing exactly qdrv.ko and adding the controls overlay.
cp -a "$baseline/." "$artifacts/"
artifact_qdrv="$artifacts/rootfs/lib/modules/$release/extra/quantenna/qdrv/qdrv.ko"
cp "$post_qdrv" "$artifact_qdrv"
cp "$stage/kernel-out/drivers/misc/qtn-topaz-recovery.o" \
	"$artifacts/controls/qtn-topaz-recovery-wlan5g.o"
cp "$stage/kernel-out/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb" \
	"$artifacts/controls/topaz_mitrastar_ramssh-wlan5g.dtb"
cp "$patch" "$artifacts/controls/"
cp "$evidence" "$artifacts/controls/"
cp "$stage/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" \
	"$artifacts/controls/qtn-topaz-recovery-wlan5g.c"
cp "$stage/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" \
	"$artifacts/controls/topaz_mitrastar_ramssh-wlan5g.dts"
cp "$stage/work/linux510-radio-port/quantenna/qdrv/qdrv_vap.c" \
	"$artifacts/controls/qdrv_vap-wlan5g-carrier.c"

printf 'module\tsha256\tsize\tvermagic\tdepends\n' >"$artifacts/module-manifest.tsv"
while IFS= read -r rel; do
	module="$artifacts/rootfs/lib/modules/$release/extra/quantenna/$rel"
	test -f "$module"
	hash=$(sha_of "$module")
	size=$(wc -c <"$module")
	vermagic=$(/usr/sbin/modinfo -F vermagic "$module")
	depends=$(/usr/sbin/modinfo -F depends "$module")
	printf '%s\t%s\t%s\t%s\t%s\n' "$rel" "$hash" "$size" \
		"$vermagic" "$depends" >>"$artifacts/module-manifest.tsv"
done <"$artifacts/actual-modules.txt"

awk -F '\t' '$1 != "qdrv/qdrv.ko" {print $1 "\t" $2}' \
	"$baseline/module-manifest.tsv" >"$stage/baseline-nonqdrv.tsv"
awk -F '\t' '$1 != "qdrv/qdrv.ko" {print $1 "\t" $2}' \
	"$artifacts/module-manifest.tsv" >"$stage/post-nonqdrv.tsv"
diff -u "$stage/baseline-nonqdrv.tsv" "$stage/post-nonqdrv.tsv" \
	>"$artifacts/logs/nonqdrv-delta.diff"

module_dir="$artifacts/rootfs/lib/modules/$release"
rm -f "$module_dir/modules.alias" "$module_dir/modules.alias.bin" \
	"$module_dir/modules.dep" "$module_dir/modules.dep.bin" \
	"$module_dir/modules.symbols" "$module_dir/modules.symbols.bin"
if ! /usr/sbin/depmod -e -F "$kernel_out/System.map" \
	-b "$artifacts/rootfs" "$release" 2>"$artifacts/depmod-unresolved.log"; then
	cat "$artifacts/depmod-unresolved.log" >&2
	exit 8
fi
test ! -s "$artifacts/depmod-unresolved.log"

post_qdrv_sha=$(sha_of "$artifact_qdrv")
test "$post_qdrv_sha" != "$baseline_qdrv_sha"
(cd "$artifacts/rootfs" && find . -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +)
(cd "$artifacts/rootfs" && tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
	--owner=0 --group=0 --numeric-owner -cf - .) | gzip -n \
	>"$artifacts/quantenna-rootfs-overlay.tar.gz"
cat >"$artifacts/postbaseline.env" <<EOF
W1_LED5G_POSTBASELINE=1
W1_OFFLINE_ONLY=1
W1_HARDWARE_EXECUTED=0
W1_FLASH_WRITES=0
W1_BASELINE_QDRV_SHA256=$baseline_qdrv_sha
W1_POSTBASELINE_QDRV_SHA256=$post_qdrv_sha
W1_PATCH_SHA256=$patch_sha
W1_NON_QDRV_MODULE_DELTA=0
W1_LED_GPIO=1
W1_LED_ACTIVE_HIGH=1
W1_LED_IFNAME=wifi0
W1_LED_CLASS=openmitrastar:green:wlan5g
EOF

python3 - "$artifacts" "$baseline" "$baseline_qdrv_sha" \
	"$post_qdrv_sha" "$patch_sha" <<'PY'
import hashlib
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
baseline = pathlib.Path(sys.argv[2])
baseline_qdrv, post_qdrv, patch_sha = sys.argv[3:6]

def meta(path):
    data = path.read_bytes()
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

essential = {
    "module-manifest.tsv": meta(out / "module-manifest.tsv"),
    "postbaseline.env": meta(out / "postbaseline.env"),
    "depmod-unresolved.log": meta(out / "depmod-unresolved.log"),
    "controls/openmitrastar-wlan5g-led-carrier.patch": meta(out / "controls/openmitrastar-wlan5g-led-carrier.patch"),
    "controls/OEM_WLAN5G_LED_EVIDENCE.md": meta(out / "controls/OEM_WLAN5G_LED_EVIDENCE.md"),
    "controls/qtn-topaz-recovery-wlan5g.o": meta(out / "controls/qtn-topaz-recovery-wlan5g.o"),
    "controls/topaz_mitrastar_ramssh-wlan5g.dtb": meta(out / "controls/topaz_mitrastar_ramssh-wlan5g.dtb"),
    "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko": meta(out / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"),
}
manifest = {
    "schema": "openmitrastar.hgw500-wlan5g-controls-postbaseline/v1",
    "created": "2026-08-20",
    "classification": "OFFLINE-POSTBASELINE-NO-HARDWARE-NO-FLASH",
    "baseline": {
        "path": str(baseline),
        "qdrv_sha256": baseline_qdrv,
        "immutable": True,
    },
    "postbaseline": {
        "qdrv_sha256": post_qdrv,
        "patch_sha256": patch_sha,
        "module_count": 25,
        "non_qdrv_module_delta": 0,
        "led_gpio": 1,
        "led_active_high": True,
        "led_interface": "wifi0",
        "led_class": "openmitrastar:green:wlan5g",
        "carrier_contract": "HOSTAP+IEEE80211_S_RUN",
    },
    "preserved": {
        "wlan2g_gpio": 11,
        "wifi_button_gpio": 2,
        "stage0_gpio": 7,
        "hrflags_marker": "OMQDRVHR stage=deferred reason=no-vap",
        "watchdog_changed": False,
    },
    "execution": {
        "hardware_executed": False,
        "com3_opened": False,
        "network_mutated": False,
        "flash_writes": 0,
    },
    "artifacts": essential,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

(cd "$artifacts" && find . -type f ! -name SHA256SUMS -print0 | \
	sort -z | xargs -0 sha256sum >SHA256SUMS)

# Re-check shared preimages after every build. This proves the integration was
# isolated and did not mutate the active W3 source or approved baseline.
require_hash "$baseline_qdrv" "$baseline_qdrv_sha"
require_hash "$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" "$recovery_preimage_sha"
require_hash "$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" "$dts_preimage_sha"
require_hash "$root/work/linux510-radio-port/quantenna/qdrv/qdrv_vap.c" "$qdrv_vap_preimage_sha"
require_hash "$root/work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c" "$qdrv_wlan_hrflags_sha"

printf 'W1_LED5G_POSTBASELINE_BUILD_PASS=1 baseline=%s post=%s artifacts=%s\n' \
	"$baseline_qdrv_sha" "$post_qdrv_sha" "$artifacts"
