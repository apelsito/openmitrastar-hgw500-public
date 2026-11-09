#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.2 with bin-aware backup mode.

0.4.2 keeps the full 0.4.1 UI but fixes backup mode to expose the actual
partition reality observed in the verified dump: linux_safety, linux_live and
rootfs_live are separate raw artifacts, while the provider webformat is a
prefix of linux_safety.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_041_overlay.py"

spec = importlib.util.spec_from_file_location("omt041", BASE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
base = mod.base

base.VERSION = "openmitrastar-0.4.2-modern-ui-full-binaware"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

base.INDEX_HTML = base.INDEX_HTML.replace(
    '<a class="button" href="/api/backup/firmware">Download raw firmware dump</a>',
    '<a class="button" href="/api/backup/firmware?part=safety">Dump linux_safety</a>'
    '<a class="button" href="/api/backup/firmware?part=live">Dump linux_live</a>'
    '<a class="button" href="/api/backup/firmware?part=rootfs">Dump rootfs_live</a>',
)

base.API_BACKUP_FIRMWARE = r"""#!/bin/sh
. /var/www/api/_lib
part_req="$(printf '%s' "$QUERY_STRING" | tr '&' '\n' | sed -n 's/^part=//p' | head -n1)"
case "$part_req" in
  safety) name="linux_safety"; file="openmitrastar-linux_safety-raw.bin" ;;
  live|"") name="linux_live"; file="openmitrastar-linux_live-raw.bin" ;;
  rootfs) name="rootfs_live"; file="openmitrastar-rootfs_live-raw.bin" ;;
  data) name="data"; file="openmitrastar-data-raw.bin" ;;
  *) name="linux_live"; file="openmitrastar-linux_live-raw.bin" ;;
esac
part="$(grep "\"$name\"" /proc/mtd 2>/dev/null | awk -F: '{print $1}' | head -n1)"
header_bin "$file"
if [ -n "$part" ] && [ -e "/dev/$part" ]; then
  cat "/dev/$part"
else
  echo "partition $name not found"
fi
"""

_copy_runtime = base.copy_runtime


def copy_runtime_042() -> None:
    _copy_runtime()
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.2-modern-ui-full-binaware\n"
        "OPENMITRASTAR_MODE=modern-ui-full-binaware\n",
    )


base.copy_runtime = copy_runtime_042


if __name__ == "__main__":
    raise SystemExit(base.main())
