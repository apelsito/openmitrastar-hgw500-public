#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out=${OM_PRODUCT_KERNEL_OUT:-/home/user/openmitrastar-build/product-rootfs-ram-equivalent/kernel-a}
initramfs=${OM_PRODUCT_INITRAMFS:-/home/user/openmitrastar-build/product-rootfs-ram-equivalent/product-rootfs-a.cpio}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
overlay="$root/tools/apply_topaz_linux_510_overlay.sh"
template="$root/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
pack="$root/tools/pack_topaz_webformat.py"
contract="$root/tools/bootbase_contract_emulator.py"
protected="$root/work/tftp/omvl/linux510-product-rootfs-ram-equivalent-v1-RAM-ONLY.bin"
artifact=${OM_PRODUCT_NETSS_IOSS_ARTIFACT:-$root/outputs/kernel-port/product-netss-ioss-fwtfix-20260818-0415-RAM-ONLY-NO-FLASH}
tftp=${OM_PRODUCT_NETSS_IOSS_TFTP:-$root/work/tftp/omvl/linux510-product-netss-ioss-fwtfix-v1-RAM-ONLY.bin}
base=linux510-product-netss-ioss-fwtfix-v1-RAM-ONLY
epoch=${SOURCE_DATE_EPOCH:-1787011200}
jobs=${TOPAZ_JOBS:-12}

case "$out" in /home/user/openmitrastar-build/*) ;; *) exit 2 ;; esac
case "$artifact" in "$root"/outputs/kernel-port/*) ;; *) exit 2 ;; esac
case "$tftp" in "$root"/work/tftp/omvl/*) ;; *) exit 2 ;; esac
case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
[ "$jobs" -gt 0 ]

for required in "$src/Makefile" "$out/.config" "$initramfs" \
	"${tc}gcc" "$overlay" "$template" "$pack" "$contract" "$protected"; do
	[ -e "$required" ] || { echo "missing input: $required" >&2; exit 3; }
done
grep -qx "CONFIG_INITRAMFS_SOURCE=\"$initramfs\"" "$out/.config"
grep -qx 'CONFIG_QTN_TOPAZ_RECOVERY=y' "$out/.config"
grep -qx 'CONFIG_QTN_TOPAZ_EMAC=y' "$out/.config"

# Preserve mtimes for unchanged overlay files so Kbuild recompiles only the
# recovery driver, DTB and their link dependants.
shim=$(mktemp -d "${TMPDIR:-/tmp}/openmitrastar-product-cp.XXXXXX")
cleanup() { rm -rf -- "$shim"; }
trap cleanup 0 1 2 15
cat >"$shim/cp" <<'EOF'
#!/bin/sh
if [ "$#" -eq 2 ]; then
	source_file=$1
	destination=$2
	if [ -d "$destination" ]; then
		target=$destination/$(basename -- "$source_file")
	else
		target=$destination
	fi
	if [ -f "$source_file" ] && [ -f "$target" ] && cmp -s -- "$source_file" "$target"; then
		exit 0
	fi
fi
exec /bin/cp "$@"
EOF
chmod 0755 "$shim/cp"
PATH="$shim:$PATH" sh "$overlay" "$src"

cmp -s "$root/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c" \
	"$src/drivers/misc/qtn-topaz-recovery.c"
cmp -s "$root/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" \
	"$src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"

export SOURCE_DATE_EPOCH=$epoch
export KBUILD_BUILD_TIMESTAMP="@$epoch"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=product-netss-ioss-fwtfix
export KBUILD_BUILD_VERSION=1

build_log="$out/openmitrastar-netss-ioss-build.log"
if ! make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	-j"$jobs" uImage.bin >"$build_log" 2>&1; then
	tail -n 240 "$build_log" >&2
	exit 4
fi
cat "$build_log"
release=$(make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)
[ "$release" = 5.10.260-openmitrastar-radiohw ]

vmlinux="$out/vmlinux"
uimage="$out/arch/arc/boot/uImage.bin"
dtb="$out/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb"
for output in "$vmlinux" "$uimage" "$dtb"; do [ -f "$output" ] || exit 4; done
strings "$vmlinux" | grep -q 'OMNETSS stage=complete pulse=%#010x wait_ms=%u enet0_reset=0'
strings "$vmlinux" | grep -q 'mitrastar,netss-ioss-reset-pulse'
dtc -I dtb -O dts "$dtb" 2>/dev/null | \
	grep -q 'mitrastar,netss-ioss-reset-pulse;'

protected_before=$(sha256sum "$protected" | cut -d' ' -f1)
rm -rf -- "$artifact"
mkdir -p "$artifact" "$(dirname -- "$tftp")"
cp "$out/.config" "$artifact/$base.config"
cp "$vmlinux" "$artifact/$base.vmlinux"
cp "$uimage" "$artifact/$base.uImage"
cp "$dtb" "$artifact/$base.dtb"
cp "$initramfs" "$artifact/$base.initramfs.cpio"
cp "$build_log" "$artifact/build.log"
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
    "product-netss-ioss-fwtfix-ram-only",
    image.read_bytes(), module.PARTITIONS["linux_live"][1])
output.write_text(json.dumps(module.image_to_dict(result), indent=2, sort_keys=True) + "\n")
if not result.accepted_by_contract:
    raise SystemExit("Bootbase contract rejected")
PY

protected_after=$(sha256sum "$protected" | cut -d' ' -f1)
[ "$protected_before" = "$protected_after" ]

sha256sum "$artifact/$base.config" "$artifact/$base.vmlinux" \
	"$artifact/$base.uImage" "$artifact/$base.dtb" \
	"$artifact/$base.initramfs.cpio" "$artifact/$base.webformat.bin" \
	"$artifact/build.log" "$tftp" >"$artifact/SHA256SUMS"

python3 - "$root" "$artifact" "$base" "$tftp" "$protected" \
	"$protected_before" "$release" "$epoch" <<'PY'
import hashlib, json, pathlib, sys
root, artifact, base, tftp, protected = map(pathlib.Path, sys.argv[1:6])
protected_hash, release, epoch = sys.argv[6], sys.argv[7], int(sys.argv[8])
def info(path):
    p = pathlib.Path(path)
    return {"file": p.name, "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
manifest = {
    "schema": "openmitrastar.product-netss-ioss-fwtfix/v1",
    "generated_utc": "2026-08-18T04:15:00+00:00",
    "classification": "RAM-ONLY-NO-FLASH",
    "candidate_eligible": False,
    "hardware_actions": False,
    "flash_supported": False,
    "incremental_kernel_build": True,
    "kernel_release": release,
    "source_date_epoch": epoch,
    "dt_gate": {
        "compatible": "mitrastar,hgw-500bna-qcv2",
        "property": "mitrastar,netss-ioss-reset-pulse",
        "pulse_mask": "0x000000a0",
        "wait_ms": 50,
        "enet0_reset": False,
    },
    "sources": {
        "driver": info(root / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"),
        "dts": info(root / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"),
    },
    "artifacts": {
        "config": info(artifact / f"{base}.config"),
        "vmlinux": info(artifact / f"{base}.vmlinux"),
        "uimage": info(artifact / f"{base}.uImage"),
        "dtb": info(artifact / f"{base}.dtb"),
        "initramfs": info(artifact / f"{base}.initramfs.cpio"),
        "webformat": info(artifact / f"{base}.webformat.bin"),
        "build_log": info(artifact / "build.log"),
        "tftp_copy": info(tftp),
    },
    "protected_product": {
        "file": str(protected), "sha256": protected_hash, "unchanged": True,
    },
    "runtime_gate": "hardware_ram_boot_pending",
}
(artifact / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf 'OMPRODUCT_NETSS_IOSS_INCREMENTAL_BUILD_PASS sha256=%s bytes=%s\n' \
	"$(sha256sum "$tftp" | cut -d' ' -f1)" "$(wc -c <"$tftp")"
