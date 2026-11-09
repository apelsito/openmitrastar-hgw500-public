#!/bin/sh

# Compose the Q1 RAM-only product from the immutable OEM-parity rootfs and the
# latest independently verified 2.4/5 GHz driver bundles.  This lane never
# accepts a PSK or private MAC as a build input and never performs hardware or
# flash actions.
set +x
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base_rootfs="$workspace/work/mission-state/w4-rootfs-product/build/openmitrastar-product-rootfs-v1.squashfs"
base_manifest="$workspace/work/mission-state/w4-rootfs-product/build/manifest.json"
realtek="$workspace/outputs/kernel-port/realtek-loop/rx-rate-tx-v4-RAM-ONLY-NO-FLASH"
qtn="$workspace/outputs/kernel-port/quantenna-linux510-radiohw-rxalign-20260820"
qtn_hostapd="$workspace/outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820"
qtn_tools="$workspace/outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820"
power="$workspace/outputs/radio-driver-kit-0.7/payload/etc/power_tables"
core="$workspace/work/mission-state/w5-product-ram-candidate/scripts/build_product_ram_candidate.sh"
base_config="$workspace/work/mission-state/f5-foundation-nowdt/build/openmitrastar-f5-foundation-nowdt-v1.config"
lane="$workspace/work/mission-state/q1-full-product"
build="$lane/build"
rootfs_build="$lane/rootfs-build"
stage_a=${OM_Q1_STAGE_A:-/home/user/openmitrastar-build/q1-full-product/rootfs-a}
stage_b=${OM_Q1_STAGE_B:-/home/user/openmitrastar-build/q1-full-product/rootfs-b}
derived_a="$rootfs_build/openmitrastar-q1-full-product-rootfs-v1-a.squashfs"
derived_b="$rootfs_build/openmitrastar-q1-full-product-rootfs-v1-b.squashfs"
derived="$rootfs_build/openmitrastar-q1-full-product-rootfs-v1.squashfs"
derived_manifest="$rootfs_build/manifest.json"
artifact_dir="$build"
build_root=${OM_Q1_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/q1-full-product/kernel}
base=openmitrastar-linux510-q1-full-product-v1-RAM-ONLY
tftp="$workspace/work/tftp/omvl/linux510-q1-full-product-v1-RAM-ONLY-NO-FLASH.bin"
release=5.10.260-openmitrastar-radiohw
epoch=${SOURCE_DATE_EPOCH:-1787011200}

base_rootfs_sha=5d0536fa7917f47b0fe4f70ac90699dcb194f9ff3c98c4d9738531c0c6c404fa
realtek_manifest_sha=c210392680a374e6b170456533141a8d1bc87a25042adbac6a7b178ea9fcb8e9
qtn_manifest_sha=6f5b86911e45a08934049305589bdfb0cff488012936f162b9c826f4adddfca7
qtn_overlay_sha=88a39ac90d99485816e6acd41ba74cde90f380ce2fc7651359f2b91d7912b1a1
qdrv_sha=9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20
hbm_sha=c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b
hostapd_sha=338beaae1e3f3bc951b16d4bea1871d42d184170fc95f5efd200aa46e45dc269
hostapd_cli_sha=67df5a9d7e6484101ac29f25c8f178cdea2bef51d4ea3f6fcdeeebb9eb033504
iwconfig_sha=5ebc31cb2ca69a1fbe1e0882f4aadba248e131a3b153c1d86d210ba53890c18b
iwpriv_sha=94c0d675a2d18fd0c259eb713e6a69d99fe6b2f73f2f838dc2fca2c2bf5f4edd

sha() { sha256sum "$1" | awk '{print $1}'; }
require_sha() {
	path=$1 expected=$2
	[ -f "$path" ] || { echo "missing Q1 input: $path" >&2; exit 3; }
	actual=$(sha "$path")
	[ "$actual" = "$expected" ] || {
		printf 'Q1 input hash mismatch: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
		exit 3
	}
}

for required in "$base_manifest" "$core" "$base_config" \
	"$realtek/manifest.json" "$realtek/LOAD_ORDER.txt" \
	"$qtn/module-manifest.tsv" "$qtn/quantenna-rootfs-overlay.tar.gz" \
	"$power/power_table.conf" "$power/tx_power_QSR1000_es.txt"; do
	[ -f "$required" ] || { echo "missing Q1 input: $required" >&2; exit 3; }
done
require_sha "$base_rootfs" "$base_rootfs_sha"
require_sha "$realtek/manifest.json" "$realtek_manifest_sha"
require_sha "$qtn/module-manifest.tsv" "$qtn_manifest_sha"
require_sha "$qtn/quantenna-rootfs-overlay.tar.gz" "$qtn_overlay_sha"
require_sha "$qtn/rootfs/lib/modules/$release/extra/quantenna/qdrv/qdrv.ko" "$qdrv_sha"
require_sha "$qtn/rootfs/lib/modules/$release/extra/quantenna/platform/topaz/hbm.ko" "$hbm_sha"
require_sha "$qtn_hostapd/hostapd" "$hostapd_sha"
require_sha "$qtn_hostapd/hostapd_cli" "$hostapd_cli_sha"
require_sha "$qtn_tools/iwconfig" "$iwconfig_sha"
require_sha "$qtn_tools/iwpriv" "$iwpriv_sha"
(cd "$realtek" && sha256sum -c SHA256SUMS >/dev/null)
(cd "$qtn" && sha256sum -c SHA256SUMS >/dev/null)
python3 "$workspace/tools/test_qtn_qdrv_rx_stack_alignment.py" >/dev/null

python3 - "$base_manifest" "$base_rootfs_sha" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
assert m["rootfs"]["sha256"] == sys.argv[2]
assert m["runtime"]["management_ipv4"] == "192.168.1.90"
assert m["runtime"]["api"]["port"] == 80
assert m["runtime"]["psk_bundled"] is False
assert m["security"]["ssh_key_only"] is True
PY

case "$stage_a:$stage_b:$build_root" in
/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*) ;;
*) echo 'unsafe Q1 build path' >&2; exit 2 ;;
esac
rm -rf -- "$stage_a" "$stage_b" "$rootfs_build" "$artifact_dir"
mkdir -p "$rootfs_build" "$artifact_dir" "$(dirname "$stage_a")" "$(dirname "$stage_b")"

compose_stage()
{
	stage=$1
	(umask 000; unsquashfs -no-progress -d "$stage" "$base_rootfs") >/dev/null
	# Pull the post-live Q1 service-state fix even while the immutable source
	# rootfs hash remains pinned: successful module load clears S35 just as AP
	# startup clears S50. These are ordinary RAM-rootfs scripts, not secrets.
	cp "$workspace/work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-degraded-clear" \
		"$stage/usr/sbin/om-degraded-clear"
	cp "$workspace/work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-radio-modules" \
		"$stage/usr/sbin/om-radio-modules"

	# Replace, do not layer over, the complete Realtek payload.
	radio2="$stage/lib/modules/$release/openmitrastar/radio2g"
	rm -rf "$radio2"
	mkdir -p "$radio2" "$stage/lib/firmware/rtlwifi" "$stage/usr/share/openmitrastar/radio2g"
	cp "$realtek/firmware/regulatory.db" "$stage/lib/firmware/regulatory.db"
	cp "$realtek/firmware/rtlwifi/rtl8192eefw.bin" "$stage/lib/firmware/rtlwifi/rtl8192eefw.bin"
	cp "$realtek/LOAD_ORDER.txt" "$stage/usr/share/openmitrastar/radio2g/modules.order"
	for module in ctr.ko ccm.ko cmac.ko cfg80211.ko libarc4.ko mac80211.ko rtlwifi.ko btcoexist.ko rtl_pci.ko rtl8192ee.ko; do
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

	# Integrate the aligned Quantenna AP path.  scan_sta/tkip/default-AuC are
	# deliberately omitted from Q1 because the target mode is AP/videobridge.
	qbase="$stage/lib/modules/$release/openmitrastar/radio5g"
	rm -rf "$qbase"
	mkdir -p "$qbase" "$stage/usr/share/openmitrastar/radio5g" "$stage/etc/power_tables"
	for rel in \
		platform/ruby/qtn_pm_qos_compat.ko \
		platform/ruby/qtn_platform_support.ko \
		platform/ruby/board_compat.ko \
		platform/ruby/runtime_compat.ko \
		platform/ruby/iputil.ko platform/ruby/dmautil.ko \
		platform/topaz/switch_vlan.ko platform/topaz/fwt_if.ko \
		platform/topaz/hbm.ko platform/topaz/topaz_congest_queue.ko \
		platform/ruby/emac_lib.ko platform/topaz/dpi.ko \
		platform/topaz/switch_tqe.ko platform/fwt/fwt_ctrl.ko \
		platform/topaz/switch_emac.ko platform/ruby/gpio.ko \
		platform/qtsens/temp_sensor.ko platform/topaz/temp_sens.ko \
		wlan/wlan.ko qdrv/qdrv.ko wlan/wlan_scan_ap.ko \
		wlan/wlan_ccmp.ko wlan/wlan_xauth.ko; do
		src="$qtn/rootfs/lib/modules/$release/extra/quantenna/$rel"
		[ -f "$src" ] || { echo "missing Q1 qtn module: $rel" >&2; exit 3; }
		name=$(basename "$rel")
		cp "$src" "$qbase/$name"
		printf '%s\n' "$name" >>"$stage/usr/share/openmitrastar/radio5g/modules.order"
	done
	cp "$qtn/rootfs/lib/firmware/qtn_driver.qtn_ruby.0.bin" "$stage/lib/firmware/"
	cp "$qtn/rootfs/lib/firmware/auc_driver.nomu.0.bin" "$stage/lib/firmware/"
	cp "$qtn/rootfs/lib/firmware/rdsp_driver.0.bin" "$stage/lib/firmware/"
	cp "$qtn/rootfs/etc/qtn_regulatory_db.bin" "$stage/etc/qtn_regulatory_db.bin"
	cp "$power/power_table.conf" "$stage/etc/power_tables/power_table.conf"
	cp "$power/tx_power_QSR1000_es.txt" "$stage/etc/power_tables/tx_power_QSR1000_es.txt"
	cp "$qtn_hostapd/hostapd" "$stage/usr/sbin/hostapd-qtn"
	cp "$qtn_hostapd/hostapd_cli" "$stage/usr/sbin/hostapd-cli-qtn"
	cp "$qtn_tools/iwconfig" "$stage/usr/sbin/iwconfig-qtn"
	cp "$qtn_tools/iwpriv" "$stage/usr/sbin/iwpriv-qtn"
	cp "$qtn/module-manifest.tsv" "$stage/usr/share/openmitrastar/radio5g/module-manifest.tsv"
	{
		for file in "$qbase"/*.ko \
			"$stage/lib/firmware/qtn_driver.qtn_ruby.0.bin" \
			"$stage/lib/firmware/auc_driver.nomu.0.bin" \
			"$stage/lib/firmware/rdsp_driver.0.bin" \
			"$stage/etc/qtn_regulatory_db.bin" \
			"$stage/etc/power_tables/power_table.conf" \
			"$stage/etc/power_tables/tx_power_QSR1000_es.txt" \
			"$stage/usr/sbin/hostapd-qtn" "$stage/usr/sbin/hostapd-cli-qtn" \
			"$stage/usr/sbin/iwconfig-qtn" "$stage/usr/sbin/iwpriv-qtn"; do
			printf '%s /%s\n' "$(sha "$file")" "${file#$stage/}"
		done
	} >"$stage/usr/share/openmitrastar/radio5g/artifacts.sha256"

	cat >"$stage/usr/sbin/om-radio-credential-check" <<'EOF'
#!/bin/ash
set -u
band=${1:-}
case "$band" in
2g) candidates='/run/openmitrastar/secrets/wpa2.psk /persist/openmitrastar/wifi/wpa2.psk' ;;
5g) candidates='/run/openmitrastar/secrets/wpa2-5g.psk /persist/openmitrastar/wifi/wpa2-5g.psk' ;;
*) exit 2 ;;
esac
for file in $candidates; do [ -r "$file" ] && break; file=; done
[ -n "${file:-}" ] || { echo "OMRADIO_CREDENTIAL_REFUSED band=$band reason=no-psk" >&2; exit 1; }
[ "$(ls -ld "$file" 2>/dev/null | awk 'NR==1 {print $1}')" = -rw------- ] || { echo "OMRADIO_CREDENTIAL_REFUSED band=$band reason=psk-mode" >&2; exit 1; }
[ "$(awk 'END {print NR}' "$file" 2>/dev/null)" = 1 ] || { echo "OMRADIO_CREDENTIAL_REFUSED band=$band reason=psk-lines" >&2; exit 1; }
IFS= read -r secret <"$file" || exit 1
case "$secret" in ''|*[!A-Za-z0-9_.-]*) unset secret; echo "OMRADIO_CREDENTIAL_REFUSED band=$band reason=psk-characters" >&2; exit 1 ;; esac
[ "${#secret}" -ge 8 ] && [ "${#secret}" -le 63 ] || { unset secret; echo "OMRADIO_CREDENTIAL_REFUSED band=$band reason=psk-length" >&2; exit 1; }
unset secret
if [ "$band" = 5g ]; then
	mac=/run/openmitrastar/secrets/qtn-mac0addr
	[ -r "$mac" ] || mac=/persist/openmitrastar/wifi/qtn-mac0addr
	[ -r "$mac" ] || { echo 'OMRADIO_CREDENTIAL_REFUSED band=5g reason=no-private-mac' >&2; exit 1; }
	[ "$(ls -ld "$mac" 2>/dev/null | awk 'NR==1 {print $1}')" = -rw------- ] || { echo 'OMRADIO_CREDENTIAL_REFUSED band=5g reason=mac-mode' >&2; exit 1; }
	grep -Eq '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' "$mac" || { echo 'OMRADIO_CREDENTIAL_REFUSED band=5g reason=mac-format' >&2; exit 1; }
fi
echo "OMRADIO_CREDENTIAL_PASS band=$band source=external"
EOF
	cat >"$stage/etc/init.d/S35-radio-modules" <<'EOF'
#!/bin/ash
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
case "${1:-start}" in
start)
	enabled=$(/usr/sbin/om-config-get RADIO2G_ENABLE 2>/dev/null || echo 0)
	[ "$enabled" = 1 ] || exit 0
	/usr/sbin/om-radio-credential-check 2g || exit 1
	exec /usr/sbin/om-radio-modules ;;
*) exit 2 ;;
esac
EOF
	cat >"$stage/usr/sbin/om-radio5-payload-verify" <<'EOF'
#!/bin/ash
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
hashes=/usr/share/openmitrastar/radio5g/artifacts.sha256
[ -r "$hashes" ] || exit 1
while read -r expected path; do
	[ -n "${expected:-}" ] || continue
	[ -f "$path" ] || { echo "OMRADIO5_PAYLOAD_FAIL reason=missing path=$path" >&2; exit 1; }
	actual=$(sha256sum "$path" | awk '{print $1}')
	[ "$actual" = "$expected" ] || { echo "OMRADIO5_PAYLOAD_FAIL reason=hash path=$path" >&2; exit 1; }
done <"$hashes"
/usr/sbin/om-radio-credential-check 5g || exit 1
echo 'OMRADIO5_PAYLOAD_READY rf=blocked autostart=0 credentials=external runtime=hardware-pending'
EOF
	cat >"$stage/usr/share/openmitrastar/radio5g/runtime-contract.json" <<EOF
{
  "schema": "openmitrastar.q1-radio5g-runtime/v1",
  "artifact": "quantenna-linux510-radiohw-rxalign-20260820",
  "qdrv_sha256": "$qdrv_sha",
  "hbm_sha256": "$hbm_sha",
  "module_manifest_sha256": "$qtn_manifest_sha",
  "country": "ES",
  "channel": 36,
  "bandwidth_mhz": 80,
  "psk_source": "external-mode-0600",
  "private_mac_source": "external-mode-0600",
  "autostart": false,
  "rf_default": "blocked",
  "hardware_validation": "pending"
}
EOF
	chmod 0755 "$stage/usr/sbin/om-radio-credential-check" \
		"$stage/usr/sbin/om-radio5-payload-verify" "$stage/etc/init.d/S35-radio-modules" \
		"$stage/usr/sbin/hostapd-qtn" "$stage/usr/sbin/hostapd-cli-qtn" \
		"$stage/usr/sbin/iwconfig-qtn" "$stage/usr/sbin/iwpriv-qtn"
	chmod 0644 "$stage/usr/share/openmitrastar/radio5g"/* \
		"$stage/usr/share/openmitrastar/radio2g/bundle-manifest.json" \
		"$qbase"/*.ko "$stage/lib/firmware/qtn_driver.qtn_ruby.0.bin" \
		"$stage/lib/firmware/auc_driver.nomu.0.bin" "$stage/lib/firmware/rdsp_driver.0.bin" \
		"$stage/etc/qtn_regulatory_db.bin" "$stage/etc/power_tables"/*
	find "$stage" -exec touch -h -d "@$epoch" {} +
}

compose_stage "$stage_a"
compose_stage "$stage_b"

mksquashfs "$stage_a" "$derived_a" -comp gzip -b 131072 -all-root -noappend \
	-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
mksquashfs "$stage_b" "$derived_b" -comp gzip -b 131072 -all-root -noappend \
	-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
cmp -s "$derived_a" "$derived_b" || { echo 'Q1 derived rootfs reproducibility mismatch' >&2; exit 5; }
cp "$derived_a" "$derived"

derived_sha=$(sha "$derived")
derived_bytes=$(wc -c <"$derived")
power_table_sha=$(sha "$power/tx_power_QSR1000_es.txt")
power_conf_sha=$(sha "$power/power_table.conf")
cat >"$derived_manifest" <<EOF
{
  "schema": "openmitrastar.q1-full-product-rootfs/v1",
  "classification": "OFFLINE-Q1-FULL-PRODUCT-INTEGRATION-NO-FLASH",
  "candidate_eligible": false,
  "hardware_actions": false,
  "network_actions": false,
  "flash_supported": false,
  "persistent_writes_default": false,
  "rootfs": {"file": "$(basename "$derived")", "format": "squashfs", "size": $derived_bytes, "sha256": "$derived_sha"},
  "base_rootfs": {"sha256": "$base_rootfs_sha", "manifest_sha256": "$(sha "$base_manifest")"},
  "target": {"architecture": "ARC700", "kernel_release": "$release", "profile": "Q1_FULL_PRODUCT"},
  "components": {
    "realtek_v4_manifest_sha256": "$realtek_manifest_sha",
    "rtl8192ee_sha256": "$(sha "$realtek/modules/rtl8192ee.ko")",
    "quantenna_module_manifest_sha256": "$qtn_manifest_sha",
    "quantenna_overlay_sha256": "$qtn_overlay_sha",
    "qdrv_sha256": "$qdrv_sha",
    "hbm_sha256": "$hbm_sha",
    "hostapd_qtn_sha256": "$hostapd_sha",
    "hostapd_cli_qtn_sha256": "$hostapd_cli_sha",
    "iwconfig_qtn_sha256": "$iwconfig_sha",
    "iwpriv_qtn_sha256": "$iwpriv_sha",
    "power_table_sha256": "$power_table_sha",
    "power_table_conf_sha256": "$power_conf_sha"
  },
  "runtime": {
    "management_ipv4": "192.168.1.90",
    "management_port": 80,
    "recovery_ipv4": "192.168.1.200",
    "bridge": "br0",
    "radio2g_payload_integrated": true,
    "radio5g_payload_integrated": true,
    "radio2g_autostart_requires_external_psk": true,
    "radio5g_autostart": false,
    "radio5g_rf_default": "blocked",
    "radio5g_runtime_hardware_validation": "pending",
    "psk_bundled": false
  },
  "security": {
    "ssh_key_only": true,
    "psk_bundled": false,
    "private_mac_bundled": false,
    "secret_value_recorded": false,
    "watchdog_enabled": false,
    "missing_credentials_fail_closed": true
  }
}
EOF

# The existing reproducible kernel packager is reused with the foundation
# no-watchdog config and the derived rootfs.  No private-build variables are
# accepted by this lane.
unset OM_PRODUCT_PRIVATE_BUILD OM_PRODUCT_PRIVATE_PSK OM_PRODUCT_WDT_FRAGMENT || true
OM_PRODUCT_RAM_ARTIFACT_DIR="$artifact_dir" \
OM_PRODUCT_RAM_BASENAME="$base" \
OM_PRODUCT_TFTP_OUTPUT="$tftp" \
OM_PRODUCT_RAM_BUILD_ROOT="$build_root" \
OM_PRODUCT_ROOTFS_IMAGE="$derived" \
OM_PRODUCT_ROOTFS_MANIFEST="$derived_manifest" \
OM_PRODUCT_KERNEL_CONFIG="$base_config" \
sh "$core" || core_rc=$?
core_rc=${core_rc:-0}
if [ "$core_rc" -ne 0 ]; then
	# The full dual-radio image is intentionally larger than linux_live.  It is
	# still a valid RAM-only experiment when CRCs pass and the only rejected
	# flash-slot condition is the measured size.  Any other core failure stops.
	python3 - "$artifact_dir/bootbase-contract.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
errors = report.get("errors", [])
if report.get("accepted_by_contract") is not False or len(errors) != 1 or not errors[0].startswith("RAS payload exceeds slot:"):
    raise SystemExit("Q1 core failed for a reason other than the expected RAM-only overslot boundary")
if report.get("header", {}).get("calculated_hcrc") != report.get("header", {}).get("hcrc"):
    raise SystemExit("Q1 RAM-only header CRC mismatch")
if report.get("header", {}).get("calculated_ras_payload_dcrc") != report.get("header", {}).get("dcrc"):
    raise SystemExit("Q1 RAM-only data CRC mismatch")
PY
fi

for suffix in initramfs.cpio config vmlinux uImage dtb webformat.bin; do
	[ -f "$artifact_dir/$base.$suffix" ] || { echo "Q1 core output missing: $suffix" >&2; exit 6; }
done
[ -f "$tftp" ] || { echo 'Q1 TFTP copy missing' >&2; exit 6; }
sha256sum "$artifact_dir/$base.initramfs.cpio" "$artifact_dir/$base.config" \
	"$artifact_dir/$base.vmlinux" "$artifact_dir/$base.uImage" \
	"$artifact_dir/$base.dtb" "$artifact_dir/$base.webformat.bin" "$tftp" \
	>"$artifact_dir/SHA256SUMS"

python3 - "$artifact_dir/manifest.json" "$derived_manifest" <<'PY'
import hashlib, json, pathlib, sys
candidate_path, rootfs_path = map(pathlib.Path, sys.argv[1:])
rootfs = json.loads(rootfs_path.read_text(encoding="utf-8"))
build = candidate_path.parent
base = "openmitrastar-linux510-q1-full-product-v1-RAM-ONLY"
def info(path):
    path = pathlib.Path(path)
    return {"file": path.name, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
if candidate_path.exists():
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
else:
    candidate = {
        "artifacts": {
            "initramfs": info(build / f"{base}.initramfs.cpio"),
            "config": info(build / f"{base}.config"),
            "vmlinux": info(build / f"{base}.vmlinux"),
            "uimage": info(build / f"{base}.uImage"),
            "dtb": info(build / f"{base}.dtb"),
            "webformat": info(build / f"{base}.webformat.bin"),
        },
        "kernel_release": "5.10.260-openmitrastar-radiohw",
        "kernel_integration_gates": {
            "posix_timers": True,
            "product_watchdog_canary": False,
            "reproducible_two_isolated_builds": True,
        },
        "security": {"ssh_key_only": True, "psk_bundled": False},
    }
contract = json.loads((build / "bootbase-contract.json").read_text(encoding="utf-8"))
image_size = candidate["artifacts"]["webformat"]["bytes"]
staging_start = 0x83000000
staging_end = staging_start + image_size
load_start = int(contract["header"]["load"], 16)
load_end = load_start + int(contract["header"]["payload_size"])
if staging_end >= load_start or load_end >= 0x88000000:
    raise SystemExit("Q1 RAM staging/load ranges are not disjoint inside DDR")
candidate.update({
    "schema": "openmitrastar.q1-full-product-ram-candidate/v1",
    "classification": "RAM-ONLY-Q1-FULL-PRODUCT-CANDIDATE-NO-FLASH",
    "profile": "Q1_FULL_PRODUCT",
    "scope": "OEM-PARITY-INTEGRATION",
    "candidate_eligible": False,
    "flash_supported": False,
    "private_build": False,
    "components": rootfs["components"],
    "base_rootfs": rootfs["base_rootfs"],
    "capabilities": {
        "management_ipv4": "192.168.1.90",
        "cgi_management_port": 80,
        "ssh_key_only": True,
        "realtek_v4_payload_integrated": True,
        "quantenna_rxalign_payload_integrated": True,
        "radio2g_hardware_pass": False,
        "radio5g_hardware_pass": False,
        "both_radios_fail_closed_without_credentials": True,
        "watchdog_enabled": False,
    },
    "security": {
        "ssh_key_only": True,
        "psk_bundled": False,
        "private_mac_bundled": False,
        "secret_value_recorded": False,
        "missing_credentials_fail_closed": True,
        "watchdog_enabled": False,
    },
    "completion_claims": {
        "full_product": False,
        "oem_parity_100": False,
        "radio2g": False,
        "radio5g": False,
    },
    "ram_only_layout": {
        "staging_start": f"0x{staging_start:08x}",
        "staging_end": f"0x{staging_end:08x}",
        "load_start": f"0x{load_start:08x}",
        "load_end": f"0x{load_end:08x}",
        "ddr_end": "0x88000000",
        "ranges_disjoint": True,
        "uimage_header_crc": "PASS",
        "uimage_data_crc": "PASS",
        "linux_live_slot_fit": False,
    },
    "runtime_gates": {
        **candidate.get("runtime_gates", {}),
        "exact_candidate_ram_boot": "pending",
        "radio2g_association_traffic_soak": "pending",
        "radio5g_association_traffic_soak": "pending",
        "oem_cgi_hardware_smoke": "pending",
        "flash": "forbidden-by-classification",
    },
})
candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

python3 "$workspace/tools/test_q1_full_product_candidate.py"
printf 'OMQ1_FULL_PRODUCT_BUILD_PASS sha256=%s bytes=%s rootfs_sha256=%s flash=0 secrets=0 watchdog=0\n' \
	"$(sha "$artifact_dir/$base.webformat.bin")" \
	"$(wc -c <"$artifact_dir/$base.webformat.bin")" "$derived_sha"
