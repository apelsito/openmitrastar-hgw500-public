#!/bin/sh

# Offline-only build for the complete HGW-500BNA-QCv2 front-panel LED surface.
# Produces a kernel object, DTB, BusyBox control script and evidence manifest.
# It never contacts hardware and never writes flash.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stage=${OM_LED_CONTROLS_STAGE:-/home/user/openmitrastar-build/hgw500-led-controls-20260821}
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
kernel_out=${TOPAZ_KERNEL_OUT:-/home/user/openmitrastar-build/radiohw-probe}
artifact=${OM_LED_CONTROLS_ARTIFACT:-$root/outputs/kernel-port/hgw500-led-controls-20260821}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
driver="$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"
dts="$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
ledctl="$root/work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-ledctl"
contract="$root/work/mission-state/w4-rootfs-product/rootfs/usr/share/openmitrastar/leds/hgw500-leds.json"
document="$root/docs/HGW500_LED_CONTROL.md"

case "$stage" in /home/user/openmitrastar-build/hgw500-led-controls-*) ;; *) exit 2 ;; esac
case "$artifact" in "$root"/outputs/kernel-port/hgw500-led-controls-*) ;; *) exit 2 ;; esac
for required in "$kernel_src/Makefile" "$kernel_out/.config" "$driver" "$dts" \
	"$ledctl" "$contract" "$document" "${tc}gcc"; do
	[ -f "$required" ] || { printf 'missing LED input: %s\n' "$required" >&2; exit 3; }
done

rm -rf "$stage" "$artifact"
mkdir -p "$stage/kernel-src" "$stage/kernel-out" "$artifact/logs" "$artifact/rootfs/usr/sbin" \
	"$artifact/rootfs/usr/share/openmitrastar/leds"
cp -al "$kernel_src/." "$stage/kernel-src/"
rm -f "$stage/kernel-src/drivers/misc/qtn-topaz-recovery.c" \
	"$stage/kernel-src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
cp "$driver" "$stage/kernel-src/drivers/misc/"
cp "$dts" "$stage/kernel-src/arch/arc/boot/dts/"
cp "$kernel_out/.config" "$stage/kernel-out/.config"

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1787270400}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=led-controls-offline
export KBUILD_BUILD_VERSION=1
canonical=/openmitrastar/hgw500-led-controls
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
	exit 4
}

python.exe "$(wslpath -w "$root/tools/test_openmitrastar_led_controls.py")" -v \
	>"$artifact/logs/tests.log" 2>&1

cp "$stage/kernel-out/drivers/misc/qtn-topaz-recovery.o" "$artifact/"
cp "$stage/kernel-out/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb" "$artifact/"
cp "$driver" "$artifact/"
cp "$dts" "$artifact/"
cp "$ledctl" "$artifact/rootfs/usr/sbin/"
cp "$contract" "$artifact/rootfs/usr/share/openmitrastar/leds/"
cp "$document" "$artifact/"
chmod 0755 "$artifact/rootfs/usr/sbin/om-ledctl"
chmod 0644 "$artifact/rootfs/usr/share/openmitrastar/leds/hgw500-leds.json"

python3 - "$artifact" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

def metadata(path: Path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

artifacts = {
    str(path.relative_to(root)).replace("\\", "/"): metadata(path)
    for path in sorted(root.rglob("*"))
    if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"}
}
manifest = {
    "schema": "openmitrastar.hgw500-led-controls/v1",
    "classification": "OFFLINE-LED-CONTROLS-RAM-ONLY-NO-FLASH",
    "model": "HGW-500BNA-QCv2",
    "hardware_revision": "A2",
    "physical_windows": 3,
    "independent_channels": 5,
    "hardware_actions": False,
    "flash_actions": False,
    "candidate_eligible": False,
    "physical_colour_identification": "pending-gpio7-gpio9-gpio10",
    "artifacts": artifacts,
}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

(cd "$artifact" && find . -type f ! -name SHA256SUMS -print0 | \
	sort -z | xargs -0 sha256sum >SHA256SUMS)

printf 'OMLED_CONTROLS_BUILD_PASS channels=5 windows=3 hardware=0 flash=0 object=%s dtb=%s\n' \
	"$(sha256sum "$artifact/qtn-topaz-recovery.o" | cut -d' ' -f1)" \
	"$(sha256sum "$artifact/topaz_mitrastar_ramssh.dtb" | cut -d' ' -f1)"
