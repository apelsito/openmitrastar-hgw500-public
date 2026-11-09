#!/bin/sh

# Build the RAM-only Q3 maintenance image.  Linux, Ethernet, SSH and the
# preserved Q2 2.4 GHz path start normally; the Quantenna 5 GHz service and
# diagnostics remain embedded but require an explicit manual start.
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tag=q3-maintenance-v1

export OM_Q3_AUTOSTART=0
export OM_Q3_LANE=${OM_Q3_LANE:-$workspace/work/mission-state/$tag}
export OM_Q3_STAGE_A=${OM_Q3_STAGE_A:-/home/user/openmitrastar-build/$tag/rootfs-a}
export OM_Q3_STAGE_B=${OM_Q3_STAGE_B:-/home/user/openmitrastar-build/$tag/rootfs-b}
export OM_Q3_ORIGIN_STAGE_A=${OM_Q3_ORIGIN_STAGE_A:-/home/user/openmitrastar-build/$tag/origin-a}
export OM_Q3_ORIGIN_STAGE_B=${OM_Q3_ORIGIN_STAGE_B:-/home/user/openmitrastar-build/$tag/origin-b}
export OM_Q3_KERNEL_BUILD_ROOT=${OM_Q3_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/$tag/kernel}
export OM_Q3_KERNEL_SOURCE_SNAPSHOT=${OM_Q3_KERNEL_SOURCE_SNAPSHOT:-/home/user/openmitrastar-build/$tag/linux-src}
export OM_Q3_BASE_NAME=${OM_Q3_BASE_NAME:-openmitrastar-linux510-q3-maintenance-v1-RAM-ONLY-NO-FLASH}
export OM_Q3_TFTP_PATH=${OM_Q3_TFTP_PATH:-$workspace/work/tftp/omvl/linux510-q3-maintenance-v1-RAM-TEST-NO-FLASH.bin}

exec sh "$workspace/tools/build_q3_pm0_calibration_v1.sh"
