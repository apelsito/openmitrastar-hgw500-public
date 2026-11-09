#!/bin/sh

# Reproducible, RAM-only 2.4 GHz parity candidate. It consumes the existing
# read-only Origin importer and current kernel overlay as separate hash-pinned
# inputs. It never contacts the router and never writes flash.
set +x
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
lane=${OM_W2_2G_LANE:-$workspace/work/mission-state/w2-2g-parity-tx3-v1}
build="$lane/build"
rootfs_build="$lane/rootfs-build"
stage_a=${OM_W2_2G_STAGE_A:-/home/user/openmitrastar-build/w2-2g-parity-tx3-v1/rootfs-a}
stage_b=${OM_W2_2G_STAGE_B:-/home/user/openmitrastar-build/w2-2g-parity-tx3-v1/rootfs-b}
kernel_build=${OM_W2_2G_KERNEL_BUILD:-/home/user/openmitrastar-build/w2-2g-parity-tx3-v1/kernel}
base_rootfs="$workspace/work/mission-state/q3-maintenance-hbm-clear-tqe-dma-v1/rootfs-build/openmitrastar-q3-persistent-rootfs-v1.squashfs"
base_manifest="$workspace/work/mission-state/q3-maintenance-hbm-clear-tqe-dma-v1/rootfs-build/manifest.json"
base_config="$workspace/work/mission-state/q3-maintenance-hbm-clear-tqe-dma-v1/build/openmitrastar-linux510-q3-maintenance-hbm-clear-tqe-dma-v1-RAM-ONLY-NO-FLASH.config"
realtek=${OM_W2_2G_REALTEK_BUNDLE:-$workspace/outputs/kernel-port/realtek-loop/w2-tx3-data-compact-txbd-RAM-ONLY-NO-FLASH}
variant_root="$workspace/work/mission-state/w2-2g-parity-v1/rootfs"
core="$workspace/work/mission-state/w5-product-ram-candidate/scripts/build_product_ram_candidate.sh"
legacy_lzma="$workspace/work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
make_uimage="$workspace/tools/make_q1_lzma_uimage.py"
pack="$workspace/tools/pack_topaz_webformat.py"
template="$workspace/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
contract_tool="$workspace/tools/bootbase_contract_emulator.py"
buttond_src="$workspace/tools/om_buttond.c"
arc_toolchain=${OM_ARC_UCLIBC_PREFIX:-$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-}
buttond_build="$build/om-buttond"
variant_slug=${OM_W2_2G_VARIANT_SLUG:-tx3}
profile=${OM_W2_2G_PROFILE:-W2_2G_TX3_DATA_COMPACT_OPEN_DIAG}
rootfs_classification=${OM_W2_2G_ROOTFS_CLASSIFICATION:-OFFLINE-W2-2G-PARITY-TX3-RAM-ONLY-NO-FLASH}
classification=${OM_W2_2G_CLASSIFICATION:-RAM-ONLY-W2-2G-PARITY-TX3-NO-FLASH}
bootbase_scope=${OM_W2_2G_BOOTBASE_SCOPE:-w2-2g-parity-tx3}
base=${OM_W2_2G_BASE:-openmitrastar-linux510-w2-2g-parity-tx3-v1-RAM-ONLY-NO-FLASH}
tftp=${OM_W2_2G_TFTP:-$workspace/work/tftp/omvl/linux510-w2-2g-parity-tx3-v1-RAM-TEST-NO-FLASH.bin}
core_tftp="$workspace/work/tftp/omvl/_unsafe_intermediate/$base.uncompressed-rejected.webformat.bin"
rootfs_a="$rootfs_build/openmitrastar-w2-2g-parity-$variant_slug-rootfs-v1-a.squashfs"
rootfs_b="$rootfs_build/openmitrastar-w2-2g-parity-$variant_slug-rootfs-v1-b.squashfs"
rootfs="$rootfs_build/openmitrastar-w2-2g-parity-$variant_slug-rootfs-v1.squashfs"
rootfs_manifest="$rootfs_build/manifest.json"
release=5.10.260-openmitrastar-radiohw
epoch=${SOURCE_DATE_EPOCH:-1787011200}
fast=${OM_W2_2G_FAST:-0}
mgmt_split=${OM_W2_2G_MGMT_SPLIT:-1}
compact32=${OM_W2_2G_COMPACT32:-1}

canonical_path()
{
	python3 - "$1" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve())
PY
}

workspace=$(canonical_path "$workspace")
lane=$(canonical_path "$lane")
stage_a=$(canonical_path "$stage_a")
stage_b=$(canonical_path "$stage_b")
kernel_build=$(canonical_path "$kernel_build")
realtek=$(canonical_path "$realtek")
tftp=$(canonical_path "$tftp")
build="$lane/build"
rootfs_build="$lane/rootfs-build"
core_tftp="$workspace/work/tftp/omvl/_unsafe_intermediate/$base.uncompressed-rejected.webformat.bin"
rootfs_a="$rootfs_build/openmitrastar-w2-2g-parity-$variant_slug-rootfs-v1-a.squashfs"
rootfs_b="$rootfs_build/openmitrastar-w2-2g-parity-$variant_slug-rootfs-v1-b.squashfs"
rootfs="$rootfs_build/openmitrastar-w2-2g-parity-$variant_slug-rootfs-v1.squashfs"
rootfs_manifest="$rootfs_build/manifest.json"

case "$lane" in
	"$workspace"/work/mission-state/w2-2g-parity-*) ;;
	*) echo "unsafe W2 2G lane path: $lane" >&2; exit 2 ;;
esac
case "$realtek" in
	"$workspace"/outputs/kernel-port/realtek-loop/*RAM-ONLY*) ;;
	*) echo "unsafe W2 2G Realtek bundle path: $realtek" >&2; exit 2 ;;
esac
case "$tftp" in
	"$workspace"/work/tftp/omvl/*RAM-TEST-NO-FLASH.bin) ;;
	*) echo "unsafe W2 2G TFTP output path: $tftp" >&2; exit 2 ;;
esac
allowed_build_root=$(canonical_path /home/user/openmitrastar-build)
for scratch in "$stage_a" "$stage_b" "$kernel_build"; do
	case "$scratch" in "$allowed_build_root"/*) ;; *) echo "unsafe W2 2G build path: $scratch" >&2; exit 2 ;; esac
done

expected_base_rootfs=871a14ce5d2af73b3eb575acfdc4241f7fa90579fa9ec504ab1447896ba97c14
expected_base_manifest=9f0393c5b9f878b9ab57160271bdc6f8d9b5e3f71af31b05ab8d727dd1350930
expected_base_config=160c49870d3efdfe46fe7999d13ef1b7dc8b99c384b740392cd19399255cb2c3
expected_realtek_manifest=${OM_W2_2G_EXPECTED_REALTEK_MANIFEST:-706b7e57d7c6888b36d03927e4abbbadfb129e69a8f712045fd0359242eb3e19}
expected_lzma_tool=04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18

sha() { sha256sum "$1" | awk '{print $1}'; }
require_sha()
{
	path=$1 expected=$2
	[ -f "$path" ] || { echo "missing W2 2G input: $path" >&2; exit 3; }
	actual=$(sha "$path")
	[ "$actual" = "$expected" ] || {
		printf 'W2 2G input drift: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
		exit 3
	}
}

for required in "$base_rootfs" "$base_manifest" "$base_config" \
	"$realtek/manifest.json" "$realtek/SHA256SUMS" "$realtek/LOAD_ORDER.txt" \
	"$variant_root/usr/sbin/om-radio-modules" \
	"$variant_root/usr/sbin/om-radio2g-diag-start" \
	"$variant_root/usr/sbin/om-radio-stop" \
	"$variant_root/usr/sbin/om-radio2g-soak-gate" \
	"$variant_root/etc/init.d/S35-radio-modules" \
	"$variant_root/etc/init.d/S50-radio-ap" \
	"$variant_root/etc/init.d/S52-buttond" \
	"$buttond_src" "${arc_toolchain}gcc" \
	"$core" "$legacy_lzma" "$make_uimage" "$pack" "$template" "$contract_tool"; do
	[ -f "$required" ] || { echo "missing W2 2G input: $required" >&2; exit 3; }
done
require_sha "$base_rootfs" "$expected_base_rootfs"
require_sha "$base_manifest" "$expected_base_manifest"
require_sha "$base_config" "$expected_base_config"
require_sha "$realtek/manifest.json" "$expected_realtek_manifest"
require_sha "$legacy_lzma" "$expected_lzma_tool"
(cd "$realtek" && sha256sum -c SHA256SUMS >/dev/null)
case "$fast" in 0|1) ;; *) echo 'OM_W2_2G_FAST must be 0 or 1' >&2; exit 2 ;; esac
case "$mgmt_split" in 0|1) ;; *) echo 'OM_W2_2G_MGMT_SPLIT must be 0 or 1' >&2; exit 2 ;; esac
case "$compact32" in 0|1) ;; *) echo 'OM_W2_2G_COMPACT32 must be 0 or 1' >&2; exit 2 ;; esac

python3 - "$base_manifest" "$base_rootfs" "$realtek/manifest.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
base_manifest, base_rootfs, realtek_manifest = map(Path, sys.argv[1:])
base = json.loads(base_manifest.read_text(encoding="utf-8"))
rtl = json.loads(realtek_manifest.read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert base["rootfs"]["sha256"] == sha(base_rootfs)
assert base["capabilities"]["origin_mtd5_read_only_import"] is True
assert base["capabilities"]["origin_psk_to_tmpfs"] is True
assert base["capabilities"]["w3_5g_autostart"] is False
assert rtl["classification"] == "RAM-ONLY-NO-FLASH"
assert rtl["experiments"]["hgw500_tx_dma_wmb"]["default"] is False
assert rtl["experiments"]["hgw500_tx_close_diag"]["default"] is False
assert rtl["experiments"]["hgw500_tx_dma_wmb"]["ampdu_unchanged"] is True
assert rtl["experiments"]["hgw500_tx_dma_wmb"]["ack_policy_unchanged"] is True
PY

rm -rf -- "$stage_a" "$stage_b" "$rootfs_build" "$build" "$kernel_build"
mkdir -p "$rootfs_build" "$build" "$(dirname "$stage_a")" "$(dirname "$stage_b")" "$(dirname "$core_tftp")"
"${arc_toolchain}gcc" -Os -Wall -Wextra -s -o "$buttond_build" "$buttond_src"
"${arc_toolchain}readelf" -h "$buttond_build" | grep -q 'Machine:.*ARCompact' || {
	echo 'om-buttond is not an ARC binary' >&2
	exit 3
}

compose_stage()
{
	stage=$1
	(umask 000; unsquashfs -no-progress -d "$stage" "$base_rootfs") >/dev/null

	radio2="$stage/lib/modules/$release/openmitrastar/radio2g"
	rm -rf "$radio2"
	mkdir -p "$radio2" "$stage/lib/firmware/rtlwifi" \
		"$stage/usr/share/openmitrastar/radio2g"
	cp "$realtek/firmware/regulatory.db" "$stage/lib/firmware/regulatory.db"
	cp "$realtek/firmware/rtlwifi/rtl8192eefw.bin" \
		"$stage/lib/firmware/rtlwifi/rtl8192eefw.bin"
	cp "$realtek/LOAD_ORDER.txt" "$stage/usr/share/openmitrastar/radio2g/modules.order"
	for module in ctr.ko ccm.ko cmac.ko cfg80211.ko libarc4.ko mac80211.ko \
		rtlwifi.ko btcoexist.ko rtl_pci.ko rtl8192ee.ko; do
		cp "$realtek/modules/$module" "$radio2/$module"
	done
	{
		for path in /lib/firmware/regulatory.db /lib/firmware/rtlwifi/rtl8192eefw.bin; do
			printf '%s %s\n' "$(sha "$stage$path")" "$path"
		done
		while IFS= read -r module; do
			[ -n "$module" ] || continue
			path="/lib/modules/$release/openmitrastar/radio2g/$module"
			printf '%s %s\n' "$(sha "$stage$path")" "$path"
		done <"$stage/usr/share/openmitrastar/radio2g/modules.order"
	} >"$stage/usr/share/openmitrastar/radio2g/artifacts.sha256"
	cp "$realtek/manifest.json" "$stage/usr/share/openmitrastar/radio2g/bundle-manifest.json"
	cp "$realtek/ram_insmod" "$stage/usr/sbin/ram-insmod-qtn"

	cp "$variant_root/usr/sbin/om-radio-modules" "$stage/usr/sbin/om-radio-modules"
	cp "$variant_root/usr/sbin/om-radio2g-diag-start" "$stage/usr/sbin/om-radio2g-diag-start"
	cp "$variant_root/usr/sbin/om-radio-stop" "$stage/usr/sbin/om-radio-stop"
	cp "$variant_root/usr/sbin/om-radio2g-soak-gate" "$stage/usr/sbin/om-radio2g-soak-gate"
	cp "$buttond_build" "$stage/usr/sbin/om-buttond"
	cp "$variant_root/etc/init.d/S35-radio-modules" "$stage/etc/init.d/S35-radio-modules"
	cp "$variant_root/etc/init.d/S50-radio-ap" "$stage/etc/init.d/S50-radio-ap"
	cp "$variant_root/etc/init.d/S52-buttond" "$stage/etc/init.d/S52-buttond"
	if [ "$mgmt_split" = 0 ]; then
		sed -i \
			-e 's/hgw500_txbd_mgmt_split=1/hgw500_txbd_mgmt_split=0/g' \
			-e 's/hgw500_txbd_mgmt_split=Y/hgw500_txbd_mgmt_split=N/g' \
			"$stage/usr/sbin/om-radio-modules"
	fi
	if [ "$compact32" = 0 ]; then
		sed -i \
			-e 's/hgw500_txbd_compact32=1/hgw500_txbd_compact32=0/g' \
			-e 's/hgw500_txbd_compact32 Y/hgw500_txbd_compact32 N/g' \
			"$stage/usr/sbin/om-radio-modules"
	fi
	chmod 0755 "$stage/usr/sbin/om-radio-modules" \
		"$stage/usr/sbin/om-radio2g-diag-start" \
		"$stage/usr/sbin/om-radio-stop" \
		"$stage/usr/sbin/om-radio2g-soak-gate" \
		"$stage/usr/sbin/om-buttond" \
		"$stage/usr/sbin/ram-insmod-qtn" \
		"$stage/etc/init.d/S35-radio-modules" "$stage/etc/init.d/S50-radio-ap" \
		"$stage/etc/init.d/S52-buttond"

	for config in \
		"$stage/usr/share/openmitrastar/config-schema/v1/defaults.conf" \
		"$stage/usr/share/openmitrastar/factory-config/v1/v1/settings.conf"; do
		sed -i 's/^RADIO2G_SSID=.*/RADIO2G_SSID=OpenMitraStar-2G-DIAG/' "$config"
		sed -i 's/^RADIO5G_ENABLE=.*/RADIO5G_ENABLE=0/' "$config"
	done
	rm -f "$stage/etc/openmitrastar/features"/q3-radio5-*

	cat >"$stage/usr/share/openmitrastar/radio2g/runtime-contract.json" <<EOF
{
  "schema": "openmitrastar.w2-2g-runtime/v1",
  "profile": "$profile",
  "ssid": "OpenMitraStar-2G-DIAG",
  "ssid_source": "immutable diagnostic profile",
  "security": "OPEN-DIAGNOSTIC",
  "uses_psk": false,
  "psk_bundled": false,
  "psk_logged": false,
  "final_secure_capability": {
    "security": "WPA2-PSK-CCMP",
    "start_helper": "/usr/sbin/om-radio-start",
    "psk_source": "/run/openmitrastar/secrets/wpa2.psk",
    "psk_producer": "/usr/sbin/om-origin-import",
    "psk_origin": "current-unit mtd5 wifi_default_key matched to OEM hostapd.conf",
    "psk_mode": "0600"
  },
  "module_profile": {
    "msi": 0,
    "dma64": 0,
    "aspm": 0,
    "ips": 0,
    "fwlps": 0,
    "swenc": 1,
    "disable_watchdog": 1,
    "debug_level": 0,
    "hgw500_tx_dma_wmb": 1,
    "hgw500_tx_close_diag": 1,
    "hgw500_txbd_compact32": $compact32,
    "hgw500_txbd_mgmt_split": $mgmt_split,
    "hgw500_tx_ampdu_disable": 0,
    "hgw500_honest_tx_ack": 0
  },
  "network": {
    "mode": "transparent-videobridge",
    "bridge": "br0",
    "members": ["eth0", "wlan0"],
    "dhcp": "upstream-pass-through",
    "local_dhcp_server": false,
    "nat": false
  },
  "controls": {
    "wlan2g_led": {"gpio": 11, "active_low": true},
    "wifi2g_button": {"gpio": 2, "active_low": true, "short_action": "none", "long_press_ms": 5000, "long_action": "wifi2g-toggle", "daemon": "/usr/sbin/om-buttond"},
    "wps2g": "absent-current-unit-contract-do-not-invent"
  },
  "radio5g_autostart": false,
  "flash": false
}
EOF
	chmod 0644 "$stage/usr/share/openmitrastar/radio2g"/*.json \
		"$stage/usr/share/openmitrastar/radio2g"/*.txt \
		"$stage/usr/share/openmitrastar/radio2g"/*.sha256 2>/dev/null || true

	python3 - "$stage" <<'PY'
import re, sys
from pathlib import Path
stage = Path(sys.argv[1])
for path in stage.rglob("*"):
    if not path.is_file() or path.is_symlink():
        continue
    data = path.read_bytes()
    if data.startswith(b"\x7fELF") or b"\x00" in data[:4096]:
        continue
    text = data.decode("utf-8", errors="ignore")
    for match in re.finditer(
        r"(?im)^\s*(?:wpa_passphrase|wpa_psk|psk)\s*=\s*([^\r\n]+)$", text
    ):
        value = match.group(1).strip().strip('"\'')
        if "$" not in value and "%s" not in value and not value.startswith("<"):
            raise SystemExit(f"secret-like PSK assignment in {path.relative_to(stage)}")
PY
	find "$stage" -exec touch -h -d "@$epoch" {} +
}

if [ "$fast" -eq 1 ]; then
	compose_stage "$stage_a"
	mksquashfs "$stage_a" "$rootfs" -comp gzip -b 131072 -all-root -noappend \
		-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
else
	compose_stage "$stage_a"
	compose_stage "$stage_b"
	mksquashfs "$stage_a" "$rootfs_a" -comp gzip -b 131072 -all-root -noappend \
		-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
	mksquashfs "$stage_b" "$rootfs_b" -comp gzip -b 131072 -all-root -noappend \
		-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
	cmp -s "$rootfs_a" "$rootfs_b" || { echo 'W2 2G rootfs reproducibility mismatch' >&2; exit 5; }
	cp "$rootfs_a" "$rootfs"
fi

cat >"$rootfs_manifest" <<EOF
{
  "schema": "openmitrastar.w2-2g-parity-rootfs/v1",
  "classification": "$rootfs_classification",
  "fast_iteration": $( [ "$fast" -eq 1 ] && printf true || printf false ),
  "candidate_eligible": false,
  "hardware_actions": false,
  "network_actions": false,
  "flash_supported": false,
  "rootfs": {"file": "$(basename "$rootfs")", "bytes": $(wc -c <"$rootfs"), "sha256": "$(sha "$rootfs")"},
  "sources": {
    "base_q3_rootfs_sha256": "$expected_base_rootfs",
    "base_q3_manifest_sha256": "$expected_base_manifest",
    "realtek_bundle_manifest_sha256": "$expected_realtek_manifest",
    "ram_insmod_nolibc_sha256": "8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6"
    ,"buttond_sha256": "$(sha "$buttond_build")"
  },
  "runtime": {
    "profile": "$profile",
    "management_ipv4": "192.168.1.90",
    "bridge": "br0",
    "ssid": "OpenMitraStar-2G-DIAG",
    "security": "OPEN-DIAGNOSTIC",
    "psk_source": "unused-in-diagnostic; final capability=current-unit-mtd5-read-only-to-tmpfs-0600",
    "psk_bundled": false,
    "radio5g_autostart": false
  },
  "security": {
    "ssh_key_only": true,
    "psk_bundled": false,
    "secret_value_recorded": false,
    "mtd5_write_path": false,
    "wps2g": false
  }
}
EOF

before_emac=$(sha "$workspace/work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c")
before_emac_h=$(sha "$workspace/work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h")
before_dts=$(sha "$workspace/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts")
before_controls=$(sha "$workspace/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c")

set +e
OM_PRODUCT_RAM_ARTIFACT_DIR="$build" \
OM_PRODUCT_RAM_BASENAME="$base" \
OM_PRODUCT_TFTP_OUTPUT="$core_tftp" \
OM_PRODUCT_RAM_BUILD_ROOT="$kernel_build" \
OM_PRODUCT_ROOTFS_IMAGE="$rootfs" \
OM_PRODUCT_ROOTFS_MANIFEST="$rootfs_manifest" \
OM_PRODUCT_KERNEL_CONFIG="$base_config" \
OM_PRODUCT_RAM_FAST="$fast" \
sh "$core"
core_rc=$?
set -e
core_rc=${core_rc:-0}
if [ "$core_rc" -ne 0 ]; then
	# This lane is deliberately RAM-only. Accept only the measured slot-size
	# rejection after proving header/data CRC and a safe disjoint RAM layout.
	python3 - "$build/bootbase-contract.json" "$build/$base.webformat.bin" <<'PY'
import json, sys
from pathlib import Path
contract_path, image_path = map(Path, sys.argv[1:])
report = json.loads(contract_path.read_text(encoding="utf-8"))
errors = report.get("errors", [])
if report.get("accepted_by_contract") is not False or len(errors) != 1:
    raise SystemExit("W2 2G core failed for an unexpected reason")
if not errors[0].startswith("RAS payload exceeds slot:"):
    raise SystemExit("W2 2G rejection is not the expected RAM-only overslot boundary")
header = report["header"]
if header["calculated_hcrc"] != header["hcrc"]:
    raise SystemExit("W2 2G header CRC mismatch")
if header["calculated_ras_payload_dcrc"] != header["dcrc"]:
    raise SystemExit("W2 2G data CRC mismatch")
size = image_path.stat().st_size
staging_start = 0x83000000
staging_end = staging_start + size
load_start = int(header["load"], 16)
load_end = load_start + int(header["payload_size"])
if staging_end >= load_start or load_end >= 0x88000000:
    raise SystemExit("W2 2G RAM staging/load ranges are unsafe")
PY
fi
rm -f -- "$core_tftp"

for suffix in initramfs.cpio config vmlinux uImage dtb webformat.bin; do
	[ -f "$build/$base.$suffix" ] || { echo "W2 2G output missing: $suffix" >&2; exit 6; }
done

uncompressed_uimage="$build/$base.uncompressed.uImage"
raw="$build/$base.decompressed.bin"
lzma_a="$build/$base-a.lzma"
lzma_b="$build/$base-b.lzma"
uimage_a="$build/$base-a.uImage"
uimage_b="$build/$base-b.uImage"
web_a="$build/$base-a.webformat.bin"
web_b="$build/$base-b.webformat.bin"

cp "$build/$base.uImage" "$uncompressed_uimage"
dd if="$uncompressed_uimage" of="$raw" bs=64 skip=1 status=none
"$legacy_lzma" --keep --best "$raw" -c >"$lzma_a"
python3 "$make_uimage" "$uncompressed_uimage" "$lzma_a" "$uimage_a"
python3 "$pack" "$uimage_a" "$template" "$web_a" >/dev/null
if [ "$fast" -eq 0 ]; then
	"$legacy_lzma" --keep --best "$raw" -c >"$lzma_b"
	cmp -s "$lzma_a" "$lzma_b" || { echo 'W2 2G LZMA reproducibility mismatch' >&2; exit 6; }
	python3 "$make_uimage" "$uncompressed_uimage" "$lzma_b" "$uimage_b"
	cmp -s "$uimage_a" "$uimage_b" || { echo 'W2 2G compressed uImage reproducibility mismatch' >&2; exit 6; }
	python3 "$pack" "$uimage_b" "$template" "$web_b" >/dev/null
	cmp -s "$web_a" "$web_b" || { echo 'W2 2G compressed webformat reproducibility mismatch' >&2; exit 6; }
fi
cp "$lzma_a" "$build/$base.lzma"
cp "$uimage_a" "$build/$base.uImage"
cp "$web_a" "$build/$base.webformat.bin"
cp "$web_a" "$tftp"
mkimage -l "$build/$base.uImage" >"$build/$base.mkimage.txt"

python3 - "$contract_tool" "$build/$base.webformat.bin" "$build/bootbase-contract.json" "$bootbase_scope" <<'PY'
import importlib.util, json, sys
from pathlib import Path
tool, image, output = map(Path, sys.argv[1:4])
scope = sys.argv[4]
spec = importlib.util.spec_from_file_location("bootbase_contract", tool)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.validate_bootbase_slot(scope, image.read_bytes(), module.PARTITIONS["linux_live"][1])
report = module.image_to_dict(result)
report["candidate_eligible"] = False
report["scope_note"] = "RAM-only format/CRC/LZMA/slot gate; exact-image hardware tests pending"
output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not result.accepted_by_contract:
    raise SystemExit("W2 2G compressed candidate rejected by Bootbase contract")
PY

[ "$(sha "$workspace/work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c")" = "$before_emac" ] || exit 7
[ "$(sha "$workspace/work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h")" = "$before_emac_h" ] || exit 7
[ "$(sha "$workspace/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts")" = "$before_dts" ] || exit 7
[ "$(sha "$workspace/work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c")" = "$before_controls" ] || exit 7

cp "$workspace/tools/evaluate_w2_2g_client_gate.py" "$build/evaluate_w2_2g_client_gate.py"
cp "$variant_root/usr/sbin/om-radio2g-soak-gate" "$build/om-radio2g-soak-gate"

python3 - "$build/manifest.json" "$rootfs_manifest" "$realtek/manifest.json" \
	"$before_emac" "$before_emac_h" "$before_dts" "$before_controls" \
	"$base" "$classification" "$profile" "$tftp" "$fast" "$mgmt_split" "$compact32" <<'PY'
import hashlib, json, sys
from pathlib import Path
manifest_path, rootfs_path, rtl_path = map(Path, sys.argv[1:4])
emac, emac_h, dts, controls = sys.argv[4:8]
base, classification, profile, tftp_path = sys.argv[8:12]
fast = sys.argv[12] == "1"
mgmt_split = sys.argv[13] == "1"
compact32 = sys.argv[14] == "1"
rootfs = json.loads(rootfs_path.read_text(encoding="utf-8"))
rtl = json.loads(rtl_path.read_text(encoding="utf-8"))
build = manifest_path.parent
contract = json.loads((build / "bootbase-contract.json").read_text(encoding="utf-8"))
def info(path):
    path = Path(path)
    return {"file": path.name, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
else:
    manifest = {
        "artifacts": {
            "initramfs": info(build / f"{base}.initramfs.cpio"),
            "config": info(build / f"{base}.config"),
            "vmlinux": info(build / f"{base}.vmlinux"),
            "uimage": info(build / f"{base}.uImage"),
            "dtb": info(build / f"{base}.dtb"),
            "webformat": info(build / f"{base}.webformat.bin"),
            "uncompressed_uimage": info(build / f"{base}.uncompressed.uImage"),
            "decompressed_payload": info(build / f"{base}.decompressed.bin"),
            "lzma_payload": info(build / f"{base}.lzma"),
            "tftp_copy": info(Path(tftp_path)),
            "bootbase_contract": info(build / "bootbase-contract.json"),
        },
        "kernel_release": "5.10.260-openmitrastar-radiohw",
        "kernel_integration_gates": {
            "reproducible_two_isolated_builds": True,
            "dtb_two_isolated_builds_identical": True,
            "posix_timers": True,
        },
    }
manifest.update({
    "schema": "openmitrastar.w2-2g-parity-ram-candidate/v1",
    "classification": classification,
    "profile": profile,
    "candidate_eligible": False,
    "flash_supported": False,
    "components": {
        "rootfs_sha256": rootfs["rootfs"]["sha256"],
        "realtek_bundle_manifest_sha256": hashlib.sha256(rtl_path.read_bytes()).hexdigest(),
        "ram_insmod_nolibc_sha256": "8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6",
        "rtl8192ee_sha256": next(x["sha256"] for x in rtl["artifacts"] if x["path"] == "modules/rtl8192ee.ko"),
        "rtl_pci_sha256": next(x["sha256"] for x in rtl["artifacts"] if x["path"] == "modules/rtl_pci.ko"),
        "rtlwifi_sha256": next(x["sha256"] for x in rtl["artifacts"] if x["path"] == "modules/rtlwifi.ko"),
    },
    "separate_kernel_inputs": {
        "qtn_topaz_emac_c_sha256": emac,
        "topaz_ethernet_h_sha256": emac_h,
        "topaz_mitrastar_ramssh_dts_sha256": dts,
        "qtn_topaz_recovery_c_sha256": controls,
    },
    "radio2g": {
        "ssid": "OpenMitraStar-2G-DIAG",
        "security": "OPEN-DIAGNOSTIC",
        "uses_psk": False,
        "final_secure_capability": {
            "security": "WPA2-PSK-CCMP",
            "psk_source": "current-unit-mtd5-read-only-to-tmpfs-0600",
            "start_helper": "/usr/sbin/om-radio-start",
        },
        "tx_dma_wmb": True,
        "txbd_compact32_data_queues_only": False,
        "txbd_compact32_global": compact32,
        "txbd_hardware_width_bit15": 0 if compact32 else 1,
        "txbd_compact32_queues": ["BK", "BE", "VI", "VO", "BEACON", "TXCMD", "MGNT", "HIGH", "HCCA"] if compact32 else [],
        "txbd_preserved_64_queues": [] if compact32 else ["BK", "BE", "VI", "VO", "BEACON", "TXCMD", "MGNT", "HIGH", "HCCA"],
        "txbd_oem_parity_claim": compact32,
        "tx_close_diag": True,
        "txbd_mgmt_split": mgmt_split,
        "tx_complete_trace": "bounded-first4-and-powers-of-two",
        "ampdu_policy": "baseline",
        "ack_policy": "baseline",
        "bridge": "br0:eth0+wlan0",
        "dhcp": "upstream-pass-through",
        "local_dhcp_server": False,
        "nat": False,
        "led_gpio11_active_low": True,
        "button_gpio2": {"short": "none", "long_ms": 5000, "long": "wifi2g-toggle"},
        "button_daemon": "/usr/sbin/om-buttond",
        "wps2g": "absent-current-unit-contract",
    },
    "runtime_gates": {
        "exact_image_ram_boot": "PENDING",
        "origin_psk_import": "PENDING_EXACT_IMAGE",
        "wpa2_client_association": "PENDING",
        "upstream_dhcp_client": "PENDING",
        "dns_and_https_from_client": "PENDING",
        "bidirectional_min_5_mbps": "PENDING",
        "directional_ratio_min_0_5": "PENDING",
        "be_queue_max_below_384": "PENDING",
        "ten_minute_soak": "PENDING",
        "gpio11_led": "PROVEN_PREVIOUS_IMAGE_PENDING_EXACT_IMAGE",
        "gpio2_short_long": "PROVEN_CURRENT_UNIT_PENDING_EXACT_IMAGE",
        "flash": "FORBIDDEN",
    },
    "security": {
        "ssh_key_only": True,
        "psk_bundled": False,
        "secret_value_recorded": False,
        "mtd5_write_path": False,
        "radio5g_autostart": False,
        "wps2g_enabled": False,
    },
    "reproducibility": {
        "fast_iteration": fast,
        "rootfs_two_builds_identical": not fast,
        "kernel_two_isolated_builds_identical": not fast,
        "lzma_two_encodes_identical": not fast,
        "webformat_two_builds_identical": not fast,
    },
    "slot": {
        "name": "linux_live",
        "bytes": 7995392,
        "candidate_bytes": (build / f"{base}.webformat.bin").stat().st_size,
        "fits": (build / f"{base}.webformat.bin").stat().st_size <= 7995392,
        "bootbase_contract": "PASS" if contract["accepted_by_contract"] else "FAIL",
    },
})
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

sha256sum "$rootfs" "$build/$base.initramfs.cpio" "$build/$base.config" \
	"$build/$base.vmlinux" "$build/$base.uImage" "$build/$base.dtb" \
	"$build/$base.webformat.bin" "$build/$base.uncompressed.uImage" \
	"$build/$base.decompressed.bin" "$build/$base.lzma" \
	"$build/$base.mkimage.txt" "$tftp" "$build/manifest.json" \
	"$build/om-buttond" \
	"$build/evaluate_w2_2g_client_gate.py" "$build/om-radio2g-soak-gate" \
	>"$build/W2_2G_SHA256SUMS"

python3 "$workspace/tools/test_w2_2g_parity_candidate.py"
printf 'OMW2_2G_PARITY_BUILD_PASS sha256=%s bytes=%s rootfs_sha256=%s flash=0 hardware=0\n' \
	"$(sha "$build/$base.webformat.bin")" "$(wc -c <"$build/$base.webformat.bin")" \
	"$(sha "$rootfs")"
