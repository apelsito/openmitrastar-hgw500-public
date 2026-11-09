#!/bin/sh

# RAM-only Q3 maintenance variant derived from q3-maintenance-hbm-clear-v1.
# It keeps the HBM clear discriminator and replaces only switch_tqe.ko with
# the ARC cache-maintenance build that cannot call dma_map_page_attrs(NULL).
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tag=q3-maintenance-hbm-clear-tqe-dma-v1
hbm="$workspace/outputs/kernel-port/qtn-hbm-clear-probe-20260821/hbm.ko"
switch_tqe="$workspace/outputs/kernel-port/qtn-switch-tqe-dma-device-fix-20260821/switch_tqe.ko"

export OM_Q3_AUTOSTART=0
export OM_Q3_STAGING_START=0x87000000
export OM_Q3_HBM_OVERRIDE_PATH="$hbm"
export OM_Q3_EXPECTED_HBM_OVERRIDE_SHA256=f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8
export OM_Q3_SWITCH_TQE_OVERRIDE_PATH="$switch_tqe"
export OM_Q3_EXPECTED_SWITCH_TQE_OVERRIDE_SHA256=368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74
export OM_Q3_MAINTENANCE_S53_PATH="$workspace/work/mission-state/q3-maintenance-orchestration/rootfs/etc/init.d/S53-qtn-calibration"
export OM_Q3_MAINTENANCE_S54_PATH="$workspace/work/mission-state/q3-maintenance-orchestration/rootfs/etc/init.d/S54-qtn-mac"
export OM_Q3_EXPECTED_MAINTENANCE_S53_SHA256=23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404
export OM_Q3_EXPECTED_MAINTENANCE_S54_SHA256=cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d
export OM_Q3_LANE=${OM_Q3_LANE:-$workspace/work/mission-state/$tag}
export OM_Q3_STAGE_A=${OM_Q3_STAGE_A:-/home/user/openmitrastar-build/$tag/rootfs-a}
export OM_Q3_STAGE_B=${OM_Q3_STAGE_B:-/home/user/openmitrastar-build/$tag/rootfs-b}
export OM_Q3_ORIGIN_STAGE_A=${OM_Q3_ORIGIN_STAGE_A:-/home/user/openmitrastar-build/$tag/origin-a}
export OM_Q3_ORIGIN_STAGE_B=${OM_Q3_ORIGIN_STAGE_B:-/home/user/openmitrastar-build/$tag/origin-b}
export OM_Q3_KERNEL_BUILD_ROOT=${OM_Q3_KERNEL_BUILD_ROOT:-/home/user/openmitrastar-build/$tag/kernel}
export OM_Q3_KERNEL_SOURCE_SNAPSHOT=${OM_Q3_KERNEL_SOURCE_SNAPSHOT:-/home/user/openmitrastar-build/$tag/linux-src}
export OM_Q3_BASE_NAME=${OM_Q3_BASE_NAME:-openmitrastar-linux510-q3-maintenance-hbm-clear-tqe-dma-v1-RAM-ONLY-NO-FLASH}
export OM_Q3_TFTP_PATH=${OM_Q3_TFTP_PATH:-$workspace/work/tftp/omvl/linux510-q3-maintenance-hbm-clear-tqe-dma-v1-RAM-TEST-NO-FLASH.bin}

sh "$workspace/tools/build_q3_pm0_calibration_v1.sh"
python3 "$workspace/tools/test_q3_hbm_clear_tqe_dma_variant.py"
