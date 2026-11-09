#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out=${OM_PRODUCT_KERNEL_OUT:-/home/user/openmitrastar-build/product-rootfs-ram-equivalent/kernel-a}
initramfs=${OM_PRODUCT_INITRAMFS:-/home/user/openmitrastar-build/product-rootfs-ram-equivalent/product-rootfs-a.cpio}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
template="$root/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
pack="$root/tools/pack_topaz_webformat.py"
contract="$root/tools/bootbase_contract_emulator.py"
protected="$root/work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin"
artifact="$root/outputs/kernel-port/product-posix-timers-20260820-RAM-ONLY-NO-FLASH"
tftp="$root/work/tftp/omvl/linux510-product-posix-timers-v1-RAM-ONLY.bin"
base=linux510-product-posix-timers-v1-RAM-ONLY
epoch=${SOURCE_DATE_EPOCH:-1787011200}
jobs=${TOPAZ_JOBS:-12}

for input in "$src/Makefile" "$out/.config" "$initramfs" "${tc}gcc" \
	"$template" "$pack" "$contract" "$protected"; do
	[ -e "$input" ] || { echo "missing input: $input" >&2; exit 3; }
done
grep -qx "CONFIG_INITRAMFS_SOURCE=\"$initramfs\"" "$out/.config"
protected_before=$(sha256sum "$protected" | cut -d' ' -f1)

"$src/scripts/config" --file "$out/.config" --enable POSIX_TIMERS
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
grep -qx 'CONFIG_POSIX_TIMERS=y' "$out/.config"

export SOURCE_DATE_EPOCH=$epoch
export KBUILD_BUILD_TIMESTAMP="@$epoch"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=product-posix-timers
export KBUILD_BUILD_VERSION=1
log="$out/openmitrastar-posix-timers-build.log"
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j"$jobs" uImage.bin >"$log" 2>&1 || {
	tail -n 240 "$log" >&2
	exit 4
}

release=$(make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)
[ "$release" = 5.10.260-openmitrastar-radiohw ]
uimage="$out/arch/arc/boot/uImage.bin"
vmlinux="$out/vmlinux"
dtb="$out/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb"
for output in "$uimage" "$vmlinux" "$dtb"; do [ -f "$output" ] || exit 4; done

rm -rf -- "$artifact"
mkdir -p "$artifact" "$(dirname -- "$tftp")"
cp "$out/.config" "$artifact/$base.config"
cp "$vmlinux" "$artifact/$base.vmlinux"
cp "$uimage" "$artifact/$base.uImage"
cp "$dtb" "$artifact/$base.dtb"
cp "$initramfs" "$artifact/$base.initramfs.cpio"
cp "$log" "$artifact/build.log"
python3 "$pack" "$uimage" "$template" "$artifact/$base.webformat.bin" >/dev/null
cp "$artifact/$base.webformat.bin" "$tftp"
mkimage -l "$uimage" >"$artifact/$base.mkimage.txt"

python3 - "$contract" "$artifact/$base.webformat.bin" "$artifact/bootbase-contract.json" <<'PY'
import importlib.util, json, pathlib, sys
tool, image, output = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bootbase_contract", tool)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.validate_bootbase_slot(
    "product-posix-timers-ram-only", image.read_bytes(),
    module.PARTITIONS["linux_live"][1])
output.write_text(json.dumps(module.image_to_dict(result), indent=2, sort_keys=True) + "\n")
if not result.accepted_by_contract:
    raise SystemExit("Bootbase contract rejected")
PY

[ "$protected_before" = "$(sha256sum "$protected" | cut -d' ' -f1)" ]
sha256sum "$artifact"/* "$tftp" >"$artifact/SHA256SUMS"
printf 'OMPRODUCT_POSIX_TIMERS_BUILD_PASS sha256=%s bytes=%s flash=0\n' \
	"$(sha256sum "$tftp" | cut -d' ' -f1)" "$(wc -c <"$tftp")"
