#!/usr/bin/env python3
"""Build F132 from F129 with the corrected HRFLAGS skip branch target."""
from __future__ import annotations

import build_f131_5g_hrflags_skip_from_f129 as base


BUILD_TAG = "f132-5g-hrflags-skip-epilogue-from-f129"
OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F132_FROM_F129_5G_HRFLAGS_SKIP_EPILOGUE"
FIX_LABEL = "5g-hgw-v89-skip-hrflags-one-shot-correct-epilogue-branch"


def main() -> int:
    base.BUILD_TAG = BUILD_TAG
    base.OUT = OUT
    base.BASE_OUT = BASE_OUT
    base.CLASSIFICATION = CLASSIFICATION
    base.FIX_LABEL = FIX_LABEL
    base.NEW_BRANCH_TO_EPILOGUE = bytes.fromhex("11 f0")
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
