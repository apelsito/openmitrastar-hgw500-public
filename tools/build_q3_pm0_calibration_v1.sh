#!/bin/sh

# One-command offline composition of the latest PM0 association trace plus the
# read-only V8.1 calibration importer. It does not boot hardware or write flash.
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
overlay_dir="$workspace/work/mission-state/q3-calibration-overlay/build"
overlay="$overlay_dir/openmitrastar-q3-dual-radio-open-lab-beacon-lifetime-overlay.tar.gz"
overlay_manifest="$overlay_dir/manifest.json"
radio_start="$workspace/work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start"

test -f "$overlay"
test -f "$overlay_manifest"
test -f "$radio_start"

export OM_Q3_PROFILE=open-lab-beacon-lifetime
export OM_Q3_LANE=${OM_Q3_LANE:-$workspace/work/mission-state/q3-pm0-calibration-v1}
export OM_Q3_STAGE_A=${OM_Q3_STAGE_A:-/home/user/openmitrastar-build/q3-pm0-calibration-v1/rootfs-a}
export OM_Q3_STAGE_B=${OM_Q3_STAGE_B:-/home/user/openmitrastar-build/q3-pm0-calibration-v1/rootfs-b}
export OM_Q3_ORIGIN_STAGE_A=${OM_Q3_ORIGIN_STAGE_A:-/home/user/openmitrastar-build/q3-pm0-calibration-v1/origin-a}
export OM_Q3_ORIGIN_STAGE_B=${OM_Q3_ORIGIN_STAGE_B:-/home/user/openmitrastar-build/q3-pm0-calibration-v1/origin-b}
export OM_Q3_KERNEL_BUILD_ROOT=${OM_Q3_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/q3-pm0-calibration-v1/kernel}
export OM_Q3_KERNEL_SOURCE_SNAPSHOT=${OM_Q3_KERNEL_SOURCE_SNAPSHOT:-/home/user/openmitrastar-build/q3-pm0-calibration-v1/linux-src}
export OM_Q3_BASE_NAME=${OM_Q3_BASE_NAME:-openmitrastar-linux510-q3-pm0-calibration-v1-LZMA-OFFLINE-NO-FLASH}
export OM_Q3_TFTP_PATH=${OM_Q3_TFTP_PATH:-$workspace/work/tftp/omvl/linux510-q3-pm0-calibration-v1-RAM-TEST-NO-FLASH.bin}
export OM_Q3_RADIO5_OVERLAY_PATH="$overlay"
export OM_Q3_RADIO5_MANIFEST_PATH="$overlay_manifest"
export OM_Q3_RADIO5_START_PATH="$radio_start"
export OM_Q3_EXPECTED_RADIO5_OVERLAY_SHA256=bd79cdbe482f1db77929611fced9875a0892b651c9bc93212e27e7b34598d5da
export OM_Q3_EXPECTED_RADIO5_MANIFEST_SHA256=13798602c6175f9bb3c040644d10c14a706f058a23e2f065b0c9aff618f425d0
export OM_Q3_EXPECTED_RADIO5_START_SHA256=80ab5867412ac7103bde9e3ba31cffbe064daf1b7bf3b993cbb0e4b0cd7c59c8
export OM_Q3_EXPECTED_RADIO5_S55_SHA256=c8aa49d42f0ae5b4b851060e8cad1954592b12c48b4ff56965a3c284af2c8002
export OM_Q3_EXPECTED_RADIO5_S53_SHA256=056dcc1034429419e32f16bb052340f69dde22859abd836c20386a5a2fb41b11
export OM_Q3_EXPECTED_QTN_CAL_PRODUCER_SHA256=d0d15a9484e8e706bb42b9fa977ef66bf0cac1d94fcf7a0f9d85fe49d3662a24
export OM_Q3_EXPECTED_CONTROLS_DRIVER_SHA256=1d7aee9231741fa32e6df0c3d2321b3fe65278a880e9b1a4ce85d88b8fff2e3e
export OM_Q3_EXPECTED_CONTROLS_DTS_SHA256=a8279d0b9d2b8a6eb38ffc85c5b190f9c3934fca620fe38b83fca535aafee0b6
export OM_Q3_EXPECTED_CONTROLS_DTB_SHA256=7fa81f07fb13aa0d4caf549ce0e0d9fbb82bdee5f06f437a779309a4173f6d83

exec sh "$workspace/tools/build_q3_persistent_composite.sh"
