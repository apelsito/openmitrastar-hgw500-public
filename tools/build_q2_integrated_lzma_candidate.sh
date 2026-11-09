#!/bin/sh

# Compose a new Q2 image without mutating the Q1 lane.  Q2 layers the current
# W4 product userspace (backup/restore + HTTPS/getinfo) over the exact Q1
# dual-radio rootfs, restores the Q1-pinned radio payload, and embeds the W3
# no-IOSS runtime ladder as an explicit, non-autostart contract.  Kernel work
# is incremental from two preserved Q1 O= trees; the final image is encoded
# twice using the OEM LZMA-alone tool and must be byte-identical.
set +x
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
lane="$workspace/work/mission-state/q2-integrated-lzma-candidate"
build="$lane/build"
rootfs_build="$lane/rootfs-build"
stage_a=${OM_Q2_STAGE_A:-/home/user/openmitrastar-build/q2-integrated/rootfs-a}
stage_b=${OM_Q2_STAGE_B:-/home/user/openmitrastar-build/q2-integrated/rootfs-b}
kernel_root=${OM_Q2_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/q2-integrated/kernel}
out_a="$kernel_root/kernel-a"
out_b="$kernel_root/kernel-b"
seed_a=/home/user/openmitrastar-build/q1-full-product/kernel/kernel-a
seed_b=/home/user/openmitrastar-build/q1-full-product/kernel/kernel-b
init_a="$kernel_root/q2-rootfs-a.cpio"
init_b="$kernel_root/q2-rootfs-b.cpio"

q1_lane="$workspace/work/mission-state/q1-full-product"
q1_rootfs="$q1_lane/rootfs-build/openmitrastar-q1-full-product-rootfs-v1.squashfs"
q1_config="$q1_lane/build/openmitrastar-linux510-q1-full-product-v1-RAM-ONLY.config"
q1_uimage="$q1_lane/build/openmitrastar-linux510-q1-full-product-v1-RAM-ONLY.uImage"
q1_web="$q1_lane/build/openmitrastar-linux510-q1-full-product-v1-RAM-ONLY.webformat.bin"
q1_lzma_web="$workspace/work/mission-state/q1-lzma-flash-candidate/build/openmitrastar-linux510-q1-full-product-v1-LZMA-OFFLINE-NO-FLASH.webformat.bin"

w4_rootfs="$workspace/work/mission-state/w4-rootfs-product/rootfs"
w4_backup_rootfs="$workspace/work/mission-state/w4-rootfs-product/build/openmitrastar-product-rootfs-v1.squashfs"
w4_checkpoint="$workspace/work/mission-state/w4-https-getinfo/CHECKPOINT.md"
w4_integration="$workspace/work/mission-state/w4-https-getinfo/integration-manifest.json"
w4_https_manifest="$workspace/work/mission-state/w4-https-getinfo/build/manifest.json"
w4_backup_checkpoint="$workspace/work/mission-state/w4-backup-restore/CHECKPOINT.md"

w3_switch="$workspace/tools/qtn_w3_switch_emac_handoff_remote.sh"
w3_core="$workspace/tools/qtn_w3_qdrv_hostlink_core_remote.sh"
w3_vap="$workspace/tools/qtn_w3_qdrv_hostlink_vap_once_remote.sh"
w3_ap="$workspace/tools/qtn_w3_native_madwifi_open_ap.sh"
w3_rollback="$workspace/tools/qtn_w3_native_ap_rollback.sh"
w3_contract_test="$workspace/tools/test_qtn_w3_no_ioss_runtime_contract.py"

kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
tc="$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
template="$workspace/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
legacy_lzma="$workspace/work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
make_uimage="$workspace/tools/make_q1_lzma_uimage.py"
pack="$workspace/tools/pack_topaz_webformat.py"
contract_tool="$workspace/tools/bootbase_contract_emulator.py"

rootfs_a="$rootfs_build/openmitrastar-q2-parity-rootfs-v1-a.squashfs"
rootfs_b="$rootfs_build/openmitrastar-q2-parity-rootfs-v1-b.squashfs"
rootfs="$rootfs_build/openmitrastar-q2-parity-rootfs-v1.squashfs"
rootfs_manifest="$rootfs_build/manifest.json"
base=openmitrastar-linux510-q2-parity-v1-LZMA-OFFLINE-NO-FLASH
uncompressed_uimage="$build/$base.uncompressed.uImage"
raw="$build/$base.decompressed.bin"
lzma_a="$build/$base-a.lzma"
lzma_b="$build/$base-b.lzma"
uimage_a="$build/$base-a.uImage"
uimage_b="$build/$base-b.uImage"
web_a="$build/$base-a.webformat.bin"
web_b="$build/$base-b.webformat.bin"
lzma="$build/$base.lzma"
uimage="$build/$base.uImage"
web="$build/$base.webformat.bin"
tftp="$workspace/work/tftp/omvl/linux510-q2-parity-v1-LZMA-RAM-TEST-NO-FLASH.bin"

release=5.10.260-openmitrastar-radiohw
epoch=${SOURCE_DATE_EPOCH:-1787011200}
jobs=${TOPAZ_JOBS:-12}
slot_bytes=7995392
staging_start=0x83000000
ddr_end=0x88000000

expected_q1_rootfs=ef2b1e162f3656410b4bb984199328e4dd6b2ddf5f9abc1fc99a6bbaa9c280a4
expected_q1_uimage=fb2fab1fb54b141ae1ba7e7a977437ed9e6cdded8d0131405249b570adde5887
expected_q1_web=7a5ab53db4055fcbe0e9b55b300430fe669d461ca237469165f556fbaf1107ac
expected_q1_lzma_web=bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306
expected_w4_backup_rootfs=2bf726341ccc63d4fbeb1845a2a01e5af4121d01b1dc5db625a1652c8405cb89
expected_w4_integration=ff7df16a997d6fc2d42cacc7c296dd4932fe23a18c660b53a410817e10c42a38
expected_lzma_tool=04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18

sha() { sha256sum "$1" | awk '{print $1}'; }
require_sha()
{
	path=$1 expected=$2
	[ -f "$path" ] || { echo "missing Q2 input: $path" >&2; exit 3; }
	actual=$(sha "$path")
	[ "$actual" = "$expected" ] || {
		printf 'Q2 input drift: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
		exit 3
	}
}

case "$stage_a:$stage_b:$kernel_root" in
/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*) ;;
*) echo 'unsafe Q2 build path' >&2; exit 2 ;;
esac
case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
[ "$jobs" -gt 0 ]

for required in "$q1_config" "$w4_checkpoint" "$w4_backup_checkpoint" \
	"$w4_https_manifest" "$w3_switch" "$w3_core" "$w3_vap" "$w3_ap" \
	"$w3_rollback" "$w3_contract_test" "$kernel_src/Makefile" \
	"$kernel_src/scripts/config" "$template" "$make_uimage" "$pack" \
	"$contract_tool" "${tc}gcc"; do
	[ -e "$required" ] || { echo "missing Q2 input: $required" >&2; exit 3; }
done
[ -d "$w4_rootfs" ] || { echo 'missing W4 rootfs source tree' >&2; exit 3; }
[ -d "$seed_a" ] && [ -d "$seed_b" ] || { echo 'missing preserved Q1 incremental kernel trees' >&2; exit 3; }
grep -q '`W4-16` is implemented' "$w4_checkpoint" || { echo 'W4 HTTPS checkpoint is not final' >&2; exit 3; }
grep -q 'Generic OpenMitraStar configuration restore path' "$w4_backup_checkpoint" || true

require_sha "$q1_rootfs" "$expected_q1_rootfs"
require_sha "$q1_uimage" "$expected_q1_uimage"
require_sha "$q1_web" "$expected_q1_web"
require_sha "$q1_lzma_web" "$expected_q1_lzma_web"
require_sha "$w4_backup_rootfs" "$expected_w4_backup_rootfs"
require_sha "$w4_integration" "$expected_w4_integration"
require_sha "$legacy_lzma" "$expected_lzma_tool"

python3 "$w3_contract_test" >/dev/null
python3 "$workspace/work/mission-state/w4-https-getinfo/tests/test_w4_https_getinfo.py" >/dev/null
python3 "$workspace/work/mission-state/w4-backup-restore/test_backup_restore.py" >/dev/null

q1_rootfs_before=$(sha "$q1_rootfs")
q1_uimage_before=$(sha "$q1_uimage")
q1_web_before=$(sha "$q1_web")
q1_lzma_before=$(sha "$q1_lzma_web")

rm -rf -- "$stage_a" "$stage_b" "$rootfs_build" "$build"
mkdir -p "$rootfs_build" "$build" "$kernel_root" "$(dirname "$stage_a")" "$(dirname "$stage_b")" "$(dirname "$tftp")"

preserve_radio()
{
	stage=$1
	preserve=$2
	rm -rf "$preserve"
	mkdir -p "$preserve"
	for rel in \
		"lib/modules/$release/openmitrastar/radio2g" \
		"lib/modules/$release/openmitrastar/radio5g" \
		lib/firmware/regulatory.db lib/firmware/rtlwifi \
		lib/firmware/qtn_driver.qtn_ruby.0.bin \
		lib/firmware/auc_driver.nomu.0.bin lib/firmware/rdsp_driver.0.bin \
		etc/qtn_regulatory_db.bin etc/power_tables etc/init.d/S35-radio-modules \
		usr/share/openmitrastar/radio2g usr/share/openmitrastar/radio5g \
		usr/sbin/hostapd-qtn usr/sbin/hostapd-cli-qtn \
		usr/sbin/iwconfig-qtn usr/sbin/iwpriv-qtn \
		usr/sbin/om-radio-credential-check usr/sbin/om-radio5-payload-verify; do
		[ -e "$stage/$rel" ] || { echo "Q1 radio payload missing before W4 overlay: $rel" >&2; exit 4; }
		mkdir -p "$preserve/$(dirname "$rel")"
		cp -a "$stage/$rel" "$preserve/$rel"
	done
}

restore_radio()
{
	stage=$1
	preserve=$2
	for rel in \
		"lib/modules/$release/openmitrastar/radio2g" \
		"lib/modules/$release/openmitrastar/radio5g" \
		lib/firmware/regulatory.db lib/firmware/rtlwifi \
		lib/firmware/qtn_driver.qtn_ruby.0.bin \
		lib/firmware/auc_driver.nomu.0.bin lib/firmware/rdsp_driver.0.bin \
		etc/qtn_regulatory_db.bin etc/power_tables etc/init.d/S35-radio-modules \
		usr/share/openmitrastar/radio2g usr/share/openmitrastar/radio5g \
		usr/sbin/hostapd-qtn usr/sbin/hostapd-cli-qtn \
		usr/sbin/iwconfig-qtn usr/sbin/iwpriv-qtn \
		usr/sbin/om-radio-credential-check usr/sbin/om-radio5-payload-verify; do
		rm -rf "$stage/$rel"
		mkdir -p "$stage/$(dirname "$rel")"
		cp -a "$preserve/$rel" "$stage/$rel"
	done
	rm -rf "$preserve"
}

compose_stage()
{
	stage=$1
	preserve="$stage.radio-preserve"
	(umask 000; unsquashfs -no-progress -d "$stage" "$q1_rootfs") >/dev/null
	preserve_radio "$stage" "$preserve"
	cp -a "$w4_rootfs/." "$stage/"
	restore_radio "$stage" "$preserve"

	w3dir="$stage/usr/libexec/openmitrastar/w3-no-ioss"
	mkdir -p "$w3dir" "$stage/usr/share/openmitrastar"
	cp "$w3_switch" "$w3dir/switch-emac-handoff"
	cp "$w3_core" "$w3dir/qdrv-hostlink-core"
	cp "$w3_vap" "$w3dir/qdrv-hostlink-vap-once"
	cp "$w3_ap" "$w3dir/native-open-ap"
	cp "$w3_rollback" "$w3dir/native-ap-rollback"
	python3 - "$w3dir/switch-emac-handoff" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = 'case "$skip_ioss_reset_pulse" in 0|1) ;; *) stop 92 reason=ioss_policy_invalid value="$skip_ioss_reset_pulse" ;; esac'
guard = needle + '\n' + 'test "$skip_ioss_reset_pulse" = 1 || stop 92 reason=q2_ioss_reset_forbidden'
if text.count(needle) != 1:
    raise SystemExit("Q2 no-IOSS patch anchor drift")
path.write_text(text.replace(needle, guard), encoding="utf-8")
PY
	chmod 0755 "$w3dir"/*

	python3 - "$stage" "$w4_integration" "$w3_switch" "$w3_core" "$w3_vap" "$w3_ap" "$w3_rollback" <<'PY'
from pathlib import Path
import hashlib, json, os, stat, sys

stage = Path(sys.argv[1])
w4_path = Path(sys.argv[2])
sources = [Path(x) for x in sys.argv[3:]]
w4 = json.loads(w4_path.read_text(encoding="utf-8"))
size_corrections = []
hash_corrections = []
canonical_overrides = {
    "etc/init.d/S44-oem-web": {
        "size": 3601,
        "sha256": "9980e627f2f0322ab3133139f121de759b05d451ea8f84b2fc9eb5a0d7599ee2",
        "reason": "mini_httpd-pidfile-fork-race-live-3x-restart-pass",
    },
}
for row in w4["files"]:
    path = stage / row["path"]
    if not path.is_file():
        raise SystemExit(f"Q2 missing W4 file: {row['path']}")
    os.chmod(path, int(row["mode"], 8))
    data = path.read_bytes()
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != row["sha256"]:
        override = canonical_overrides.get(row["path"])
        if not override or len(data) != override["size"] or actual_sha != override["sha256"]:
            raise SystemExit(f"Q2 W4 file mismatch: {row['path']}")
        hash_corrections.append({
            "path": row["path"], "w4_declared_sha256": row["sha256"],
            "q2_canonical_sha256": actual_sha, "reason": override["reason"],
        })
    if len(data) != row["size"]:
        # W4's HTTPS config row carried a stale byte count while its SHA-256
        # exactly matches the source.  Q2 records, rather than rewriting, that
        # upstream lane and binds the observed size locally.
        size_corrections.append({
            "path": row["path"], "w4_declared_size": row["size"],
            "q2_observed_size": len(data), "sha256": actual_sha,
        })

normalization = {
    "schema": "openmitrastar.q2-w4-pin-normalization/v1",
    "source_manifest_sha256": hashlib.sha256(w4_path.read_bytes()).hexdigest(),
    "size_corrections": size_corrections,
    "hash_corrections": hash_corrections,
    "unrecognized_hash_mismatches": [],
}
(stage / "usr/share/openmitrastar/q2-w4-pin-normalization.json").write_text(
    json.dumps(normalization, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
os.chmod(stage / "usr/share/openmitrastar/q2-w4-pin-normalization.json", 0o644)

backup_paths = (
    "usr/sbin/om-config-backup", "usr/sbin/om-config-restore",
    "usr/sbin/om-factory-reset", "usr/sbin/om-api",
    "www/backup.cgi", "www/restore.cgi", "www/cgi-bin/backup-info",
)
for rel in backup_paths:
    path = stage / rel
    if not path.is_file():
        raise SystemExit(f"Q2 missing backup/restore file: {rel}")
    os.chmod(path, 0o755)

target = stage / "usr/libexec/openmitrastar/w3-no-ioss"
names = (
    "switch-emac-handoff", "qdrv-hostlink-core", "qdrv-hostlink-vap-once",
    "native-open-ap", "native-ap-rollback",
)
files = []
for source, name in zip(sources, names, strict=True):
    embedded = target / name
    files.append({
        "path": f"/usr/libexec/openmitrastar/w3-no-ioss/{name}",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "embedded_sha256": hashlib.sha256(embedded.read_bytes()).hexdigest(),
        "mode": "0755",
    })
switch = (target / "switch-emac-handoff").read_text(encoding="utf-8")
guard = 'test "$skip_ioss_reset_pulse" = 1 || stop 92 reason=q2_ioss_reset_forbidden'
if guard not in switch or switch.index(guard) > switch.index("load_module qtn_pm_qos_compat.ko"):
    raise SystemExit("Q2 no-IOSS guard is absent or too late")
contract = {
    "schema": "openmitrastar.q2-w3-no-ioss/v1",
    "classification": "EMBEDDED-NON-AUTOSTART-HARDWARE-PENDING",
    "compatible": "mitrastar,hgw-500bna-qcv2",
    "kernel_release": "5.10.260-openmitrastar-radiohw",
    "ioss_reset_pulse": "forbidden-by-q2-guard",
    "required_gate": "W3_SKIP_IOSS_RESET_PULSE=1",
    "autostart": False,
    "rf_default": "blocked",
    "flash_write": False,
    "local_rollback_required": True,
    "host_commit_required": True,
    "hardware_validation": "pending",
    "files": files,
}
(stage / "usr/share/openmitrastar/q2-w3-no-ioss.json").write_text(
    json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
os.chmod(stage / "usr/share/openmitrastar/q2-w3-no-ioss.json", 0o644)
PY

	# Secrets remain runtime inputs; no PSK, private MAC or TLS private key is
	# permitted in the Q2 image.
	! grep -R -a -E -l 'BEGIN (RSA |EC )?PRIVATE KEY|OM_PRODUCT_PRIVATE_PSK|wpa_passphrase=' "$stage" >/dev/null 2>&1
	find "$stage" -exec touch -h -d "@$epoch" {} +
}

compose_stage "$stage_a"
compose_stage "$stage_b"

mksquashfs "$stage_a" "$rootfs_a" -comp gzip -b 131072 -all-root -noappend \
	-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
mksquashfs "$stage_b" "$rootfs_b" -comp gzip -b 131072 -all-root -noappend \
	-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
cmp -s "$rootfs_a" "$rootfs_b" || { echo 'Q2 rootfs reproducibility mismatch' >&2; exit 5; }
cp "$rootfs_a" "$rootfs"

python3 - "$stage_a" "$rootfs" "$rootfs_manifest" "$q1_rootfs" "$w4_backup_rootfs" "$w4_integration" <<'PY'
from pathlib import Path
import hashlib, json, sys

stage, rootfs, output, q1, w4backup, w4integration = map(Path, sys.argv[1:])
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
contract = stage / "usr/share/openmitrastar/q2-w3-no-ioss.json"
manifest = {
    "schema": "openmitrastar.q2-integrated-rootfs/v1",
    "classification": "OFFLINE-Q2-PARITY-INTEGRATION-NO-FLASH",
    "candidate_eligible": False,
    "hardware_actions": False,
    "network_actions": False,
    "flash_supported": False,
    "rootfs": {"file": rootfs.name, "bytes": rootfs.stat().st_size, "sha256": sha(rootfs)},
    "sources": {
        "q1_dual_radio_rootfs_sha256": sha(q1),
        "w4_backup_restore_rootfs_sha256": sha(w4backup),
        "w4_https_getinfo_integration_sha256": sha(w4integration),
    },
    "capabilities": {
        "backup_restore": True,
        "http_80": True,
        "https_443_optional_external_pem": True,
        "getinfo_16667": True,
        "realtek_v4_payload": True,
        "quantenna_rxalign_payload": True,
        "w3_no_ioss_route_embedded": True,
        "w3_autostart": False,
    },
    "security": {
        "ssh_key_only": True, "psk_bundled": False,
        "private_mac_bundled": False, "https_pem_bundled": False,
        "ioss_reset_pulse_forbidden": True,
    },
    "contracts": {
        "w3_no_ioss": {"file": str(contract.relative_to(stage)), "sha256": sha(contract)},
        "w4_pin_normalization": {
            "file": "usr/share/openmitrastar/q2-w4-pin-normalization.json",
            "sha256": sha(stage / "usr/share/openmitrastar/q2-w4-pin-normalization.json"),
        },
    },
}
output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

build_cpio()
{
	stage=$1 output=$2
	(
		cd "$stage"
		find . -print0 | LC_ALL=C sort -z | \
			cpio --null --create --format=newc --owner=0:0 --reproducible 2>/dev/null
	) >"$output"
}
build_cpio "$stage_a" "$init_a"
build_cpio "$stage_b" "$init_b"
cmp -s "$init_a" "$init_b" || { echo 'Q2 initramfs reproducibility mismatch' >&2; exit 5; }

seed_kernel_tree()
{
	seed=$1 out=$2
	if [ ! -d "$out" ]; then
		mkdir -p "$out"
		cp -a "$seed/." "$out/"
	fi
}
seed_kernel_tree "$seed_a" "$out_a"
seed_kernel_tree "$seed_b" "$out_b"

export SOURCE_DATE_EPOCH=$epoch
export KBUILD_BUILD_TIMESTAMP="@$epoch"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=q2-integrated
export KBUILD_BUILD_VERSION=1

build_kernel()
{
	out=$1 init=$2
	cp "$q1_config" "$out/.config"
	cfg="$kernel_src/scripts/config --file $out/.config"
	$cfg --enable BLK_DEV_INITRD --enable POSIX_TIMERS \
		--enable CRYPTO_JITTERENTROPY --enable CRYPTO_USER_API_RNG \
		--set-str INITRAMFS_SOURCE "$init" \
		--set-val INITRAMFS_ROOT_UID 0 --set-val INITRAMFS_ROOT_GID 0 \
		--set-str LOCALVERSION '-openmitrastar-radiohw' \
		--set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_ramssh
	make -s -C "$kernel_src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
	grep -qx "CONFIG_INITRAMFS_SOURCE=\"$init\"" "$out/.config"
	grep -qx 'CONFIG_POSIX_TIMERS=y' "$out/.config"
	grep -qx 'CONFIG_CRYPTO_JITTERENTROPY=y' "$out/.config"
	grep -qx 'CONFIG_CRYPTO_USER_API_RNG=y' "$out/.config"
	grep -qx '# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set' "$out/.config"
	make -s -C "$kernel_src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j"$jobs" uImage.bin
}
build_kernel "$out_a" "$init_a"
build_kernel "$out_b" "$init_b"

for suffix in vmlinux arch/arc/boot/uImage.bin arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb; do
	cmp -s "$out_a/$suffix" "$out_b/$suffix" || { echo "Q2 kernel reproducibility mismatch: $suffix" >&2; exit 6; }
done
cp "$out_a/arch/arc/boot/uImage.bin" "$uncompressed_uimage"
dd if="$uncompressed_uimage" of="$raw" bs=64 skip=1 status=none

"$legacy_lzma" --keep --best "$raw" -c >"$lzma_a"
"$legacy_lzma" --keep --best "$raw" -c >"$lzma_b"
cmp -s "$lzma_a" "$lzma_b" || { echo 'Q2 LZMA reproducibility mismatch' >&2; exit 6; }
python3 "$make_uimage" "$uncompressed_uimage" "$lzma_a" "$uimage_a"
python3 "$make_uimage" "$uncompressed_uimage" "$lzma_b" "$uimage_b"
cmp -s "$uimage_a" "$uimage_b" || { echo 'Q2 uImage reproducibility mismatch' >&2; exit 6; }
python3 "$pack" "$uimage_a" "$template" "$web_a" >/dev/null
python3 "$pack" "$uimage_b" "$template" "$web_b" >/dev/null
cmp -s "$web_a" "$web_b" || { echo 'Q2 webformat reproducibility mismatch' >&2; exit 6; }

cp "$lzma_a" "$lzma"
cp "$uimage_a" "$uimage"
cp "$web_a" "$web"
cp "$web" "$tftp"
cp "$out_a/.config" "$build/$base.config"
cp "$out_a/vmlinux" "$build/$base.vmlinux"
cp "$out_a/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb" "$build/$base.dtb"
cp "$init_a" "$build/$base.initramfs.cpio"
mkimage -l "$uimage" >"$build/$base.mkimage.txt"

python3 - "$contract_tool" "$web" "$build/bootbase-contract.json" <<'PY'
import importlib.util, json, pathlib, sys
tool, image, output = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bootbase_contract", tool)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.validate_bootbase_slot("q2-integrated-lzma", image.read_bytes(), module.PARTITIONS["linux_live"][1])
report = module.image_to_dict(result)
report["candidate_eligible"] = False
report["scope_note"] = "Q2 format/CRC/LZMA/slot guard only; exact-image RAM boot pending"
output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not result.accepted_by_contract:
    raise SystemExit("Q2 candidate rejected by Bootbase contract")
PY

python3 - "$q1_rootfs" "$q1_uimage" "$q1_web" "$q1_lzma_web" \
	"$rootfs_manifest" "$w4_integration" "$raw" "$lzma" "$uncompressed_uimage" \
	"$uimage" "$web" "$tftp" "$build/bootbase-contract.json" \
	"$build/manifest.json" "$build/ram-layout.json" "$slot_bytes" \
	"$staging_start" "$ddr_end" <<'PY'
from pathlib import Path
import hashlib, json, lzma, struct, sys

(q1_rootfs, q1_uimage, q1_web, q1_lzma_web, rootfs_manifest, w4_integration,
 raw_path, lzma_path, source_uimage, uimage_path, web_path, tftp_path,
 contract_path, manifest_path, layout_path) = map(Path, sys.argv[1:16])
slot = int(sys.argv[16])
staging_start = int(sys.argv[17], 0)
ddr_end = int(sys.argv[18], 0)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def info(path): return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}

source = source_uimage.read_bytes()
raw = raw_path.read_bytes()
encoded = lzma_path.read_bytes()
uimage = uimage_path.read_bytes()
web = web_path.read_bytes()
src = struct.unpack(">7I4B32s", source[:64])
out = struct.unpack(">7I4B32s", uimage[:64])
contract = json.loads(contract_path.read_text(encoding="utf-8"))
rootmeta = json.loads(rootfs_manifest.read_text(encoding="utf-8"))
if source[64:] != raw or lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
    raise SystemExit("Q2 LZMA exact payload binding failed")
if out[4:6] != src[4:6] or out[10] != 3:
    raise SystemExit("Q2 LZMA load/entry/compression mismatch")
if tftp_path.read_bytes() != web or len(web) > slot or not contract["accepted_by_contract"]:
    raise SystemExit("Q2 TFTP/slot/Bootbase contract failed")

load_start = out[4]
load_end = load_start + len(raw)
entry = out[5]
staging_end = staging_start + len(web)
props = encoded[0]
lc = props % 9
rest = props // 9
lp = rest % 5
pb = rest // 5
probability_bytes = (1846 + (768 << (lc + lp))) * 2
probability_start = (load_end + 0x80) & ~0x7f
probability_end = probability_start + probability_bytes
safe = staging_end < load_start and load_start <= entry < load_end and probability_end < ddr_end
layout = {
    "schema": "openmitrastar.q2-lzma-ram-layout/v1",
    "staging": {"start": f"0x{staging_start:08x}", "end": f"0x{staging_end:08x}"},
    "decompressed_image": {"start": f"0x{load_start:08x}", "end": f"0x{load_end:08x}", "bytes": len(raw), "entry": f"0x{entry:08x}"},
    "lzma_probability_workspace": {"start": f"0x{probability_start:08x}", "end": f"0x{probability_end:08x}", "bytes": probability_bytes, "lc": lc, "lp": lp, "pb": pb},
    "ddr_end": f"0x{ddr_end:08x}", "safe_offline": safe,
}
if not safe:
    raise SystemExit("Q2 RAM layout unsafe")
layout_path.write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n", encoding="utf-8")

manifest = {
    "schema": "openmitrastar.q2-integrated-lzma-candidate/v1",
    "classification": "FLASH-SIZED-Q2-LZMA-CANDIDATE-HARDWARE-PENDING-NO-FLASH",
    "candidate_eligible": False, "flash_supported": False,
    "hardware_actions": False, "network_actions": False,
    "profile": "Q2_PARITY_INTEGRATED",
    "sources": {
        "q1_dual_radio_rootfs": info(q1_rootfs), "q1_uncompressed_uimage": info(q1_uimage),
        "q1_overslot_webformat": info(q1_web), "q1_lzma_candidate": info(q1_lzma_web),
        "q2_rootfs_manifest_sha256": sha(rootfs_manifest),
        "w4_https_getinfo_integration_sha256": sha(w4_integration),
    },
    "rootfs": rootmeta,
    "artifacts": {
        "rootfs": info(Path(rootmeta["rootfs"]["file"]) if False else rootfs_manifest.parent / rootmeta["rootfs"]["file"]),
        "uncompressed_uimage": info(source_uimage), "decompressed_payload": info(raw_path),
        "lzma_payload": info(lzma_path), "uimage": info(uimage_path),
        "webformat": info(web_path), "tftp_copy": info(tftp_path),
        "bootbase_contract": info(contract_path), "ram_layout": info(layout_path),
    },
    "capabilities": rootmeta["capabilities"],
    "security": rootmeta["security"],
    "compression": {"format": "lzma-alone", "properties": encoded[:5].hex(), "declared_uncompressed_bytes": int.from_bytes(encoded[5:13], "little"), "decoded_sha256": sha(raw_path), "two_encodes_identical": True},
    "slot": {"name": "linux_live", "bytes": slot, "candidate_bytes": len(web), "spare_bytes": slot - len(web), "fits": len(web) <= slot, "bootbase_contract": "PASS"},
    "ram_layout": layout,
    "reproducibility": {"rootfs_two_builds_identical": True, "initramfs_two_builds_identical": True, "kernel_two_incremental_trees_identical": True, "lzma_two_encodes_identical": True, "webformat_two_builds_identical": True},
    "protected_q1": {"unchanged": True, "hashes": {"rootfs": sha(q1_rootfs), "uimage": sha(q1_uimage), "webformat": sha(q1_web), "lzma_webformat": sha(q1_lzma_web)}},
    "runtime_gates": {"exact_candidate_ram_boot": "pending", "ram_equivalence_180s": "pending", "https_runtime_external_pem": "pending", "backup_restore_runtime": "pending", "w3_no_ioss_hardware": "pending", "flash": "forbidden-until-new-Q2-hardware-gates"},
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

[ "$(sha "$q1_rootfs")" = "$q1_rootfs_before" ]
[ "$(sha "$q1_uimage")" = "$q1_uimage_before" ]
[ "$(sha "$q1_web")" = "$q1_web_before" ]
[ "$(sha "$q1_lzma_web")" = "$q1_lzma_before" ]

sha256sum "$rootfs" "$build/$base.initramfs.cpio" "$uncompressed_uimage" \
	"$raw" "$lzma" "$uimage" "$web" "$tftp" "$build/bootbase-contract.json" \
	"$build/ram-layout.json" "$build/manifest.json" >"$build/SHA256SUMS"

python3 "$workspace/tools/test_q2_integrated_lzma_candidate.py"
sh "$workspace/tools/test_q2_integrated_rootfs.sh"
printf 'OMQ2_INTEGRATED_LZMA_BUILD_PASS sha256=%s bytes=%s spare=%s rootfs_sha256=%s q1_unchanged=1 flash=0 hardware=0\n' \
	"$(sha "$web")" "$(wc -c <"$web")" "$((slot_bytes - $(wc -c <"$web")))" "$(sha "$rootfs")"
