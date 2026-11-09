#!/bin/sh

# Separate RAM-only Q3 maintenance discriminator. It preserves the canonical
# f072... image and changes only hbm.ko plus the declared RAM staging address.
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tag=q3-maintenance-hbm-clear-v1
hbm="$workspace/outputs/kernel-port/qtn-hbm-clear-probe-20260821/hbm.ko"

export OM_Q3_AUTOSTART=0
export OM_Q3_STAGING_START=0x87000000
export OM_Q3_HBM_OVERRIDE_PATH="$hbm"
export OM_Q3_EXPECTED_HBM_OVERRIDE_SHA256=f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8
export OM_Q3_LANE=${OM_Q3_LANE:-$workspace/work/mission-state/$tag}
export OM_Q3_STAGE_A=${OM_Q3_STAGE_A:-/home/user/openmitrastar-build/$tag/rootfs-a}
export OM_Q3_STAGE_B=${OM_Q3_STAGE_B:-/home/user/openmitrastar-build/$tag/rootfs-b}
export OM_Q3_ORIGIN_STAGE_A=${OM_Q3_ORIGIN_STAGE_A:-/home/user/openmitrastar-build/$tag/origin-a}
export OM_Q3_ORIGIN_STAGE_B=${OM_Q3_ORIGIN_STAGE_B:-/home/user/openmitrastar-build/$tag/origin-b}
export OM_Q3_KERNEL_BUILD_ROOT=${OM_Q3_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/$tag/kernel}
export OM_Q3_KERNEL_SOURCE_SNAPSHOT=${OM_Q3_KERNEL_SOURCE_SNAPSHOT:-/home/user/openmitrastar-build/$tag/linux-src}
export OM_Q3_BASE_NAME=${OM_Q3_BASE_NAME:-openmitrastar-linux510-q3-maintenance-hbm-clear-v1-RAM-ONLY-NO-FLASH}
export OM_Q3_TFTP_PATH=${OM_Q3_TFTP_PATH:-$workspace/work/tftp/omvl/linux510-q3-maintenance-hbm-clear-v1-RAM-TEST-NO-FLASH.bin}

sh "$workspace/tools/build_q3_pm0_calibration_v1.sh"
python3 "$workspace/tools/test_q3_hbm_clear_variant.py"
