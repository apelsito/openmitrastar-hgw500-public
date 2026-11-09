#!/usr/bin/env python3
from pathlib import Path
import run_qtn_w3_fwt_tdes_probe as base

base.ART=base.ROOT/"outputs/kernel-port/quantenna-linux510-v89-radiohw-fwt-reflectprobe-20260818-0215"
base.MANIFEST=base.ROOT/"work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_REFLECTPROBE_SIGNED_ARTIFACT.json"
base.CLOSED=base.ROOT/"work/mission-state/w3-offline/W3_FWT_REFLECT_PROBE_GATE.env"
base.APPROVED=base.ROOT/"work/mission-state/w3-offline/W3_FWT_REFLECT_PROBE_GATE.approved.env"
base.REMOTE=base.ROOT/"tools/qtn_w3_fwt_reflect_probe_remote.sh"
base.ACK="OPENMITRASTAR_QTN_W3_FWT_REFLECT_PROBE"
base.PROBE_DESCRIPTION="TOPAZ_TQE_MISC reflect-to-LHOST single-mode then exact restore"
base.REMOTE_ROOT="/tmp/w3-qtn-reflect"
base.REMOTE_GATE_NAME="W3_FWT_REFLECT_PROBE_GATE.env"
base.REMOTE_SCRIPT_NAME="qtn_w3_fwt_reflect_probe_remote.sh"
base.UART_TAG="w3-fwt-reflect"
base.DRY_MARKER="W3_FWT_REFLECT_PROBE_DRY_RUN_PASS"
base.PASS_MARKER="W3_FWT_REFLECT_PROBE_PASS"

if __name__=="__main__":
    raise SystemExit(base.main())
