#!/bin/sh

# Separate RAM-only PM0 composition with the observational GPIO4 module.
# The module is present but never autoloaded.
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tag=q3-pm0-gpio4-diag-20260821

export OM_Q3_GPIO4_DIAG_OVERLAY_PATH="$workspace/outputs/kernel-port/hgw500-gpio4-diag-20260821/hgw500-gpio4-diag-rootfs-overlay.tar.gz"
export OM_Q3_EXPECTED_GPIO4_DIAG_OVERLAY_SHA256=e8b4bb724658a86f8553a020b68e1bd0659feb487ae739f7ed78880471f7cfc7
export OM_Q3_LANE="$workspace/work/mission-state/$tag"
export OM_Q3_STAGE_A="/home/user/openmitrastar-build/$tag/rootfs-a"
export OM_Q3_STAGE_B="/home/user/openmitrastar-build/$tag/rootfs-b"
export OM_Q3_ORIGIN_STAGE_A="/home/user/openmitrastar-build/$tag/origin-a"
export OM_Q3_ORIGIN_STAGE_B="/home/user/openmitrastar-build/$tag/origin-b"
export OM_Q3_KERNEL_BUILD_ROOT="/home/user/openmitrastar-build/$tag/kernel"
export OM_Q3_KERNEL_SOURCE_SNAPSHOT="/home/user/openmitrastar-build/$tag/linux-src"
export OM_Q3_BASE_NAME=openmitrastar-linux510-q3-pm0-gpio4-diag-RAM-ONLY-NO-FLASH
export OM_Q3_TFTP_PATH="$workspace/work/tftp/omvl/linux510-q3-pm0-gpio4-diag-RAM-TEST-NO-FLASH.bin"

exec sh "$workspace/tools/build_q3_pm0_calibration_v1.sh"
