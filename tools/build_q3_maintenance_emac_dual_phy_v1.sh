#!/bin/sh

# RAM-only Q3 maintenance image with the exact HGW-500BNA dual-EMAC/PHY
# recovery path.  This variant is intentionally separate from ce04697a and
# may never be used as a flash input before its hardware gate passes.
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tag=q3-maintenance-hbm-clear-tqe-dma-emac-aneg-v1
lane="$workspace/work/mission-state/$tag"
controls="$lane/inputs/controls"
dts="$workspace/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
controls_driver="$workspace/outputs/kernel-port/hgw500-controls-oem-gpio4-20260821/qtn-topaz-recovery.c"
emac_driver="$workspace/work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
emac_header="$workspace/work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h"
hbm="$workspace/outputs/kernel-port/qtn-hbm-clear-probe-20260821/hbm.ko"
switch_tqe="$workspace/outputs/kernel-port/qtn-switch-tqe-dma-device-fix-20260821/switch_tqe.ko"
overlay_dir="$workspace/work/mission-state/q3-calibration-overlay/build"
overlay="$overlay_dir/openmitrastar-q3-dual-radio-open-lab-beacon-lifetime-overlay.tar.gz"
overlay_manifest="$overlay_dir/manifest.json"
radio_start="$workspace/work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start"

sha()
{
	sha256sum "$1" | awk '{print $1}'
}

require_sha()
{
	path=$1 expected=$2
	actual=$(sha "$path")
	[ "$actual" = "$expected" ] || {
		printf 'EMAC variant input drift: %s expected=%s actual=%s\n' \
			"$path" "$expected" "$actual" >&2
		exit 3
	}
}

require_sha "$dts" a8279d0b9d2b8a6eb38ffc85c5b190f9c3934fca620fe38b83fca535aafee0b6
require_sha "$controls_driver" 41f8b6b16a1030ef68804341439d9d87c766319079edc2db95163892c16f1445
require_sha "$emac_driver" c73895be6a61da6f86439d8a5c5a550368bd8a0158295e6395b94953734d3993
require_sha "$emac_header" 59e06f782d8afa0eb0da5db7a9723d28c82678fe422dd51f34d7914b8a9f18c9
mkdir -p "$controls"
cp "$dts" "$controls/topaz_mitrastar_ramssh.dts"
cp "$controls_driver" "$controls/qtn-topaz-recovery.c"

export OM_Q3_AUTOSTART=0
export OM_Q3_STAGING_START=0x87000000
export OM_Q3_PROFILE=open-lab-beacon-lifetime
export OM_Q3_HBM_OVERRIDE_PATH="$hbm"
export OM_Q3_EXPECTED_HBM_OVERRIDE_SHA256=f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8
export OM_Q3_SWITCH_TQE_OVERRIDE_PATH="$switch_tqe"
export OM_Q3_EXPECTED_SWITCH_TQE_OVERRIDE_SHA256=368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74
export OM_Q3_MAINTENANCE_S53_PATH="$workspace/work/mission-state/q3-maintenance-orchestration/rootfs/etc/init.d/S53-qtn-calibration"
export OM_Q3_MAINTENANCE_S54_PATH="$workspace/work/mission-state/q3-maintenance-orchestration/rootfs/etc/init.d/S54-qtn-mac"
export OM_Q3_EXPECTED_MAINTENANCE_S53_SHA256=23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404
export OM_Q3_EXPECTED_MAINTENANCE_S54_SHA256=cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d
export OM_Q3_RADIO5_OVERLAY_PATH="$overlay"
export OM_Q3_RADIO5_MANIFEST_PATH="$overlay_manifest"
export OM_Q3_RADIO5_START_PATH="$radio_start"
export OM_Q3_EXPECTED_RADIO5_OVERLAY_SHA256=bd79cdbe482f1db77929611fced9875a0892b651c9bc93212e27e7b34598d5da
export OM_Q3_EXPECTED_RADIO5_MANIFEST_SHA256=13798602c6175f9bb3c040644d10c14a706f058a23e2f065b0c9aff618f425d0
export OM_Q3_EXPECTED_RADIO5_START_SHA256=80ab5867412ac7103bde9e3ba31cffbe064daf1b7bf3b993cbb0e4b0cd7c59c8
export OM_Q3_EXPECTED_RADIO5_S55_SHA256=c8aa49d42f0ae5b4b851060e8cad1954592b12c48b4ff56965a3c284af2c8002
export OM_Q3_EXPECTED_RADIO5_S53_SHA256=056dcc1034429419e32f16bb052340f69dde22859abd836c20386a5a2fb41b11
export OM_Q3_EXPECTED_QTN_CAL_PRODUCER_SHA256=d0d15a9484e8e706bb42b9fa977ef66bf0cac1d94fcf7a0f9d85fe49d3662a24
export OM_Q3_CONTROLS_ARTIFACT="$controls"
export OM_Q3_EXPECTED_CONTROLS_DRIVER_SHA256=41f8b6b16a1030ef68804341439d9d87c766319079edc2db95163892c16f1445
export OM_Q3_EXPECTED_CONTROLS_DTS_SHA256=a8279d0b9d2b8a6eb38ffc85c5b190f9c3934fca620fe38b83fca535aafee0b6
export OM_Q3_EXPECTED_CONTROLS_DTB_SHA256=7fa81f07fb13aa0d4caf549ce0e0d9fbb82bdee5f06f437a779309a4173f6d83
export OM_Q3_EMAC_DRIVER_PATH="$emac_driver"
export OM_Q3_EXPECTED_EMAC_DRIVER_SHA256=c73895be6a61da6f86439d8a5c5a550368bd8a0158295e6395b94953734d3993
export OM_Q3_EMAC_HEADER_PATH="$emac_header"
export OM_Q3_EXPECTED_EMAC_HEADER_SHA256=59e06f782d8afa0eb0da5db7a9723d28c82678fe422dd51f34d7914b8a9f18c9
export OM_Q3_LANE="$lane"
export OM_Q3_STAGE_A=/home/user/openmitrastar-build/$tag/rootfs-a
export OM_Q3_STAGE_B=/home/user/openmitrastar-build/$tag/rootfs-b
export OM_Q3_ORIGIN_STAGE_A=/home/user/openmitrastar-build/$tag/origin-a
export OM_Q3_ORIGIN_STAGE_B=/home/user/openmitrastar-build/$tag/origin-b
export OM_Q3_KERNEL_BUILD_ROOT=/home/user/openmitrastar-build/$tag/kernel
export OM_Q3_KERNEL_SOURCE_SNAPSHOT=/home/user/openmitrastar-build/$tag/linux-src
export OM_Q3_BASE_NAME=openmitrastar-linux510-q3-maintenance-hbm-clear-tqe-dma-emac-aneg-v1-RAM-ONLY-NO-FLASH
export OM_Q3_TFTP_PATH="$workspace/work/tftp/omvl/linux510-q3-maintenance-hbm-clear-tqe-dma-emac-aneg-v1-RAM-TEST-NO-FLASH.bin"

exec sh "$workspace/tools/build_q3_persistent_composite.sh"
