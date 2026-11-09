#!/bin/sh

# Isolated, offline build gate for HGW-500BNA-QCv2 front-panel/reset parity.
# It never contacts hardware and contains no flash operation.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stage=${OM_Q1_CONTROLS_STAGE:-/home/user/openmitrastar-build/hgw500-q1-controls-parity-20260820}
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
kernel_out=${TOPAZ_KERNEL_OUT:-/home/user/openmitrastar-build/radiohw-probe}
artifact=${OM_Q1_CONTROLS_ARTIFACT:-$root/outputs/kernel-port/hgw500-q1-controls-parity-20260820}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

case "$stage" in /home/user/openmitrastar-build/hgw500-q1-controls-parity-*) ;; *) exit 2 ;; esac
case "$artifact" in "$root"/outputs/kernel-port/hgw500-q1-controls-parity-*) ;; *) exit 2 ;; esac
[ -f "$kernel_src/Makefile" ]
[ -f "$kernel_out/.config" ]
[ -x "${tc}gcc" ]

rm -rf "$stage" "$artifact"
mkdir -p "$stage/kernel-src" "$stage/kernel-out" "$artifact/logs" "$artifact/rootfs"
cp -al "$kernel_src/." "$stage/kernel-src/"
rm -f "$stage/kernel-src/drivers/misc/qtn-topaz-recovery.c" \
	"$stage/kernel-src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
cp "$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" \
	"$stage/kernel-src/drivers/misc/"
cp "$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" \
	"$stage/kernel-src/arch/arc/boot/dts/"
cp "$kernel_out/.config" "$stage/kernel-out/.config"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1787184000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=q1-controls-offline
export KBUILD_BUILD_VERSION=1
canonical=/openmitrastar/hgw500-q1-controls-parity
flags="-fdebug-prefix-map=$stage=$canonical -fmacro-prefix-map=$stage=$canonical"

make -C "$stage/kernel-src" O="$stage/kernel-out" ARCH=arc \
	CROSS_COMPILE="$tc" KCFLAGS="$flags" olddefconfig \
	>"$artifact/logs/olddefconfig.log" 2>&1
make -C "$stage/kernel-src" O="$stage/kernel-out" ARCH=arc \
	CROSS_COMPILE="$tc" KCFLAGS="$flags" -j4 \
	drivers/misc/qtn-topaz-recovery.o \
	>"$artifact/logs/kernel-object.log" 2>&1
make -C "$stage/kernel-src" O="$stage/kernel-out" ARCH=arc \
	CROSS_COMPILE="$tc" KCFLAGS="$flags" -j4 \
	topaz_mitrastar_ramssh.dtb \
	>"$artifact/logs/kernel-dtb.log" 2>&1

"$stage/kernel-src/scripts/checkpatch.pl" --no-tree --file \
	"$stage/kernel-src/drivers/misc/qtn-topaz-recovery.c" \
	>"$artifact/logs/checkpatch.log" 2>&1 || {
	cat "$artifact/logs/checkpatch.log" >&2
	exit 3
}

python.exe "$(wslpath -w "$root/tools/test_openmitrastar_q1_controls_parity.py")" \
	>"$artifact/logs/q1-tests.log" 2>&1
python.exe "$(wslpath -w "$root/tools/test_openmitrastar_hgw500_controls.py")" \
	>"$artifact/logs/legacy-controls-tests.log" 2>&1
python.exe "$(wslpath -w "$root/tools/test_openmitrastar_hgw500_wlan5g_led.py")" \
	>"$artifact/logs/wlan5g-tests.log" 2>&1

cp "$stage/kernel-out/drivers/misc/qtn-topaz-recovery.o" "$artifact/"
cp "$stage/kernel-out/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb" "$artifact/"
cp "$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" "$artifact/"
cp "$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" "$artifact/"
cp "$root/work/linux510-radio-port/quantenna/qdrv/qdrv_vap.c" "$artifact/"
cp "$root/work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c" "$artifact/"
cp "$root/work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start" \
	"$artifact/rootfs/"
cp "$root/docs/HGW500_Q1_CONTROLS_PARITY_20260820.md" "$artifact/"
cp "$root/docs/HGW500_Q1_CONTROLS_PARITY_20260820.json" "$artifact/"
for file in om-config-backup om-factory-reset om-radio2g-toggle om-radio5g-toggle om-control-event; do
	cp "$root/work/mission-state/w4-rootfs-product/rootfs/usr/sbin/$file" "$artifact/rootfs/"
done
cp "$root/work/mission-state/w4-rootfs-product/rootfs/etc/mdev.conf" "$artifact/rootfs/"

(cd "$artifact" && find . -type f ! -name SHA256SUMS ! -name manifest.json -print0 | \
	sort -z | xargs -0 sha256sum >SHA256SUMS)
python3 - "$artifact" <<'PY'
import hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1])
def meta(path):
    data = path.read_bytes()
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

manifest = {
    "schema": "openmitrastar.hgw500-q1-controls-parity-build/v1",
    "classification": "OFFLINE-CONTROLS-PARITY-NO-HARDWARE-NO-FLASH",
    "hardware_executed": False,
    "flash_executed": False,
    "candidate_eligible": False,
    "tests": {"q1": 12, "legacy_controls": 13, "wlan5g": 8},
    "artifacts": {
        str(path.relative_to(root)).replace("\\", "/"): meta(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in {"manifest.json"}
    },
}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

printf 'OMQ1_CONTROLS_BUILD_PASS object=%s dtb=%s tests=33 hardware=0 flash=0\n' \
	"$(sha256sum "$artifact/qtn-topaz-recovery.o" | cut -d' ' -f1)" \
	"$(sha256sum "$artifact/topaz_mitrastar_ramssh.dtb" | cut -d' ' -f1)"
