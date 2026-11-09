#!/bin/sh

# Compose Q3 without mutating the persistent Q2/cbe904ab lane.  Q3 starts from
# the exact Q2 rootfs, applies only hash-pinned autonomous-entropy and read-only
# Origin/mtd5 files, replaces the Quantenna payload with the direct-EMAC-safe
# symbols-only bundle, and embeds the current W3 ladder behind an explicit
# autostart policy.  Kernel work is incremental from two preserved Q2 O= trees; the
# final image is encoded twice using the OEM LZMA-alone tool and must be
# byte-identical.
set +x
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
lane=${OM_Q3_LANE:-$workspace/work/mission-state/q3-persistent-composite}
build="$lane/build"
rootfs_build="$lane/rootfs-build"
stage_a=${OM_Q3_STAGE_A:-/home/user/openmitrastar-build/q3-persistent/rootfs-a}
stage_b=${OM_Q3_STAGE_B:-/home/user/openmitrastar-build/q3-persistent/rootfs-b}
origin_a=${OM_Q3_ORIGIN_STAGE_A:-/home/user/openmitrastar-build/q3-persistent/origin-a}
origin_b=${OM_Q3_ORIGIN_STAGE_B:-/home/user/openmitrastar-build/q3-persistent/origin-b}
kernel_root=${OM_Q3_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/q3-persistent/kernel}
out_a="$kernel_root/kernel-a"
out_b="$kernel_root/kernel-b"
seed_a=/home/user/openmitrastar-build/q2-integrated/kernel/kernel-a
seed_b=/home/user/openmitrastar-build/q2-integrated/kernel/kernel-b
init_a="$kernel_root/q3-rootfs-a.cpio"
init_b="$kernel_root/q3-rootfs-b.cpio"

q2_lane="$workspace/work/mission-state/q2-integrated-lzma-candidate"
q2_rootfs="$q2_lane/rootfs-build/openmitrastar-q2-parity-rootfs-v1.squashfs"
q2_config="$q2_lane/build/openmitrastar-linux510-q2-parity-v1-LZMA-OFFLINE-NO-FLASH.config"
q2_web="$workspace/work/mission-state/q2-mtd4-flash-candidate/openmitrastar-linux510-q2-parity-v1-webformat.bin"
q2_manifest="$q2_lane/build/manifest.json"

origin_artifact="$workspace/outputs/kernel-port/openmitrastar-q3-origin-mtd5-ro-20260820"
origin_rootfs="$origin_artifact/rootfs/openmitrastar-q3-origin-mtd5-ro-rootfs-v1.squashfs"
origin_manifest="$origin_artifact/manifest.json"
bootenv_artifact="$workspace/outputs/kernel-port/q3-bootenv-wifiaddr-readonly"
bootenv_manifest="$bootenv_artifact/manifest.json"
bootenv_producer="$bootenv_artifact/om-bootenv-readonly"
controls_artifact=${OM_Q3_CONTROLS_ARTIFACT:-$workspace/outputs/kernel-port/hgw500-led-controls-20260821}
controls_driver="$controls_artifact/qtn-topaz-recovery.c"
controls_dts="$controls_artifact/topaz_mitrastar_ramssh.dts"
canonical_product_rootfs="$workspace/work/mission-state/w4-rootfs-product/rootfs"
canonical_persist="$canonical_product_rootfs/usr/sbin/om-persist"
canonical_origin_import="$canonical_product_rootfs/usr/sbin/om-origin-import"
canonical_radio_start="$canonical_product_rootfs/usr/sbin/om-radio-start"
canonical_radio_modules="${OM_Q3_RADIO_MODULES_PATH:-$canonical_product_rootfs/usr/sbin/om-radio-modules}"
canonical_control_event="$canonical_product_rootfs/usr/sbin/om-control-event"
canonical_ledctl="$canonical_product_rootfs/usr/sbin/om-ledctl"
canonical_led_contract="$canonical_product_rootfs/usr/share/openmitrastar/leds/hgw500-leds.json"
canonical_radio5_toggle="$canonical_product_rootfs/usr/sbin/om-radio5g-toggle"
canonical_ipv6_policy="$canonical_product_rootfs/usr/sbin/om-ipv6-local-policy"
canonical_ipv6_init="$canonical_product_rootfs/etc/init.d/S34-ipv6-local-policy"
canonical_config_get="$canonical_product_rootfs/usr/sbin/om-config-get"
canonical_config_prepare="$canonical_product_rootfs/usr/sbin/om-config-prepare"
canonical_config_restore="$canonical_product_rootfs/usr/sbin/om-config-restore"
canonical_defaults="$canonical_product_rootfs/usr/share/openmitrastar/config-schema/v1/defaults.conf"
canonical_factory_settings="$canonical_product_rootfs/usr/share/openmitrastar/factory-config/v1/v1/settings.conf"
canonical_degraded_clear="$canonical_product_rootfs/usr/sbin/om-degraded-clear"
canonical_ready="$canonical_product_rootfs/etc/init.d/S90-ready"
canonical_radio_modules_init="$canonical_product_rootfs/etc/init.d/S35-radio-modules"
canonical_radio_ap_init="$canonical_product_rootfs/etc/init.d/S50-radio-ap"
canonical_api_status="$canonical_product_rootfs/www/api/status"
canonical_http_config="$canonical_product_rootfs/etc/minihttpd-oem.conf"
canonical_https_config="$canonical_product_rootfs/etc/minihttpd-https.conf"
canonical_cgi_stamp="$canonical_product_rootfs/usr/share/openmitrastar/cgi-overlay-v1.json"
canonical_videobridge_policy="$canonical_product_rootfs/usr/sbin/om-videobridge-policy"
canonical_videobridge_init="$canonical_product_rootfs/etc/init.d/S33-videobridge-policy"
canonical_oem_parity="$canonical_product_rootfs/etc/openmitrastar/oem-parity.conf"
realtek_product_artifact=${OM_Q3_REALTEK_PRODUCT_ARTIFACT:-$workspace/outputs/kernel-port/realtek-loop/all64-mcs7-q2-product-v1-RAM-ONLY-NO-FLASH}
factory_authorized_keys=${OM_Q3_FACTORY_AUTHORIZED_KEYS_FILE:-}
qtn_artifact="$workspace/outputs/kernel-port/quantenna-linux510-radiohw-direct-symbols-20260820"
qtn_overlay="$qtn_artifact/quantenna-rootfs-overlay.tar.gz"
qtn_manifest="$qtn_artifact/module-manifest.tsv"
qtn_sums="$qtn_artifact/SHA256SUMS"
qcsapi_runtime=${OM_Q3_QCSAPI_RUNTIME_PATH:-$workspace/outputs/kernel-port/qcsapi-5g-ap36-bw80-ram-only-20260819/runtime}
qcsapi_runtime_manifest="$qcsapi_runtime/manifest.sha256"
qcsapi_abi_report=${OM_Q3_QCSAPI_ABI_REPORT_PATH:-$workspace/outputs/kernel-port/qcsapi-5g-ap36-bw80-ram-only-20260819/abi-report.json}
radio5_artifact="$workspace/work/mission-state/q3-dual-radio-autostart/build"
radio5_overlay=${OM_Q3_RADIO5_OVERLAY_PATH:-$radio5_artifact/openmitrastar-q3-dual-radio-autostart-overlay.tar.gz}
radio5_manifest=${OM_Q3_RADIO5_MANIFEST_PATH:-$radio5_artifact/manifest.json}
canonical_radio5_start=${OM_Q3_RADIO5_START_PATH:-$workspace/work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start}
maintenance_s53=${OM_Q3_MAINTENANCE_S53_PATH:-$workspace/work/mission-state/q3-maintenance-orchestration/rootfs/etc/init.d/S53-qtn-calibration}
maintenance_s54=${OM_Q3_MAINTENANCE_S54_PATH:-$workspace/work/mission-state/q3-maintenance-orchestration/rootfs/etc/init.d/S54-qtn-mac}
expected_maintenance_s53=${OM_Q3_EXPECTED_MAINTENANCE_S53_SHA256:-23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404}
expected_maintenance_s54=${OM_Q3_EXPECTED_MAINTENANCE_S54_SHA256:-cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d}
hbm_override=${OM_Q3_HBM_OVERRIDE_PATH:-}
expected_hbm_override=${OM_Q3_EXPECTED_HBM_OVERRIDE_SHA256:-}
switch_tqe_override=${OM_Q3_SWITCH_TQE_OVERRIDE_PATH:-}
expected_switch_tqe_override=${OM_Q3_EXPECTED_SWITCH_TQE_OVERRIDE_SHA256:-}
emac_driver_override=${OM_Q3_EMAC_DRIVER_PATH:-}
expected_emac_driver_override=${OM_Q3_EXPECTED_EMAC_DRIVER_SHA256:-}
emac_header_override=${OM_Q3_EMAC_HEADER_PATH:-}
expected_emac_header_override=${OM_Q3_EXPECTED_EMAC_HEADER_SHA256:-}
gpio4_diag_overlay=${OM_Q3_GPIO4_DIAG_OVERLAY_PATH:-}
expected_gpio4_diag_overlay=${OM_Q3_EXPECTED_GPIO4_DIAG_OVERLAY_SHA256:-}
q3_profile=${OM_Q3_PROFILE:-autostart-secure}
case "$q3_profile" in autostart-secure|open-lab|open-lab-tqe512|open-lab-beacon-preflight|open-lab-beacon-lifetime) ;; *) echo "invalid Q3 profile: $q3_profile" >&2; exit 2 ;; esac
if [ -z "${OM_Q3_RADIO5_OVERLAY_PATH:-}" ]; then
	case "$q3_profile" in
	open-lab-beacon-lifetime)
		radio5_overlay="$radio5_artifact/openmitrastar-q3-dual-radio-open-lab-beacon-lifetime-overlay.tar.gz"
		;;
	esac
fi
q3_autostart=${OM_Q3_AUTOSTART:-1}
case "$q3_autostart" in 0|1) ;; *) echo 'OM_Q3_AUTOSTART must be 0 or 1' >&2; exit 2 ;; esac

w3_switch="$workspace/tools/qtn_w3_switch_emac_handoff_remote.sh"
w3_core="$workspace/tools/qtn_w3_qdrv_hostlink_core_remote.sh"
w3_vap="$workspace/tools/qtn_w3_qdrv_hostlink_vap_once_remote.sh"
w3_ap="$workspace/tools/qtn_w3_native_madwifi_open_ap.sh"
w3_rollback="$workspace/tools/qtn_w3_native_ap_rollback.sh"
w3_contract_test="$workspace/tools/test_qtn_w3_no_ioss_runtime_contract.py"

kernel_src_base=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
kernel_src=${OM_Q3_KERNEL_SOURCE_SNAPSHOT:-/home/user/openmitrastar-build/q3-persistent/linux-src}
origin_dts="$controls_dts"
tc=${OM_Q3_CROSS_COMPILE:-$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-}
template="$workspace/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
legacy_lzma="$workspace/work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
make_uimage="$workspace/tools/make_q1_lzma_uimage.py"
pack="$workspace/tools/pack_topaz_webformat.py"
contract_tool="$workspace/tools/bootbase_contract_emulator.py"

rootfs_a="$rootfs_build/openmitrastar-q3-persistent-rootfs-v1-a.squashfs"
rootfs_b="$rootfs_build/openmitrastar-q3-persistent-rootfs-v1-b.squashfs"
rootfs="$rootfs_build/openmitrastar-q3-persistent-rootfs-v1.squashfs"
rootfs_manifest="$rootfs_build/manifest.json"
base=${OM_Q3_BASE_NAME:-openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH}
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
tftp=${OM_Q3_TFTP_PATH:-$workspace/work/tftp/omvl/linux510-q3-persistent-v1-LZMA-RAM-TEST-NO-FLASH.bin}

release=5.10.260-openmitrastar-radiohw
epoch=${SOURCE_DATE_EPOCH:-1787011200}
jobs=${TOPAZ_JOBS:-12}
slot_bytes=7995392
staging_start=${OM_Q3_STAGING_START:-0x87000000}
ddr_end=0x88000000
hbm_start=0x8063c000
hbm_end=0x8490c400

expected_q2_rootfs=951b31584e0fa7ce7734ba8d772327237236b9751f452da9aad9e1ec7c59fe95
expected_q2_web=cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1
expected_origin_rootfs=5540ed30154412706eecc3510b9c7604a074ef6751f89289437695a60fdb3173
expected_origin_manifest=12e0defd6e717796bf093043dd039b2c3de0882595d1634ca985034c87fda275
expected_canonical_persist=a411323a97391c76f2d7439dd5ae99263d189151e3e0b76e79699ec0cee8af20
expected_canonical_origin_import=85cdb3d25317eddbfd973939ace81ed139f2f6e1be3a86ae8d34b4609d40d4fb
expected_canonical_radio_start=${OM_Q3_EXPECTED_RADIO_START_SHA256:-46bd158c0e0c200cc5f8adea30e962cbfe3b8a72b7defbb17d4d70aaa6c9cd97}
expected_canonical_radio_modules=${OM_Q3_EXPECTED_RADIO_MODULES_SHA256:-428a91a54a0fce4d1475219142eb91e86999edaffcd9a1e4b5b4015b6d733786}
expected_canonical_control_event=7be9fb928841ce59ef259319f51da4be952cb7cda48a9883b2a8aef33df2edb7
expected_canonical_ledctl=${OM_Q3_EXPECTED_LEDCTL_SHA256:-0df28604268964c7a99c26f831d94d4e7ae1a06bce86189b1bb97567ae711b47}
expected_canonical_led_contract=${OM_Q3_EXPECTED_LED_CONTRACT_SHA256:-b976758a86b0ce26c4a48c36d945001343d406ce4d73600d45248c0d6788462a}
expected_canonical_radio5_toggle=45951a36be4b6f649c6e92eb1f72ac2fa2d922d9b327aac712ca0814f021e45a
expected_canonical_ipv6_policy=a64b81c9eaaaaaa9ae23a9171a5b6d167fc6517b815be95b8be7a7205a86d7f8
expected_canonical_ipv6_init=a4a8e4b8855f7fa438d44ba96cdaacb6bcd55415f265ef391a3e351afbe633d0
expected_canonical_config_get=da1e1210a503182f5d3329107518a654a831824cdec102116c1e530789492dfd
expected_canonical_config_prepare=c909f0bcfcc111c11ac0a5a6767c643321e6eae8dbb4d3c4c5600c2a27cbc51f
expected_canonical_config_restore=e4a659455a21e4cdc1268633ee54e18e435b5400205f06feb67730cd4cea20fa
expected_canonical_defaults=9453b9960cf7dc0387f6138819295eb71308840ec28f526efc3ea4720c573050
expected_canonical_factory_settings=9453b9960cf7dc0387f6138819295eb71308840ec28f526efc3ea4720c573050
expected_canonical_degraded_clear=f6c5fa02f538469b5d7841e766c46c46984d830bfd316f0a2006371913e75eeb
expected_canonical_ready=492ba7cd10e7c41f4c4b8c2645678c03fae2bfdd68d98dc67f6540f0a2a44d32
expected_canonical_radio_modules_init=bc79afe8f23eab00db8864a8a0b676c072eaf4131b1320523e55f49c9615ec5d
expected_canonical_radio_ap_init=1a0bb8918139fc08f0a06d7c1153c81eb31b728fa7c450a61f9af98120921d71
expected_canonical_videobridge_policy=a77c21f1a09e0a2ceefdeccb528cf84d22bd397f6f549ba4c32c0ba107c6c5d8
expected_canonical_videobridge_init=05566ef9a29140136f06f9fedc9403211a791defb823205c72d95a393be1844f
expected_canonical_oem_parity=f4e249693eea8b567985138c09da23f7dca75ea8b663650a7ecbe3289cb03b3f
expected_canonical_api_status=538aac7b60020006dac997139fe59c237f9496ea0d0077d3dae6ca28162b986c
expected_canonical_http_config=c314f6e1a07ddb0cadfc99324ecda0eae5566583e9740444de2d892e66cdf539
expected_canonical_https_config=aaae195c5ad0bf231d0e87fbe97618e0ac64b1aa765eec087463d40ff49c67a2
expected_canonical_cgi_stamp=${OM_Q3_EXPECTED_CGI_STAMP_SHA256:-4b7557384f5e5d1b59f6600e7f2d1160772978df159b06e9e0cff46f7436545f}
expected_qtn_overlay=02bac80ba8dac2151a62fa26a8ef1c5d95b8db65fcaee927fc1e74ec82876c4b
expected_qtn_manifest=f2b2c2369d22a38aa7868ab22838a707c2121cb1528a32f84759672f4ab96eee
expected_qtn_sums=24d8cae029a3506e6bd5bb7e7814a97e2c7cebcac54cbacf271cb496038cc9a9
expected_qcsapi_runtime_manifest=${OM_Q3_EXPECTED_QCSAPI_RUNTIME_MANIFEST_SHA256:-d13cfee57c913dfcfd9bbeb003e93d9817dc13bea657160deebc9d320dae59b9}
expected_qcsapi_abi_report=${OM_Q3_EXPECTED_QCSAPI_ABI_REPORT_SHA256:-a38cca2548ab86abc2caf580dc629e5596aa3ba21ea6b48f39cdf630a0bbac91}
case "$q3_profile" in
open-lab-beacon-lifetime)
	expected_radio5_overlay=${OM_Q3_EXPECTED_RADIO5_OVERLAY_SHA256:-44c072295519644cc0635ffcff0c9684589c384e559a8d1259c496f27230f981}
	;;
*)
	expected_radio5_overlay=${OM_Q3_EXPECTED_RADIO5_OVERLAY_SHA256:-e9a6acf82384ad13e6d5e6fce3f340dceb2a1bbc70d884343b8a495fb156a522}
	;;
esac
expected_radio5_manifest=${OM_Q3_EXPECTED_RADIO5_MANIFEST_SHA256:-608a213fd5eeb4bef2f82e780200bea312a168a373dbd61b751c6c8752283f59}
expected_canonical_radio5_start=${OM_Q3_EXPECTED_RADIO5_START_SHA256:-851ee2204cd6c03b6cd630813cbf182897538ba0a70348e10b4305aded9eb3a7}
expected_radio5_s55=${OM_Q3_EXPECTED_RADIO5_S55_SHA256:-06c0efbbb951a84f4990fd9fd99dbbedfd99f19695edea7bc94385e80bc4daa2}
expected_radio5_s53=${OM_Q3_EXPECTED_RADIO5_S53_SHA256:-}
expected_qtn_cal_producer=${OM_Q3_EXPECTED_QTN_CAL_PRODUCER_SHA256:-}
expected_origin_dts=${OM_Q3_EXPECTED_CONTROLS_DTS_SHA256:-a8279d0b9d2b8a6eb38ffc85c5b190f9c3934fca620fe38b83fca535aafee0b6}
expected_controls_driver=${OM_Q3_EXPECTED_CONTROLS_DRIVER_SHA256:-1d7aee9231741fa32e6df0c3d2321b3fe65278a880e9b1a4ce85d88b8fff2e3e}
expected_bootenv_dtb=${OM_Q3_EXPECTED_CONTROLS_DTB_SHA256:-7fa81f07fb13aa0d4caf549ce0e0d9fbb82bdee5f06f437a779309a4173f6d83}
expected_bootenv_manifest=6d25f8c72cc083fa5a8b0a862d9b32dd0d81ff2c7dc69e2f3819602f80fe55ea
expected_bootenv_producer=7ae702dafca99b95fa95a0098a2662622278e10788869d70e00f61b5738fdb96
expected_map_rom=472b50706a948d09e858e0c1360ea1052adfaafc116c232daaf3946ecceff2e4
expected_physmap=2913f920a1227a27913701af878f6f67becab78c066f8c6c9ed0db2e9dfe7992
expected_w3_switch=94392cd45d4605adf42ea77351206ac83f41e188604d88a88ed14d021d75f057
expected_w3_core=1b6388607341631f55554a1230d6a9384d84808d286df2fd8862b94ce4976968
expected_w3_vap=4199b8b458d86c6599f1c267ec58b45fbee63106bd7b65b33d0e8d88d5d23354
expected_w3_ap=e4ba0b3b5dbe692ef71985d34adca6dfd88f283bf6c1b349b95b986e708e34e5
expected_w3_rollback=c6c853146bcf36f0bb39176c05b92082be1b13fc607713665155d6f23fb536c6
expected_lzma_tool=04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18

sha() { sha256sum "$1" | awk '{print $1}'; }
require_sha()
{
	path=$1 expected=$2
	[ -f "$path" ] || { echo "missing Q3 input: $path" >&2; exit 3; }
	actual=$(sha "$path")
	[ "$actual" = "$expected" ] || {
		printf 'Q3 input drift: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
		exit 3
	}
}

case "$stage_a:$stage_b:$origin_a:$origin_b:$kernel_root" in
/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*:/home/user/openmitrastar-build/*) ;;
*) echo 'unsafe Q3 build path' >&2; exit 2 ;;
esac
case "$jobs" in ''|*[!0-9]*) exit 2 ;; esac
[ "$jobs" -gt 0 ]

for required in "$q2_config" "$q2_manifest" "$origin_manifest" "$origin_dts" \
	"$controls_driver" \
	"$bootenv_manifest" "$bootenv_producer" "$qtn_manifest" \
	"$qcsapi_runtime_manifest" "$qcsapi_abi_report" \
	"$radio5_overlay" "$radio5_manifest" \
	"$canonical_radio5_start" \
	"$canonical_persist" "$canonical_origin_import" "$canonical_radio_start" \
	"$canonical_radio_modules" \
	"$canonical_control_event" "$canonical_ledctl" "$canonical_led_contract" \
	"$canonical_radio5_toggle" \
	"$canonical_ipv6_policy" "$canonical_ipv6_init" \
	"$canonical_config_get" "$canonical_config_prepare" \
	"$canonical_config_restore" "$canonical_defaults" \
	"$canonical_factory_settings" \
	"$canonical_degraded_clear" "$canonical_ready" \
	"$canonical_radio_modules_init" "$canonical_radio_ap_init" \
	"$canonical_videobridge_policy" "$canonical_videobridge_init" "$canonical_oem_parity" \
	"$canonical_api_status" "$canonical_http_config" \
	"$canonical_https_config" "$canonical_cgi_stamp" \
	"$qtn_sums" "$w3_switch" "$w3_core" "$w3_vap" "$w3_ap" \
	"$w3_rollback" "$w3_contract_test" "$kernel_src_base/Makefile" \
	"$kernel_src_base/scripts/config" "$template" "$make_uimage" "$pack" \
	"$contract_tool" "${tc}gcc"; do
	[ -e "$required" ] || { echo "missing Q3 input: $required" >&2; exit 3; }
done
[ -d "$seed_a" ] && [ -d "$seed_b" ] || { echo 'missing preserved Q2 incremental kernel trees' >&2; exit 3; }

require_sha "$q2_rootfs" "$expected_q2_rootfs"
require_sha "$q2_web" "$expected_q2_web"
require_sha "$origin_rootfs" "$expected_origin_rootfs"
require_sha "$origin_manifest" "$expected_origin_manifest"
require_sha "$bootenv_manifest" "$expected_bootenv_manifest"
require_sha "$bootenv_producer" "$expected_bootenv_producer"
require_sha "$canonical_persist" "$expected_canonical_persist"
require_sha "$canonical_origin_import" "$expected_canonical_origin_import"
require_sha "$canonical_radio_start" "$expected_canonical_radio_start"
require_sha "$canonical_radio_modules" "$expected_canonical_radio_modules"
require_sha "$canonical_control_event" "$expected_canonical_control_event"
require_sha "$canonical_ledctl" "$expected_canonical_ledctl"
require_sha "$canonical_led_contract" "$expected_canonical_led_contract"
require_sha "$canonical_radio5_toggle" "$expected_canonical_radio5_toggle"
require_sha "$canonical_ipv6_policy" "$expected_canonical_ipv6_policy"
require_sha "$canonical_ipv6_init" "$expected_canonical_ipv6_init"
require_sha "$canonical_config_get" "$expected_canonical_config_get"
require_sha "$canonical_config_prepare" "$expected_canonical_config_prepare"
require_sha "$canonical_config_restore" "$expected_canonical_config_restore"
require_sha "$canonical_defaults" "$expected_canonical_defaults"
require_sha "$canonical_factory_settings" "$expected_canonical_factory_settings"
require_sha "$canonical_degraded_clear" "$expected_canonical_degraded_clear"
require_sha "$canonical_ready" "$expected_canonical_ready"
require_sha "$canonical_radio_modules_init" "$expected_canonical_radio_modules_init"
require_sha "$canonical_radio_ap_init" "$expected_canonical_radio_ap_init"
require_sha "$canonical_videobridge_policy" "$expected_canonical_videobridge_policy"
require_sha "$canonical_videobridge_init" "$expected_canonical_videobridge_init"
require_sha "$canonical_oem_parity" "$expected_canonical_oem_parity"
require_sha "$canonical_api_status" "$expected_canonical_api_status"
require_sha "$canonical_http_config" "$expected_canonical_http_config"
require_sha "$canonical_https_config" "$expected_canonical_https_config"
require_sha "$canonical_cgi_stamp" "$expected_canonical_cgi_stamp"
require_sha "$origin_dts" "$expected_origin_dts"
require_sha "$controls_driver" "$expected_controls_driver"
require_sha "$kernel_src_base/drivers/mtd/chips/map_rom.c" "$expected_map_rom"
require_sha "$kernel_src_base/drivers/mtd/maps/physmap-core.c" "$expected_physmap"
require_sha "$qtn_overlay" "$expected_qtn_overlay"
require_sha "$qtn_manifest" "$expected_qtn_manifest"
require_sha "$qtn_sums" "$expected_qtn_sums"
require_sha "$qcsapi_runtime_manifest" "$expected_qcsapi_runtime_manifest"
require_sha "$qcsapi_abi_report" "$expected_qcsapi_abi_report"
require_sha "$radio5_overlay" "$expected_radio5_overlay"
require_sha "$radio5_manifest" "$expected_radio5_manifest"
require_sha "$canonical_radio5_start" "$expected_canonical_radio5_start"
if [ "$q3_autostart" = 0 ]; then
	require_sha "$maintenance_s53" "$expected_maintenance_s53"
	require_sha "$maintenance_s54" "$expected_maintenance_s54"
fi
if [ -n "$hbm_override" ] || [ -n "$expected_hbm_override" ]; then
	[ -n "$hbm_override" ] && [ -n "$expected_hbm_override" ] || {
		echo 'HBM override path and expected SHA-256 must be supplied together' >&2
		exit 3
	}
	require_sha "$hbm_override" "$expected_hbm_override"
fi
if [ -n "$emac_driver_override" ] || [ -n "$expected_emac_driver_override" ] || \
	[ -n "$emac_header_override" ] || [ -n "$expected_emac_header_override" ]; then
	[ -n "$emac_driver_override" ] && [ -n "$expected_emac_driver_override" ] && \
		[ -n "$emac_header_override" ] && [ -n "$expected_emac_header_override" ] || {
		echo 'EMAC driver/header overrides and expected SHA-256 values must be supplied together' >&2
		exit 3
	}
	require_sha "$emac_driver_override" "$expected_emac_driver_override"
	require_sha "$emac_header_override" "$expected_emac_header_override"
fi
if [ -n "$gpio4_diag_overlay" ]; then
	[ -n "$expected_gpio4_diag_overlay" ] || {
		echo 'GPIO4 diagnostic overlay requires an expected SHA-256' >&2
		exit 3
	}
	require_sha "$gpio4_diag_overlay" "$expected_gpio4_diag_overlay"
fi
if [ -n "$factory_authorized_keys" ]; then
	[ -f "$factory_authorized_keys" ] || { echo "missing Q3 factory authorized_keys file: $factory_authorized_keys" >&2; exit 3; }
	if grep -Ev '^(#|[[:space:]]*$|ssh-ed25519[[:space:]][A-Za-z0-9+/=]+([[:space:]].*)?$)' "$factory_authorized_keys" | grep -q .; then
		echo 'Q3 factory authorized_keys input contains non-ed25519 or malformed lines' >&2
		exit 3
	fi
	grep -Eq '^ssh-ed25519[[:space:]][A-Za-z0-9+/=]+' "$factory_authorized_keys" || {
		echo 'Q3 factory authorized_keys input contains no ssh-ed25519 key' >&2
		exit 3
	}
fi
require_sha "$w3_switch" "$expected_w3_switch"
require_sha "$w3_core" "$expected_w3_core"
require_sha "$w3_vap" "$expected_w3_vap"
require_sha "$w3_ap" "$expected_w3_ap"
require_sha "$w3_rollback" "$expected_w3_rollback"
require_sha "$legacy_lzma" "$expected_lzma_tool"

python3 "$w3_contract_test" >/dev/null

q2_rootfs_before=$(sha "$q2_rootfs")
q2_web_before=$(sha "$q2_web")

rm -rf -- "$stage_a" "$stage_b" "$origin_a" "$origin_b" "$rootfs_build" "$build"
mkdir -p "$rootfs_build" "$build" "$kernel_root" "$(dirname "$stage_a")" "$(dirname "$stage_b")" "$(dirname "$tftp")"
emac_source_match=1
if [ -n "$emac_driver_override" ]; then
	[ -f "$kernel_src/drivers/net/ethernet/qtn/qtn-topaz-emac.c" ] && \
		[ "$(sha "$kernel_src/drivers/net/ethernet/qtn/qtn-topaz-emac.c")" = "$expected_emac_driver_override" ] && \
		[ -f "$kernel_src/include/linux/soc/qtn/topaz-ethernet.h" ] && \
		[ "$(sha "$kernel_src/include/linux/soc/qtn/topaz-ethernet.h")" = "$expected_emac_header_override" ] || \
		emac_source_match=0
fi
if [ -f "$kernel_src/Makefile" ] && \
	[ "$(sha "$kernel_src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts")" = "$expected_origin_dts" ] && \
	[ "$(sha "$kernel_src/drivers/misc/qtn-topaz-recovery.c")" = "$expected_controls_driver" ] && \
	[ "$(sha "$kernel_src/drivers/mtd/chips/map_rom.c")" = "$expected_map_rom" ] && \
	[ "$(sha "$kernel_src/drivers/mtd/maps/physmap-core.c")" = "$expected_physmap" ] && \
	[ "$emac_source_match" = 1 ]; then
	printf 'OMQ3_KERNEL_SOURCE_REUSE_PASS dts=%s\n' "$expected_origin_dts"
else
	rm -rf -- "$kernel_src"
	mkdir -p "$(dirname "$kernel_src")"
	cp -al "$kernel_src_base" "$kernel_src"
	rm -f "$kernel_src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" \
		"$kernel_src/drivers/misc/qtn-topaz-recovery.c"
	cp "$origin_dts" "$kernel_src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
	cp "$controls_driver" "$kernel_src/drivers/misc/qtn-topaz-recovery.c"
	if [ -n "$emac_driver_override" ]; then
		cp "$emac_driver_override" "$kernel_src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
		cp "$emac_header_override" "$kernel_src/include/linux/soc/qtn/topaz-ethernet.h"
	fi
fi
require_sha "$kernel_src/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts" "$expected_origin_dts"
require_sha "$kernel_src/drivers/misc/qtn-topaz-recovery.c" "$expected_controls_driver"
require_sha "$kernel_src/drivers/mtd/chips/map_rom.c" "$expected_map_rom"
require_sha "$kernel_src/drivers/mtd/maps/physmap-core.c" "$expected_physmap"
if [ -n "$emac_driver_override" ]; then
	require_sha "$kernel_src/drivers/net/ethernet/qtn/qtn-topaz-emac.c" "$expected_emac_driver_override"
	require_sha "$kernel_src/include/linux/soc/qtn/topaz-ethernet.h" "$expected_emac_header_override"
fi

compose_stage()
{
	stage=$1
	origin_stage=$2
	(umask 000; unsquashfs -no-progress -d "$stage" "$q2_rootfs") >/dev/null
	(umask 000; unsquashfs -no-progress -d "$origin_stage" "$origin_rootfs") >/dev/null

	# Apply only the reviewed Origin/entropy delta.  Q2 remains the base for
	# every other service, UI file, Realtek module, and 2.4 GHz autostart path.
	for rel in \
		etc/init.d/rcS etc/init.d/S25-origin-import \
		usr/sbin/om-entropy-seed usr/sbin/om-origin-import \
		usr/sbin/om-config-get usr/sbin/om-config-prepare usr/sbin/om-ssh \
		usr/share/openmitrastar/origin-mtd5/current-unit.policy; do
		[ -f "$origin_stage/$rel" ] || { echo "Q3 Origin file missing: $rel" >&2; exit 4; }
		mkdir -p "$stage/$(dirname "$rel")"
		cp -a "$origin_stage/$rel" "$stage/$rel"
	done
	# Two runtime corrections proven by the first Q3 RAM boot are overlaid from
	# their exact canonical scripts without modifying Q2 or the Origin artifact.
	cp "$canonical_persist" "$stage/usr/sbin/om-persist"
	cp "$canonical_origin_import" "$stage/usr/sbin/om-origin-import"
	cp "$canonical_radio_start" "$stage/usr/sbin/om-radio-start"
	cp "$canonical_radio_modules" "$stage/usr/sbin/om-radio-modules"
	cp "$canonical_control_event" "$stage/usr/sbin/om-control-event"
	mkdir -p "$stage/usr/share/openmitrastar/leds"
	cp "$canonical_ledctl" "$stage/usr/sbin/om-ledctl"
	cp "$canonical_led_contract" "$stage/usr/share/openmitrastar/leds/hgw500-leds.json"
	cp "$canonical_radio5_toggle" "$stage/usr/sbin/om-radio5g-toggle"
	cp "$canonical_ipv6_policy" "$stage/usr/sbin/om-ipv6-local-policy"
	cp "$canonical_ipv6_init" "$stage/etc/init.d/S34-ipv6-local-policy"
	cp "$canonical_config_get" "$stage/usr/sbin/om-config-get"
	cp "$canonical_config_prepare" "$stage/usr/sbin/om-config-prepare"
	cp "$canonical_config_restore" "$stage/usr/sbin/om-config-restore"
	cp "$canonical_defaults" "$stage/usr/share/openmitrastar/config-schema/v1/defaults.conf"
	cp "$canonical_factory_settings" "$stage/usr/share/openmitrastar/factory-config/v1/v1/settings.conf"
	cp "$canonical_degraded_clear" "$stage/usr/sbin/om-degraded-clear"
	cp "$canonical_ready" "$stage/etc/init.d/S90-ready"
	cp "$canonical_radio_modules_init" "$stage/etc/init.d/S35-radio-modules"
	cp "$canonical_radio_ap_init" "$stage/etc/init.d/S50-radio-ap"
	cp "$canonical_videobridge_policy" "$stage/usr/sbin/om-videobridge-policy"
	cp "$canonical_videobridge_init" "$stage/etc/init.d/S33-videobridge-policy"
	cp "$canonical_oem_parity" "$stage/etc/openmitrastar/oem-parity.conf"
	[ -d "$realtek_product_artifact/modules" ] || { echo 'Q3 Realtek product modules missing' >&2; exit 4; }
	[ -f "$realtek_product_artifact/firmware/regulatory.db" ] || { echo 'Q3 Realtek regulatory.db missing' >&2; exit 4; }
	[ -f "$realtek_product_artifact/firmware/rtlwifi/rtl8192eefw.bin" ] || { echo 'Q3 Realtek firmware missing' >&2; exit 4; }
	mkdir -p "$stage/lib/modules/$release/openmitrastar/radio2g" "$stage/lib/firmware/rtlwifi"
	cp "$realtek_product_artifact/firmware/regulatory.db" "$stage/lib/firmware/regulatory.db"
	cp "$realtek_product_artifact/firmware/rtlwifi/rtl8192eefw.bin" "$stage/lib/firmware/rtlwifi/rtl8192eefw.bin"
	while read -r module; do
		[ -n "$module" ] || continue
		cp "$realtek_product_artifact/modules/$module" \
			"$stage/lib/modules/$release/openmitrastar/radio2g/$module"
	done <"$realtek_product_artifact/LOAD_ORDER.txt"
	cp "$realtek_product_artifact/LOAD_ORDER.txt" "$stage/usr/share/openmitrastar/radio2g/modules.order"
	python3 - "$stage" "$release" <<'PY'
from pathlib import Path
import hashlib, sys

stage = Path(sys.argv[1])
release = sys.argv[2]
paths = [
    "/lib/firmware/regulatory.db",
    "/lib/firmware/rtlwifi/rtl8192eefw.bin",
]
order = stage / "usr/share/openmitrastar/radio2g/modules.order"
for module in order.read_text(encoding="ascii").splitlines():
    module = module.strip()
    if module:
        paths.append(f"/lib/modules/{release}/openmitrastar/radio2g/{module}")
rows = []
for rel in paths:
    target = stage / rel.lstrip("/")
    if not target.is_file():
        raise SystemExit(f"Q3 Realtek artifact missing after copy: {rel}")
    rows.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()} {rel}")
(stage / "usr/share/openmitrastar/radio2g/artifacts.sha256").write_text(
    "\n".join(rows) + "\n", encoding="ascii"
)
PY
	mkdir -p "$stage/www/api" "$stage/usr/share/openmitrastar"
	cp "$canonical_api_status" "$stage/www/api/status"
	cp "$canonical_http_config" "$stage/etc/minihttpd-oem.conf"
	cp "$canonical_https_config" "$stage/etc/minihttpd-https.conf"
	cp "$canonical_cgi_stamp" "$stage/usr/share/openmitrastar/cgi-overlay-v1.json"
	if [ -n "$factory_authorized_keys" ]; then
		mkdir -p "$stage/usr/share/openmitrastar/keys"
		awk 'NF >= 2 && $1 == "ssh-ed25519" { print $1 " " $2 }' "$factory_authorized_keys" | sort -u \
			>"$stage/usr/share/openmitrastar/keys/factory-authorized_keys"
		chmod 0600 "$stage/usr/share/openmitrastar/keys/factory-authorized_keys"
	fi
	chmod 0755 "$stage/www/api/status"
	chmod 0755 "$stage/usr/sbin/om-control-event" \
		"$stage/usr/sbin/om-ledctl" \
		"$stage/usr/sbin/om-radio-modules" \
		"$stage/usr/sbin/om-radio5g-toggle" \
		"$stage/usr/sbin/om-ipv6-local-policy" \
		"$stage/etc/init.d/S34-ipv6-local-policy" \
		"$stage/usr/sbin/om-config-get" \
		"$stage/usr/sbin/om-config-prepare" \
		"$stage/usr/sbin/om-config-restore"
	chmod 0755 "$stage/usr/sbin/om-videobridge-policy" "$stage/etc/init.d/S33-videobridge-policy"
	chmod 0644 "$stage/etc/minihttpd-oem.conf" "$stage/etc/minihttpd-https.conf" \
		"$stage/usr/share/openmitrastar/cgi-overlay-v1.json" \
		"$stage/usr/share/openmitrastar/leds/hgw500-leds.json" \
		"$stage/etc/openmitrastar/oem-parity.conf"

	# Bootbase preserves rdinit=/init.  CONFIG_BLOCK makes prepare_namespace
	# enforce that exact pathname, so bind it to the product init explicitly.
	rm -f "$stage/init"
	ln -s sbin/init "$stage/init"

	# Install the exact safe-service overlay.  It contains the 22-module
	# direct-symbols/RXALIGN subset and deliberately excludes fwt_ctrl.  S55 is
	# present, but its activation feature remains absent until RAM proof.
	rm -rf "$stage/lib/modules/$release/openmitrastar/radio5g"
	tar -xzf "$radio5_overlay" -C "$stage"
	rm -rf "$stage/usr/libexec/openmitrastar/qcsapi-runtime"
	mkdir -p "$stage/usr/libexec/openmitrastar/qcsapi-runtime"
	cp -a "$qcsapi_runtime/." "$stage/usr/libexec/openmitrastar/qcsapi-runtime/"
	for link in \
		ld-uClibc.so.0:ld-uClibc-0.9.29.so \
		libc.so.0:libuClibc-0.9.29.so \
		libpthread.so.0:libpthread-0.9.29.so \
		libm.so.0:libm-0.9.29.so \
		libdl.so.0:libdl-0.9.29.so \
		librt.so.0:librt-0.9.29.so \
		libz.so.1:libz.so.1.2.3 \
		libqcsapi.so.1:libqcsapi.so.1.0.1 \
		libcall_qcsapi.so.1:libcall_qcsapi.so.1.0.1; do
		alias=${link%%:*}
		target=${link#*:}
		ln -sf "$target" "$stage/usr/libexec/openmitrastar/qcsapi-runtime/lib/$alias"
	done
	chmod 0600 "$stage/usr/libexec/openmitrastar/qcsapi-runtime/lib/"*.so*
	chmod 0700 "$stage/usr/libexec/openmitrastar/qcsapi-runtime/bin/call_qcsapi" \
		"$stage/usr/libexec/openmitrastar/qcsapi-runtime/bin/hostapd" \
		"$stage/usr/libexec/openmitrastar/qcsapi-runtime/bin/hostapd_cli" \
		"$stage/usr/libexec/openmitrastar/qcsapi-runtime/lib/ld-uClibc-0.9.29.so"
	if [ -n "$gpio4_diag_overlay" ]; then
		# Diagnostic module only: deliberately no init script or autoload hook.
		tar -xzf "$gpio4_diag_overlay" -C "$stage"
		test -f "$stage/lib/modules/$release/openmitrastar/diagnostics/hgw500-gpio4-diag.ko"
		chmod 0644 "$stage/lib/modules/$release/openmitrastar/diagnostics/hgw500-gpio4-diag.ko"
	fi
	cp "$bootenv_producer" "$stage/usr/sbin/om-bootenv-readonly"
	cp "$bootenv_manifest" "$stage/usr/share/openmitrastar/bootenv-wifiaddr-producer.json"
	cp "$canonical_radio5_start" "$stage/usr/sbin/om-radio5-start"
	# The Windows-produced overlay preserved CRLF in its checksum index and
	# dropped executable bits.  Normalize these archive properties explicitly.
	for file in artifacts.sha256 runtime.env; do
		sed 's/\r$//' "$stage/usr/share/openmitrastar/radio5g/$file" \
			>"$stage/usr/share/openmitrastar/radio5g/.$file.tmp"
		mv "$stage/usr/share/openmitrastar/radio5g/.$file.tmp" \
			"$stage/usr/share/openmitrastar/radio5g/$file"
	done
	chmod 0755 "$stage/etc/init.d/S55-radio5-ap" \
		"$stage/usr/sbin/om-radio5-start" "$stage/usr/sbin/om-radio5-stop" \
		"$stage/usr/sbin/hostapd-qtn" "$stage/usr/sbin/hostapd-cli-qtn" \
		"$stage/usr/sbin/iwconfig-qtn" "$stage/usr/sbin/iwpriv-qtn" \
		"$stage/usr/sbin/ram-insmod-qtn" "$stage/usr/sbin/om-bootenv-readonly" \
		"$stage/usr/sbin/om-qtn-mac-prepare" "$stage/etc/init.d/S54-qtn-mac"
	if [ -n "$expected_radio5_s53" ] || [ -n "$expected_qtn_cal_producer" ]; then
		[ -f "$stage/etc/init.d/S53-qtn-calibration" ] || { echo 'Q3 calibration init missing' >&2; exit 4; }
		[ -f "$stage/usr/sbin/om-qtn-cal-readonly" ] || { echo 'Q3 calibration producer missing' >&2; exit 4; }
		chmod 0755 "$stage/etc/init.d/S53-qtn-calibration" "$stage/usr/sbin/om-qtn-cal-readonly"
	fi
	if [ "$q3_autostart" = 0 ]; then
		# Maintenance still prepares read-only per-unit state during boot.  Only
		# S55/RF activation is disabled; manual om-radio5-start needs no hidden
		# calibration or MAC preparation step.
		cp "$maintenance_s53" "$stage/etc/init.d/S53-qtn-calibration"
		cp "$maintenance_s54" "$stage/etc/init.d/S54-qtn-mac"
		chmod 0755 "$stage/etc/init.d/S53-qtn-calibration" \
			"$stage/etc/init.d/S54-qtn-mac"
	fi
	find "$stage/lib/modules/$release/openmitrastar/radio5g" -type f -name '*.ko' -exec chmod 0644 {} +
	chmod 0644 "$stage/usr/share/openmitrastar/radio5g/artifacts.sha256" \
		"$stage/usr/share/openmitrastar/radio5g/modules.order" \
		"$stage/usr/share/openmitrastar/radio5g/q3-radio5-autostart.feature" \
		"$stage/usr/share/openmitrastar/radio5g/runtime-contract.json" \
		"$stage/usr/share/openmitrastar/radio5g/runtime.env" \
		"$stage/usr/share/openmitrastar/bootenv-wifiaddr-producer.json" \
		"$stage/lib/firmware/qtn_driver.qtn_ruby.0.bin" \
		"$stage/lib/firmware/auc_driver.nomu.0.bin" \
		"$stage/lib/firmware/rdsp_driver.0.bin" \
		"$stage/etc/qtn_regulatory_db.bin" "$stage/etc/power_tables/"*
	feature="$stage/etc/openmitrastar/features/q3-radio5-autostart"
	if [ "$q3_autostart" = 1 ]; then
		[ -f "$feature" ] || { echo 'Q3 promoted radio5 feature gate missing' >&2; exit 4; }
		feature_value=$(sed -n '1{s/\r$//;p;}' "$feature")
		[ "$feature_value" = Q3_RADIO5_AUTOSTART=1 ] || {
			echo 'Q3 promoted radio5 feature gate invalid' >&2; exit 4;
		}
		printf '%s\n' "$feature_value" >"$feature"
	else
		rm -f "$feature"
	fi
	case "$q3_profile" in open-lab*)
		open_feature="$stage/etc/openmitrastar/features/q3-radio5-open-lab"
		[ -f "$open_feature" ] || { echo 'Q3 OPEN-LAB feature gate missing' >&2; exit 4; }
		open_value=$(sed -n '1{s/\r$//;p;}' "$open_feature")
		[ "$open_value" = Q3_RADIO5_OPEN_LAB=1 ] || { echo 'Q3 OPEN-LAB feature invalid' >&2; exit 4; }
		printf '%s\n' "$open_value" >"$open_feature"
		chmod 0644 "$open_feature"
		;;
	esac
	if [ "$q3_profile" = open-lab-tqe512 ]; then
		tqe_feature="$stage/etc/openmitrastar/features/q3-radio5-tqe512-discriminator"
		[ -f "$tqe_feature" ] || { echo 'Q3 TQE512 discriminator feature missing' >&2; exit 4; }
		tqe_value=$(sed -n '1{s/\r$//;p;}' "$tqe_feature")
		[ "$tqe_value" = Q3_RADIO5_TQE_RING_ENTRIES=512 ] || { echo 'Q3 TQE512 discriminator feature invalid' >&2; exit 4; }
		printf '%s\n' "$tqe_value" >"$tqe_feature"
		chmod 0644 "$tqe_feature"
	fi
	if [ "$q3_profile" = open-lab-beacon-preflight ]; then
		beacon_feature="$stage/etc/openmitrastar/features/q3-radio5-beacon-preflight"
		[ -f "$beacon_feature" ] || { echo 'Q3 beacon preflight feature missing' >&2; exit 4; }
		beacon_value=$(sed -n '1{s/\r$//;p;}' "$beacon_feature")
		[ "$beacon_value" = Q3_RADIO5_BEACON_PREFLIGHT=1 ] || { echo 'Q3 beacon preflight feature invalid' >&2; exit 4; }
		printf '%s\n' "$beacon_value" >"$beacon_feature"
		chmod 0644 "$beacon_feature"
	fi
	if [ "$q3_profile" = open-lab-beacon-lifetime ]; then
		lifetime_feature="$stage/etc/openmitrastar/features/q3-radio5-beacon-lifetime"
		[ -f "$lifetime_feature" ] || { echo 'Q3 beacon lifetime feature missing' >&2; exit 4; }
		lifetime_value=$(sed -n '1{s/\r$//;p;}' "$lifetime_feature")
		[ "$lifetime_value" = Q3_RADIO5_BEACON_LIFETIME=1 ] || { echo 'Q3 beacon lifetime feature invalid' >&2; exit 4; }
		printf '%s\n' "$lifetime_value" >"$lifetime_feature"
		chmod 0644 "$lifetime_feature"
	fi
	[ "$(find "$stage/lib/modules/$release/openmitrastar/radio5g" -type f -name '*.ko' | wc -l)" -eq 22 ]
	[ ! -e "$stage/lib/modules/$release/openmitrastar/radio5g/fwt_ctrl.ko" ]
	cp "$qtn_manifest" "$stage/usr/share/openmitrastar/radio5g/direct-symbols-module-manifest.tsv"
	cp "$qtn_sums" "$stage/usr/share/openmitrastar/radio5g/direct-symbols-SHA256SUMS"
	cp "$radio5_manifest" "$stage/usr/share/openmitrastar/radio5g/q3-dual-radio-build-manifest.json"
	if [ -n "$hbm_override" ]; then
		hbm_target="$stage/lib/modules/$release/openmitrastar/radio5g/hbm.ko"
		cp "$hbm_override" "$hbm_target"
		chmod 0644 "$hbm_target"
		python3 - "$stage" "$expected_hbm_override" <<'PY'
from pathlib import Path
import hashlib, json, os, sys

stage = Path(sys.argv[1])
expected = sys.argv[2]
module_path = "/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/hbm.ko"

sums = stage / "usr/share/openmitrastar/radio5g/artifacts.sha256"
rows = []
replaced = 0
for line in sums.read_text(encoding="utf-8").splitlines():
    digest, path = line.split(" ", 1)
    if path == module_path:
        digest = expected
        replaced += 1
    rows.append(f"{digest} {path}")
if replaced != 1:
    raise SystemExit("Q3 HBM override artifacts.sha256 row missing or duplicated")
sums.write_text("\n".join(rows) + "\n", encoding="ascii")

runtime = stage / "usr/share/openmitrastar/radio5g/runtime.env"
runtime_rows = []
replaced = 0
for line in runtime.read_text(encoding="utf-8").splitlines():
    if line.startswith("Q3_HBM_SHA256="):
        line = "Q3_HBM_SHA256=" + expected
        replaced += 1
    runtime_rows.append(line)
if replaced != 1:
    raise SystemExit("Q3 HBM override runtime.env row missing or duplicated")
runtime.write_text("\n".join(runtime_rows) + "\n", encoding="ascii")

direct = stage / "usr/share/openmitrastar/radio5g/direct-symbols-module-manifest.tsv"
direct_rows = []
replaced = 0
for line in direct.read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if fields[0] == "platform/topaz/hbm.ko":
        fields[1] = expected
        fields[2] = str((stage / module_path.lstrip("/")).stat().st_size)
        line = "\t".join(fields)
        replaced += 1
    direct_rows.append(line)
if replaced != 1:
    raise SystemExit("Q3 HBM override direct manifest row missing or duplicated")
direct.write_text("\n".join(direct_rows) + "\n", encoding="ascii")

direct_sums = stage / "usr/share/openmitrastar/radio5g/direct-symbols-SHA256SUMS"
direct_manifest_hash = hashlib.sha256(direct.read_bytes()).hexdigest()
sum_rows = []
replaced = 0
for line in direct_sums.read_text(encoding="utf-8").splitlines():
    digest, path = line.split(None, 1)
    if path == "module-manifest.tsv":
        digest = direct_manifest_hash
        replaced += 1
    sum_rows.append(f"{digest}  {path}")
if replaced != 1:
    raise SystemExit("Q3 HBM override direct SHA256SUMS row missing or duplicated")
direct_sums.write_text("\n".join(sum_rows) + "\n", encoding="ascii")

stamp = {
    "schema": "openmitrastar.q3-hbm-clear-probe/v1",
    "classification": "RAM_ONLY_NO_FLASH",
    "compatible": "mitrastar,hgw-500bna-qcv2",
    "hardware_revision": "A2",
    "module": module_path,
    "sha256": expected,
    "chunk_bytes": 4194304,
    "hardware_validation": "pending",
    "flash_actions": False,
}
stamp_path = stage / "usr/share/openmitrastar/radio5g/hbm-clear-probe.json"
stamp_path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(stamp_path, 0o644)
PY
	fi
	if [ -n "$switch_tqe_override" ]; then
		switch_tqe_target="$stage/lib/modules/$release/openmitrastar/radio5g/switch_tqe.ko"
		cp "$switch_tqe_override" "$switch_tqe_target"
		chmod 0644 "$switch_tqe_target"
		python3 - "$stage" "$expected_switch_tqe_override" <<'PY'
from pathlib import Path
import hashlib, json, os, sys

stage = Path(sys.argv[1])
expected = sys.argv[2]
module_path = "/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/switch_tqe.ko"
module = stage / module_path.lstrip("/")

actual = hashlib.sha256(module.read_bytes()).hexdigest()
if not expected or actual != expected:
    raise SystemExit("Q3 switch_tqe override hash mismatch")

sums = stage / "usr/share/openmitrastar/radio5g/artifacts.sha256"
rows = []
replaced = 0
for line in sums.read_text(encoding="utf-8").splitlines():
    digest, path = line.split(" ", 1)
    if path == module_path:
        digest = expected
        replaced += 1
    rows.append(f"{digest} {path}")
if replaced != 1:
    raise SystemExit("Q3 switch_tqe override artifacts.sha256 row missing or duplicated")
sums.write_text("\n".join(rows) + "\n", encoding="ascii")

runtime = stage / "usr/share/openmitrastar/radio5g/runtime.env"
runtime_rows = []
replaced = 0
for line in runtime.read_text(encoding="utf-8").splitlines():
    if line.startswith("Q3_SWITCH_TQE_SHA256="):
        line = "Q3_SWITCH_TQE_SHA256=" + expected
        replaced += 1
    runtime_rows.append(line)
if replaced != 1:
    raise SystemExit("Q3 switch_tqe override runtime.env row missing or duplicated")
runtime.write_text("\n".join(runtime_rows) + "\n", encoding="ascii")

direct = stage / "usr/share/openmitrastar/radio5g/direct-symbols-module-manifest.tsv"
direct_rows = []
replaced = 0
for line in direct.read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if fields[0] == "platform/topaz/switch_tqe.ko":
        fields[1] = expected
        fields[2] = str(module.stat().st_size)
        line = "\t".join(fields)
        replaced += 1
    direct_rows.append(line)
if replaced != 1:
    raise SystemExit("Q3 switch_tqe override direct manifest row missing or duplicated")
direct.write_text("\n".join(direct_rows) + "\n", encoding="ascii")

direct_sums = stage / "usr/share/openmitrastar/radio5g/direct-symbols-SHA256SUMS"
direct_manifest_hash = hashlib.sha256(direct.read_bytes()).hexdigest()
sum_rows = []
replaced = 0
for line in direct_sums.read_text(encoding="utf-8").splitlines():
    digest, path = line.split(None, 1)
    if path == "module-manifest.tsv":
        digest = direct_manifest_hash
        replaced += 1
    sum_rows.append(f"{digest}  {path}")
if replaced != 1:
    raise SystemExit("Q3 switch_tqe override direct SHA256SUMS row missing or duplicated")
direct_sums.write_text("\n".join(sum_rows) + "\n", encoding="ascii")

stamp = {
    "schema": "openmitrastar.q3-switch-tqe-dma-cache-fix/v1",
    "classification": "RAM_ONLY_NO_FLASH",
    "compatible": "mitrastar,hgw-500bna-qcv2",
    "hardware_revision": "A2",
    "module": module_path,
    "sha256": expected,
    "dma_map_page_attrs_in_tqe_rx_pkt_drop": False,
    "replacement": "dma_cache_inv",
    "hardware_validation": "pending",
    "flash_actions": False,
}
stamp_path = stage / "usr/share/openmitrastar/radio5g/switch-tqe-dma-cache-fix.json"
stamp_path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(stamp_path, 0o644)
PY
	fi

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
guard = needle + '\n' + 'test "$skip_ioss_reset_pulse" = 1 || stop 92 reason=q3_ioss_reset_forbidden'
if text.count(needle) != 1:
    raise SystemExit("Q3 no-IOSS patch anchor drift")
path.write_text(text.replace(needle, guard), encoding="utf-8")
PY
	chmod 0755 "$w3dir"/*

	python3 - "$stage" "$origin_manifest" "$radio5_manifest" "$w3_switch" "$w3_core" "$w3_vap" "$w3_ap" "$w3_rollback" <<'PY'
from pathlib import Path
import hashlib, json, os, stat, sys

stage = Path(sys.argv[1])
origin_path = Path(sys.argv[2])
radio5_manifest_path = Path(sys.argv[3])
sources = [Path(x) for x in sys.argv[4:]]
origin = json.loads(origin_path.read_text(encoding="utf-8"))
radio5_manifest = json.loads(radio5_manifest_path.read_text(encoding="utf-8"))
profile = os.environ.get("OM_Q3_PROFILE", "autostart-secure")
autostart = os.environ.get("OM_Q3_AUTOSTART", "1") == "1"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

origin_files = {
    "etc/init.d/rcS": "2435abe03da459ff82f8ca77bf2a447f30c043c9e69c6da1a411702dfafc0592",
    "etc/init.d/S25-origin-import": "30207e7c0b17a2f47c0b74dfe413730b2adeadc0decd7536ab74dd33a6718093",
    "usr/sbin/om-entropy-seed": "b078bb6de4b889963daadf42b3665bc8f808155df1ac54410f12147b3ce222f6",
    "usr/sbin/om-origin-import": "85cdb3d25317eddbfd973939ace81ed139f2f6e1be3a86ae8d34b4609d40d4fb",
    "usr/sbin/om-persist": "a411323a97391c76f2d7439dd5ae99263d189151e3e0b76e79699ec0cee8af20",
    "usr/sbin/om-radio-start": os.environ.get("OM_Q3_EXPECTED_RADIO_START_SHA256", "46bd158c0e0c200cc5f8adea30e962cbfe3b8a72b7defbb17d4d70aaa6c9cd97"),
    "usr/sbin/om-radio-modules": os.environ.get("OM_Q3_EXPECTED_RADIO_MODULES_SHA256", "428a91a54a0fce4d1475219142eb91e86999edaffcd9a1e4b5b4015b6d733786"),
    "usr/sbin/om-degraded-clear": "f6c5fa02f538469b5d7841e766c46c46984d830bfd316f0a2006371913e75eeb",
    "etc/init.d/S90-ready": "492ba7cd10e7c41f4c4b8c2645678c03fae2bfdd68d98dc67f6540f0a2a44d32",
    "etc/init.d/S35-radio-modules": "bc79afe8f23eab00db8864a8a0b676c072eaf4131b1320523e55f49c9615ec5d",
    "etc/init.d/S50-radio-ap": "1a0bb8918139fc08f0a06d7c1153c81eb31b728fa7c450a61f9af98120921d71",
    "usr/sbin/om-radio5-start": os.environ.get("OM_Q3_EXPECTED_RADIO5_START_SHA256", "851ee2204cd6c03b6cd630813cbf182897538ba0a70348e10b4305aded9eb3a7"),
    "usr/sbin/om-config-get": "da1e1210a503182f5d3329107518a654a831824cdec102116c1e530789492dfd",
    "usr/sbin/om-config-prepare": "c909f0bcfcc111c11ac0a5a6767c643321e6eae8dbb4d3c4c5600c2a27cbc51f",
    "usr/sbin/om-config-restore": "e4a659455a21e4cdc1268633ee54e18e435b5400205f06feb67730cd4cea20fa",
    "usr/sbin/om-control-event": "7be9fb928841ce59ef259319f51da4be952cb7cda48a9883b2a8aef33df2edb7",
    "usr/sbin/om-radio5g-toggle": "45951a36be4b6f649c6e92eb1f72ac2fa2d922d9b327aac712ca0814f021e45a",
    "usr/sbin/om-ipv6-local-policy": "a64b81c9eaaaaaa9ae23a9171a5b6d167fc6517b815be95b8be7a7205a86d7f8",
    "etc/init.d/S34-ipv6-local-policy": "a4a8e4b8855f7fa438d44ba96cdaacb6bcd55415f265ef391a3e351afbe633d0",
    "usr/share/openmitrastar/config-schema/v1/defaults.conf": "9453b9960cf7dc0387f6138819295eb71308840ec28f526efc3ea4720c573050",
    "usr/share/openmitrastar/factory-config/v1/v1/settings.conf": "9453b9960cf7dc0387f6138819295eb71308840ec28f526efc3ea4720c573050",
    "usr/sbin/om-ssh": "f7dfc096e6a3f03d4442cae77cf84ef7b6af63645f2c0066fd7ec4742f01c9fd",
    "usr/share/openmitrastar/origin-mtd5/current-unit.policy": origin["artifacts"]["rootfs/current-unit.policy"]["sha256"],
}
for rel, expected in origin_files.items():
    path = stage / rel
    if not path.is_file() or sha(path) != expected:
        raise SystemExit(f"Q3 Origin delta mismatch: {rel}")
for rel in ("etc/init.d/rcS", "etc/init.d/S25-origin-import", "usr/sbin/om-entropy-seed",
            "usr/sbin/om-origin-import", "usr/sbin/om-persist", "usr/sbin/om-config-get", "usr/sbin/om-config-prepare",
            "usr/sbin/om-config-restore", "usr/sbin/om-control-event", "usr/sbin/om-radio5g-toggle",
            "usr/sbin/om-ipv6-local-policy", "etc/init.d/S34-ipv6-local-policy",
            "usr/sbin/om-ssh", "usr/sbin/om-radio-start", "usr/sbin/om-radio-modules",
            "usr/sbin/om-degraded-clear",
            "etc/init.d/S90-ready", "etc/init.d/S35-radio-modules", "etc/init.d/S50-radio-ap",
            "usr/sbin/om-radio5-start"):
    os.chmod(stage / rel, 0o755)
os.chmod(stage / "usr/share/openmitrastar/origin-mtd5/current-unit.policy", 0o600)
os.chmod(stage / "usr/share/openmitrastar/config-schema/v1/defaults.conf", 0o644)
os.chmod(stage / "usr/share/openmitrastar/factory-config/v1/v1/settings.conf", 0o644)

rows = []
sums = stage / "usr/share/openmitrastar/radio5g/artifacts.sha256"
for line in sums.read_text(encoding="utf-8").splitlines():
    expected, rel = line.split(" ", 1)
    embedded = stage / rel.lstrip("/")
    if not embedded.is_file() or sha(embedded) != expected:
        raise SystemExit(f"Q3 safe radio5 payload mismatch: {rel}")
    if rel.endswith(".ko"):
        rows.append({"embedded": rel.lstrip("/"), "sha256": expected, "bytes": embedded.stat().st_size})
if len(rows) != 22:
    raise SystemExit("Q3 Quantenna module count mismatch")
if (stage / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/fwt_ctrl.ko").exists():
    raise SystemExit("Q3 safe radio5 payload contains forbidden fwt_ctrl")
qcsapi_runtime = stage / "usr/libexec/openmitrastar/qcsapi-runtime"
qcsapi_manifest = qcsapi_runtime / "manifest.sha256"
if not qcsapi_manifest.is_file():
    raise SystemExit("Q3 qcsapi runtime manifest missing")
for line in qcsapi_manifest.read_text(encoding="ascii").splitlines():
    if not line.strip():
        continue
    expected, rel = line.split(None, 1)
    embedded = qcsapi_runtime / rel
    if not embedded.is_file() or sha(embedded) != expected:
        raise SystemExit(f"Q3 qcsapi runtime mismatch: {rel}")
aliases = {
    "ld-uClibc.so.0": "ld-uClibc-0.9.29.so",
    "libc.so.0": "libuClibc-0.9.29.so",
    "libpthread.so.0": "libpthread-0.9.29.so",
    "libm.so.0": "libm-0.9.29.so",
    "libdl.so.0": "libdl-0.9.29.so",
    "librt.so.0": "librt-0.9.29.so",
    "libz.so.1": "libz.so.1.2.3",
    "libqcsapi.so.1": "libqcsapi.so.1.0.1",
    "libcall_qcsapi.so.1": "libcall_qcsapi.so.1.0.1",
}
for alias, target_name in aliases.items():
    link = qcsapi_runtime / "lib" / alias
    if not link.is_symlink() or os.readlink(link) != target_name:
        raise SystemExit(f"Q3 qcsapi alias mismatch: {alias}")
for rel in ("bin/call_qcsapi", "lib/ld-uClibc-0.9.29.so"):
    if stat.S_IMODE((qcsapi_runtime / rel).stat().st_mode) != 0o700:
        raise SystemExit(f"Q3 qcsapi executable mode mismatch: {rel}")
feature = stage / "etc/openmitrastar/features/q3-radio5-autostart"
if autostart:
    if radio5_manifest["autostart_enabled_by_default"] is not True:
        raise SystemExit("Q3 promoted radio5 overlay does not enable autostart")
    if not feature.is_file() or feature.read_text(encoding="utf-8").strip() != "Q3_RADIO5_AUTOSTART=1":
        raise SystemExit("Q3 promoted radio5 feature gate missing or invalid")
    if stat.S_IMODE(feature.stat().st_mode) != 0o644:
        raise SystemExit("Q3 promoted radio5 feature mode mismatch")
elif feature.exists():
    raise SystemExit("Q3 maintenance image unexpectedly enables radio5 autostart")
if profile.startswith("open-lab"):
    expected_class = ("OPEN-LAB-TQE512-DISCRIMINATOR-RAM-ONLY-NO-FLASH" if profile == "open-lab-tqe512" else ("OPEN-LAB-BEACON-PREFLIGHT-RAM-ONLY-NO-FLASH" if profile == "open-lab-beacon-preflight" else ("OPEN-LAB-BEACON-LIFETIME-RAM-ONLY-NO-FLASH" if profile == "open-lab-beacon-lifetime" else "OPEN-LAB-RAM-ONLY-NO-FLASH")))
    if radio5_manifest.get("classification") != expected_class or radio5_manifest.get("profile") != profile:
        raise SystemExit("Q3 OPEN-LAB manifest classification mismatch")
    if radio5_manifest.get("psk_required") is not False or radio5_manifest.get("psk_bundled") is not False:
        raise SystemExit("Q3 OPEN-LAB PSK contract mismatch")
    open_feature = stage / "etc/openmitrastar/features/q3-radio5-open-lab"
    if not open_feature.is_file() or open_feature.read_text(encoding="utf-8").strip() != "Q3_RADIO5_OPEN_LAB=1":
        raise SystemExit("Q3 OPEN-LAB feature missing")
    if stat.S_IMODE(open_feature.stat().st_mode) != 0o644:
        raise SystemExit("Q3 OPEN-LAB feature mode mismatch")
    if profile == "open-lab-tqe512":
        tqe_feature = stage / "etc/openmitrastar/features/q3-radio5-tqe512-discriminator"
        if not tqe_feature.is_file() or tqe_feature.read_text(encoding="utf-8").strip() != "Q3_RADIO5_TQE_RING_ENTRIES=512":
            raise SystemExit("Q3 TQE512 discriminator feature missing")
        if stat.S_IMODE(tqe_feature.stat().st_mode) != 0o644:
            raise SystemExit("Q3 TQE512 discriminator feature mode mismatch")
    if profile == "open-lab-beacon-preflight":
        beacon_feature = stage / "etc/openmitrastar/features/q3-radio5-beacon-preflight"
        if not beacon_feature.is_file() or beacon_feature.read_text(encoding="utf-8").strip() != "Q3_RADIO5_BEACON_PREFLIGHT=1":
            raise SystemExit("Q3 beacon preflight feature missing")
        if stat.S_IMODE(beacon_feature.stat().st_mode) != 0o644:
            raise SystemExit("Q3 beacon preflight feature mode mismatch")
    if profile == "open-lab-beacon-lifetime":
        lifetime_feature = stage / "etc/openmitrastar/features/q3-radio5-beacon-lifetime"
        if not lifetime_feature.is_file() or lifetime_feature.read_text(encoding="utf-8").strip() != "Q3_RADIO5_BEACON_LIFETIME=1":
            raise SystemExit("Q3 beacon lifetime feature missing")
        if stat.S_IMODE(lifetime_feature.stat().st_mode) != 0o644:
            raise SystemExit("Q3 beacon lifetime feature mode mismatch")
producer = stage / "usr/sbin/om-bootenv-readonly"
consumer = stage / "usr/sbin/om-qtn-mac-prepare"
s54 = stage / "etc/init.d/S54-qtn-mac"
s55 = stage / "etc/init.d/S55-radio5-ap"
expected_s55 = os.environ.get("OM_Q3_EXPECTED_RADIO5_S55_SHA256", "06c0efbbb951a84f4990fd9fd99dbbedfd99f19695edea7bc94385e80bc4daa2")
expected_s53 = os.environ.get("OM_Q3_EXPECTED_RADIO5_S53_SHA256", "")
expected_cal_producer = os.environ.get("OM_Q3_EXPECTED_QTN_CAL_PRODUCER_SHA256", "")
expected_maintenance_s53 = os.environ.get("OM_Q3_EXPECTED_MAINTENANCE_S53_SHA256", "23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404")
expected_maintenance_s54 = os.environ.get("OM_Q3_EXPECTED_MAINTENANCE_S54_SHA256", "cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d")
if sha(producer) != "7ae702dafca99b95fa95a0098a2662622278e10788869d70e00f61b5738fdb96":
    raise SystemExit("Q3 bootenv producer mismatch")
if sha(consumer) != "26d39272d932a77f1c58a38f0a0065e3e56022bdfaea28d9dfb8633d5531ddd2":
    raise SystemExit("Q3 qtn MAC consumer mismatch")
selected_s54 = ("c2559268692b5568288f4df3b4b3e8febe550a45825e7d80f6bd7506b2a3ef70"
                if autostart else expected_maintenance_s54)
if sha(s54) != selected_s54:
    raise SystemExit("Q3 S54 MAC producer init mismatch")
if sha(s55) != expected_s55:
    raise SystemExit("Q3 S55 promoted autostart mismatch")
executables = [producer, consumer, s54, s55]
if expected_s53 or expected_cal_producer:
    s53 = stage / "etc/init.d/S53-qtn-calibration"
    cal_producer = stage / "usr/sbin/om-qtn-cal-readonly"
    if not expected_s53 or not expected_cal_producer:
        raise SystemExit("Q3 calibration pins must be supplied together")
    selected_s53 = expected_s53 if autostart else expected_maintenance_s53
    if not s53.is_file() or sha(s53) != selected_s53:
        raise SystemExit("Q3 S53 calibration init mismatch")
    if not cal_producer.is_file() or sha(cal_producer) != expected_cal_producer:
        raise SystemExit("Q3 calibration producer mismatch")
    calibration = radio5_manifest.get("contract", {}).get("calibration", {})
    if radio5_manifest.get("device_calibration_runtime_import") is not True:
        raise SystemExit("Q3 calibration runtime import contract missing")
    if calibration.get("flash_writes") is not False or calibration.get("copies_must_match") is not True:
        raise SystemExit("Q3 calibration safety contract mismatch")
    executables.extend((s53, cal_producer))
if not autostart:
    if sha(s54) != expected_maintenance_s54:
        raise SystemExit("Q3 maintenance S54 MAC preparation mismatch")
    s53_text = s53.read_text(encoding="utf-8")
    s54_text = s54.read_text(encoding="utf-8")
    if "q3-radio5-autostart" in s53_text or "q3-radio5-autostart" in s54_text:
        raise SystemExit("Q3 maintenance preparation still depends on RF autostart")
    if "OMQTNCAL_PREP_START" not in s53_text or "OMQTN_MAC_PREP_START" not in s54_text:
        raise SystemExit("Q3 maintenance preparation markers missing")
for executable in executables:
    if stat.S_IMODE(executable.stat().st_mode) != 0o755:
        raise SystemExit(f"Q3 promoted executable mode mismatch: {executable}")

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
guard = 'test "$skip_ioss_reset_pulse" = 1 || stop 92 reason=q3_ioss_reset_forbidden'
if guard not in switch or switch.index(guard) > switch.index("load_module qtn_pm_qos_compat.ko"):
    raise SystemExit("Q3 no-IOSS guard is absent or too late")
if 'w3_symbols_only=1' not in switch:
    raise SystemExit("Q3 direct-EMAC symbols-only route missing")
contract = {
    "schema": "openmitrastar.q3-w3-direct-emac/v1",
    "classification": "Q3-MAINTENANCE-MANUAL-5G-RAM-ONLY-NO-FLASH" if not autostart else (("OPEN-LAB-TQE512-DISCRIMINATOR-RAM-ONLY-NO-FLASH" if profile == "open-lab-tqe512" else ("OPEN-LAB-BEACON-PREFLIGHT-RAM-ONLY-NO-FLASH" if profile == "open-lab-beacon-preflight" else ("OPEN-LAB-BEACON-LIFETIME-RAM-ONLY-NO-FLASH" if profile == "open-lab-beacon-lifetime" else "OPEN-LAB-RAM-ONLY-NO-FLASH"))) if profile.startswith("open-lab") else "EMBEDDED-AUTOSTART-HARDWARE-PENDING"),
    "compatible": "mitrastar,hgw-500bna-qcv2",
    "kernel_release": "5.10.260-openmitrastar-radiohw",
    "ioss_reset_pulse": "forbidden-by-q3-guard",
    "direct_emac": "preserved",
    "switch_emac_mode": "w3_symbols_only=1",
    "fwt_ctrl_runtime": "excluded-from-safe-ladder",
    "required_gate": "W3_SKIP_IOSS_RESET_PULSE=1",
    "autostart": autostart,
    "profile": profile,
    "security_profile": "OPEN" if profile.startswith("open-lab") else "WPA2-PSK-CCMP",
    "psk_required": not profile.startswith("open-lab"),
    "rf_default": "blocked",
    "flash_write": False,
    "local_rollback_required": True,
    "host_commit_required": True,
    "hardware_validation": "pending",
    "qcsapi_control_plane": {
        "runtime": "/usr/libexec/openmitrastar/qcsapi-runtime",
        "client": "/usr/libexec/openmitrastar/qcsapi-runtime/bin/call_qcsapi",
        "dynamic_closure": "uClibc-0.9.29",
        "psk_bundled": False,
    },
    "maintenance_preparation": {
        "boot_calibration_read_only": not autostart,
        "boot_mac_read_only": not autostart,
        "rf_start_deferred_to_manual_s55": not autostart,
        "hidden_manual_prerequisites": False,
    },
    "modules": rows,
    "safe_service": {
        "init": "/etc/init.d/S55-radio5-ap",
        "start": "/usr/sbin/om-radio5-start",
        "stop": "/usr/sbin/om-radio5-stop",
        "embedded": True,
        "autostart_feature_installed": autostart,
        "hardware_validation": "pending",
    },
    "files": files,
}
(stage / "usr/share/openmitrastar/q3-w3-direct-emac.json").write_text(
    json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
os.chmod(stage / "usr/share/openmitrastar/q3-w3-direct-emac.json", 0o644)
PY

	# Secrets remain runtime inputs; no PSK, private MAC or TLS private key is
	# permitted in the Q3 image.  The mtd5 importer publishes them only to tmpfs.
	! find "$stage" -type f -exec grep -a -E -l \
		'BEGIN (RSA |EC )?PRIVATE KEY|OM_PRODUCT_PRIVATE_PSK' {} + \
		>/dev/null 2>&1
	find "$stage" -exec touch -h -d "@$epoch" {} +
}

compose_stage "$stage_a" "$origin_a"
compose_stage "$stage_b" "$origin_b"

mksquashfs "$stage_a" "$rootfs_a" -comp gzip -b 131072 -all-root -noappend \
	-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
mksquashfs "$stage_b" "$rootfs_b" -comp gzip -b 131072 -all-root -noappend \
	-no-xattrs -reproducible -mkfs-time "$epoch" -all-time "$epoch" >/dev/null
cmp -s "$rootfs_a" "$rootfs_b" || { echo 'Q3 rootfs reproducibility mismatch' >&2; exit 5; }
cp "$rootfs_a" "$rootfs"

python3 - "$stage_a" "$rootfs" "$rootfs_manifest" "$q2_rootfs" "$q2_web" \
	"$origin_manifest" "$bootenv_manifest" "$radio5_manifest" <<'PY'
from pathlib import Path
import hashlib, json, os, sys

stage, rootfs, output, q2root, q2web, origin, bootenv, radio5 = map(Path, sys.argv[1:])
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
contract = stage / "usr/share/openmitrastar/q3-w3-direct-emac.json"
profile = os.environ.get("OM_Q3_PROFILE", "autostart-secure")
open_lab = profile.startswith("open-lab")
autostart = os.environ.get("OM_Q3_AUTOSTART", "1") == "1"
manifest = {
    "schema": "openmitrastar.q3-persistent-rootfs/v1",
    "classification": "Q3-MAINTENANCE-MANUAL-5G-RAM-ONLY-NO-FLASH" if not autostart else (("OPEN-LAB-TQE512-DISCRIMINATOR-RAM-ONLY-NO-FLASH" if profile == "open-lab-tqe512" else ("OPEN-LAB-BEACON-PREFLIGHT-RAM-ONLY-NO-FLASH" if profile == "open-lab-beacon-preflight" else ("OPEN-LAB-BEACON-LIFETIME-RAM-ONLY-NO-FLASH" if profile == "open-lab-beacon-lifetime" else "OPEN-LAB-RAM-ONLY-NO-FLASH"))) if open_lab else "OFFLINE-Q3-PERSISTENT-COMPOSITE-HARDWARE-PENDING-NO-FLASH"),
    "profile": profile,
    "candidate_eligible": False,
    "hardware_actions": False,
    "network_actions": False,
    "flash_supported": False,
    "rootfs": {"file": rootfs.name, "bytes": rootfs.stat().st_size, "sha256": sha(rootfs)},
    "sources": {
        "persistent_q2_rootfs_sha256": sha(q2root),
        "persistent_q2_cbe904ab_sha256": sha(q2web),
        "origin_mtd5_manifest_sha256": sha(origin),
        "bootenv_wifiaddr_manifest_sha256": sha(bootenv),
        "quantenna_safe_service_manifest_sha256": sha(radio5),
        "qcsapi_runtime_manifest_sha256": sha(stage / "usr/libexec/openmitrastar/qcsapi-runtime/manifest.sha256"),
    },
    "capabilities": {
        "backup_restore": True,
        "http_80": True,
        "https_443_optional_external_pem": True,
        "getinfo_16667": True,
        "api_status_alias": True,
        "front_panel_led_control": True,
        "realtek_v4_payload": True,
        "realtek_2g_autostart_preserved_from_q2": True,
        "autonomous_entropy_af_alg_jitterentropy": True,
        "origin_mtd5_read_only_import": True,
        "origin_psk_to_tmpfs": True,
        "quantenna_rxalign_direct_symbols_payload": True,
        "w3_direct_emac_route_embedded": True,
        "w3_5g_safe_service_embedded": True,
        "qcsapi_control_plane_embedded": True,
        "w3_5g_autostart": autostart,
        "w3_5g_manual_start": not autostart,
        "w3_5g_open_lab": open_lab,
        "w3_tqe_ring_entries": 512 if profile == "open-lab-tqe512" else 256,
        "w3_beacon_preflight": profile == "open-lab-beacon-preflight",
        "w3_beacon_lifetime": profile == "open-lab-beacon-lifetime",
        "bootenv_redundant_read_only_import": True,
        "quantenna_auto_mac_from_bootenv": True,
    },
    "security": {
        "ssh_key_only": True, "psk_bundled": False,
        "radio5_security": "OPEN" if open_lab else "WPA2-PSK-CCMP",
        "radio5_psk_required": not open_lab,
        "private_mac_bundled": False, "https_pem_bundled": False,
        "ioss_reset_pulse_forbidden": True,
        "mtd5_write_path": False,
        "bootenv_write_path": False,
    },
    "contracts": {
        "w3_direct_emac": {"file": str(contract.relative_to(stage)), "sha256": sha(contract)},
        "origin_policy": {"file": "usr/share/openmitrastar/origin-mtd5/current-unit.policy", "sha256": sha(stage / "usr/share/openmitrastar/origin-mtd5/current-unit.policy")},
        "bootenv_producer": {"file": "usr/sbin/om-bootenv-readonly", "sha256": sha(stage / "usr/sbin/om-bootenv-readonly")},
        "api_status_alias": {"file": "www/api/status", "sha256": sha(stage / "www/api/status"), "auth": "same-session-dispatcher", "csrf": "unchanged-not-required-for-readonly-status"},
        "front_panel_led_control": {"file": "usr/sbin/om-ledctl", "sha256": sha(stage / "usr/sbin/om-ledctl"), "contract": "usr/share/openmitrastar/leds/hgw500-leds.json", "physical_windows": 3, "independent_channels": 5, "lower_colour_mapping": "pending-physical-identification"},
        "videobridge_policy": {"file": "usr/sbin/om-videobridge-policy", "sha256": sha(stage / "usr/sbin/om-videobridge-policy"), "init": "etc/init.d/S33-videobridge-policy", "config": "etc/openmitrastar/oem-parity.conf", "runtime": "read-only-status"},
        "qcsapi_runtime": {"file": "usr/libexec/openmitrastar/qcsapi-runtime/manifest.sha256", "sha256": sha(stage / "usr/libexec/openmitrastar/qcsapi-runtime/manifest.sha256"), "dynamic_closure": "uClibc-0.9.29", "psk_bundled": False},
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
cmp -s "$init_a" "$init_b" || { echo 'Q3 initramfs reproducibility mismatch' >&2; exit 5; }

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
export KBUILD_BUILD_HOST=q3-persistent
export KBUILD_BUILD_VERSION=1

build_kernel()
{
	out=$1 init=$2
	cp "$q2_config" "$out/.config"
	cfg="$kernel_src/scripts/config --file $out/.config"
	$cfg --enable BLK_DEV_INITRD --enable POSIX_TIMERS \
		--enable CRYPTO_JITTERENTROPY --enable CRYPTO_USER_API_RNG \
		--enable BLOCK --enable MISC_FILESYSTEMS \
		--enable MTD --enable MTD_ROM --enable MTD_PHYSMAP \
		--enable MTD_PHYSMAP_OF --enable MTD_BLOCK_RO \
		--enable JFFS2_FS --enable JFFS2_ZLIB --enable JFFS2_RTIME \
		--disable MTD_BLOCK \
		--set-str INITRAMFS_SOURCE "$init" \
		--set-val INITRAMFS_ROOT_UID 0 --set-val INITRAMFS_ROOT_GID 0 \
		--set-str LOCALVERSION '-openmitrastar-radiohw' \
		--set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_ramssh
	make -s -C "$kernel_src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
	grep -qx "CONFIG_INITRAMFS_SOURCE=\"$init\"" "$out/.config"
	grep -qx 'CONFIG_POSIX_TIMERS=y' "$out/.config"
	grep -qx 'CONFIG_CRYPTO_JITTERENTROPY=y' "$out/.config"
	grep -qx 'CONFIG_CRYPTO_USER_API_RNG=y' "$out/.config"
	grep -qx 'CONFIG_MTD_ROM=y' "$out/.config"
	grep -qx 'CONFIG_MTD_PHYSMAP_OF=y' "$out/.config"
	grep -qx 'CONFIG_MTD_BLOCK_RO=y' "$out/.config"
	grep -qx 'CONFIG_JFFS2_FS=y' "$out/.config"
	grep -qx '# CONFIG_MTD_BLOCK is not set' "$out/.config"
	grep -qx '# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set' "$out/.config"
	make -s -C "$kernel_src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j"$jobs" uImage.bin
}
build_kernel "$out_a" "$init_a"
build_kernel "$out_b" "$init_b"

for suffix in vmlinux arch/arc/boot/uImage.bin arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb; do
	cmp -s "$out_a/$suffix" "$out_b/$suffix" || { echo "Q3 kernel reproducibility mismatch: $suffix" >&2; exit 6; }
done
require_sha "$out_a/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb" "$expected_bootenv_dtb"
cp "$out_a/arch/arc/boot/uImage.bin" "$uncompressed_uimage"
dd if="$uncompressed_uimage" of="$raw" bs=64 skip=1 status=none

"$legacy_lzma" --keep --best "$raw" -c >"$lzma_a"
"$legacy_lzma" --keep --best "$raw" -c >"$lzma_b"
cmp -s "$lzma_a" "$lzma_b" || { echo 'Q3 LZMA reproducibility mismatch' >&2; exit 6; }
python3 "$make_uimage" "$uncompressed_uimage" "$lzma_a" "$uimage_a"
python3 "$make_uimage" "$uncompressed_uimage" "$lzma_b" "$uimage_b"
cmp -s "$uimage_a" "$uimage_b" || { echo 'Q3 uImage reproducibility mismatch' >&2; exit 6; }
python3 "$pack" "$uimage_a" "$template" "$web_a" >/dev/null
python3 "$pack" "$uimage_b" "$template" "$web_b" >/dev/null
cmp -s "$web_a" "$web_b" || { echo 'Q3 webformat reproducibility mismatch' >&2; exit 6; }

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
result = module.validate_bootbase_slot("q3-persistent-composite", image.read_bytes(), module.PARTITIONS["linux_live"][1])
report = module.image_to_dict(result)
report["candidate_eligible"] = False
report["scope_note"] = "Q3 format/CRC/LZMA/slot guard only; exact-image RAM boot pending"
output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not result.accepted_by_contract:
    raise SystemExit("Q3 candidate rejected by Bootbase contract")
PY

python3 - "$q2_rootfs" "$q2_web" "$origin_manifest" "$bootenv_manifest" "$radio5_manifest" \
	"$rootfs_manifest" "$origin_dts" "$raw" "$lzma" "$uncompressed_uimage" \
	"$uimage" "$web" "$tftp" "$build/bootbase-contract.json" \
	"$build/manifest.json" "$build/ram-layout.json" "$slot_bytes" \
	"$staging_start" "$ddr_end" "$hbm_start" "$hbm_end" <<'PY'
from pathlib import Path
import hashlib, json, lzma, os, struct, sys

(q2_rootfs, q2_web, origin_manifest, bootenv_manifest, radio5_manifest, rootfs_manifest, origin_dts,
 raw_path, lzma_path, source_uimage, uimage_path, web_path, tftp_path,
 contract_path, manifest_path, layout_path) = map(Path, sys.argv[1:17])
slot = int(sys.argv[17])
staging_start = int(sys.argv[18], 0)
ddr_end = int(sys.argv[19], 0)
hbm_start = int(sys.argv[20], 0)
hbm_end = int(sys.argv[21], 0)
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
autostart = os.environ.get("OM_Q3_AUTOSTART", "1") == "1"
if source[64:] != raw or lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
    raise SystemExit("Q3 LZMA exact payload binding failed")
if out[4:6] != src[4:6] or out[10] != 3:
    raise SystemExit("Q3 LZMA load/entry/compression mismatch")
if tftp_path.read_bytes() != web or len(web) > slot or not contract["accepted_by_contract"]:
    raise SystemExit("Q3 TFTP/slot/Bootbase contract failed")

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
def disjoint(a_start, a_end, b_start, b_end):
    return a_end <= b_start or b_end <= a_start
staging_in_ddr = 0x80000000 <= staging_start < staging_end <= ddr_end
staging_vs_image = disjoint(staging_start, staging_end, load_start, load_end)
staging_vs_workspace = disjoint(staging_start, staging_end, probability_start, probability_end)
staging_vs_hbm = disjoint(staging_start, staging_end, hbm_start, hbm_end)
image_vs_workspace = disjoint(load_start, load_end, probability_start, probability_end)
safe = (staging_in_ddr and staging_vs_image and staging_vs_workspace and
        staging_vs_hbm and image_vs_workspace and
        load_start <= entry < load_end and probability_end < ddr_end)
layout = {
    "schema": "openmitrastar.q3-lzma-ram-layout/v1",
    "staging": {"start": f"0x{staging_start:08x}", "end": f"0x{staging_end:08x}"},
    "decompressed_image": {"start": f"0x{load_start:08x}", "end": f"0x{load_end:08x}", "bytes": len(raw), "entry": f"0x{entry:08x}"},
    "lzma_probability_workspace": {"start": f"0x{probability_start:08x}", "end": f"0x{probability_end:08x}", "bytes": probability_bytes, "lc": lc, "lp": lp, "pb": pb},
    "hbm_reserved": {"start": f"0x{hbm_start:08x}", "end": f"0x{hbm_end:08x}"},
    "non_overlap": {
        "staging_vs_decompressed": staging_vs_image,
        "staging_vs_lzma_workspace": staging_vs_workspace,
        "staging_vs_hbm": staging_vs_hbm,
        "decompressed_vs_lzma_workspace": image_vs_workspace,
    },
    "staging_in_ddr": staging_in_ddr,
    "ddr_end": f"0x{ddr_end:08x}", "safe_offline": safe,
}
if not safe:
    raise SystemExit("Q3 RAM layout unsafe")
layout_path.write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n", encoding="utf-8")

manifest = {
    "schema": "openmitrastar.q3-persistent-composite/v1",
    "classification": rootmeta["classification"] if (not autostart or str(rootmeta.get("profile", "")).startswith("open-lab")) else "FLASH-SIZED-Q3-COMPOSITE-HARDWARE-PENDING-NO-FLASH",
    "candidate_eligible": False, "flash_supported": False,
    "hardware_actions": False, "network_actions": False,
    "profile": "Q3_MAINTENANCE_MANUAL_5G" if not autostart else ("Q3_OPEN_LAB_TQE512" if rootmeta.get("profile") == "open-lab-tqe512" else ("Q3_OPEN_LAB_BEACON_PREFLIGHT" if rootmeta.get("profile") == "open-lab-beacon-preflight" else ("Q3_OPEN_LAB_BEACON_LIFETIME" if rootmeta.get("profile") == "open-lab-beacon-lifetime" else ("Q3_OPEN_LAB" if rootmeta.get("profile") == "open-lab" else "Q3_PERSISTENT_ORIGIN_DUAL_RADIO")))),
    "sources": {
        "persistent_q2_rootfs": info(q2_rootfs),
        "persistent_q2_cbe904ab": info(q2_web),
        "origin_mtd5_manifest": info(origin_manifest),
        "bootenv_wifiaddr_manifest": info(bootenv_manifest),
        "quantenna_safe_service_manifest": info(radio5_manifest),
        "q3_rootfs_manifest_sha256": sha(rootfs_manifest),
        "bootenv_and_mtd5_readonly_dts": info(origin_dts),
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
    "protected_q2": {"unchanged": True, "hashes": {"rootfs": sha(q2_rootfs), "persistent_webformat": sha(q2_web)}},
    "runtime_gates": {
        "exact_candidate_ram_boot": "pending",
        "cold_boot_autonomous_entropy": "pending",
        "origin_mtd5_read_only_import": "pending",
        "bootenv_redundant_read_only_import": "pending",
        "quantenna_auto_mac": "pending",
        "origin_psk_consumption_without_logging": "pending",
        "realtek_2g_autostart": "pending",
        "w3_direct_emac_symbols_only": "pending",
        "quantenna_5g_autostart": "pending-exact-image-hardware-validation" if autostart else "disabled-by-build",
        "quantenna_5g_manual_start": "not-applicable" if autostart else "pending-exact-image-hardware-validation",
        "flash": "forbidden-until-new-Q3-hardware-gates",
    },
}
hbm_override = os.environ.get("OM_Q3_HBM_OVERRIDE_PATH", "")
switch_tqe_override = os.environ.get("OM_Q3_SWITCH_TQE_OVERRIDE_PATH", "")
ram_only_overrides = {}
if hbm_override:
    override_path = Path(hbm_override)
    expected_override = os.environ.get("OM_Q3_EXPECTED_HBM_OVERRIDE_SHA256", "")
    if not expected_override or sha(override_path) != expected_override:
        raise SystemExit("Q3 final HBM override binding failed")
    ram_only_overrides["hbm_clear_probe"] = {
        **info(override_path),
        "embedded_sha256": expected_override,
        "flash_actions": False,
        "hardware_validation": "pending",
    }
if switch_tqe_override:
    override_path = Path(switch_tqe_override)
    expected_override = os.environ.get("OM_Q3_EXPECTED_SWITCH_TQE_OVERRIDE_SHA256", "")
    if not expected_override or sha(override_path) != expected_override:
        raise SystemExit("Q3 final switch_tqe override binding failed")
    ram_only_overrides["switch_tqe_dma_cache_fix"] = {
        **info(override_path),
        "embedded_sha256": expected_override,
        "dma_map_page_attrs_in_tqe_rx_pkt_drop": False,
        "replacement": "dma_cache_inv",
        "flash_actions": False,
        "hardware_validation": "pending",
    }
emac_driver_override = os.environ.get("OM_Q3_EMAC_DRIVER_PATH", "")
emac_header_override = os.environ.get("OM_Q3_EMAC_HEADER_PATH", "")
if emac_driver_override:
    driver_path = Path(emac_driver_override)
    header_path = Path(emac_header_override)
    expected_driver = os.environ.get("OM_Q3_EXPECTED_EMAC_DRIVER_SHA256", "")
    expected_header = os.environ.get("OM_Q3_EXPECTED_EMAC_HEADER_SHA256", "")
    if (not expected_driver or not expected_header or
            sha(driver_path) != expected_driver or
            sha(header_path) != expected_header):
        raise SystemExit("Q3 final EMAC source binding failed")
    ram_only_overrides["emac_dual_phy_autoneg"] = {
        "driver": info(driver_path),
        "header": info(header_path),
        "driver_embedded_sha256": expected_driver,
        "header_embedded_sha256": expected_header,
        "ports": ["emac1/irq20/phy3", "emac0/irq19/phy1"],
        "flash_actions": False,
        "hardware_validation": "pending",
    }
if ram_only_overrides:
    manifest["ram_only_overrides"] = ram_only_overrides
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

[ "$(sha "$q2_rootfs")" = "$q2_rootfs_before" ]
[ "$(sha "$q2_web")" = "$q2_web_before" ]

sha256sum "$rootfs" "$build/$base.initramfs.cpio" "$uncompressed_uimage" \
	"$raw" "$lzma" "$uimage" "$web" "$tftp" "$build/bootbase-contract.json" \
	"$build/ram-layout.json" "$build/manifest.json" >"$build/SHA256SUMS"

python3 "$workspace/tools/test_q3_persistent_composite.py"
printf 'OMQ3_PERSISTENT_COMPOSITE_BUILD_PASS sha256=%s bytes=%s spare=%s rootfs_sha256=%s q2_unchanged=1 flash=0 hardware=0\n' \
	"$(sha "$web")" "$(wc -c <"$web")" "$((slot_bytes - $(wc -c <"$web")))" "$(sha "$rootfs")"
