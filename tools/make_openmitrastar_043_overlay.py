#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.3 with compatible firmware upload.

0.4.2 proved the modern UI shape, but firmware upload was too clever: the
stock firmware.cgi binary was moved to /api/flash. On this firmware the proven
path is the original .cgi backend plus its template, so 0.4.3 keeps the SPA as
the UX and restores firmware.cgi as a hidden compatibility backend.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_042_overlay.py"

spec = importlib.util.spec_from_file_location("omt042", BASE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
base = mod.base

base.VERSION = "openmitrastar-0.4.3-modern-ui-full-flashfix"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

base.INDEX_HTML = base.INDEX_HTML.replace(
    '<form method="post" enctype="multipart/form-data" action="/api/flash" class="flash">',
    '<form method="post" enctype="multipart/form-data" action="/firmware.cgi" class="flash">',
)

base.MINIHTTPD = """ # mini_httpd configuration file
data_dir=/var/www
port=80
host=0.0.0.0
cgipat=**/api/*|**.cgi|**.php
charset=UTF-8
certfile=/etc/minihttpd.pem
"""

base.MINIHTTPD_SSL = """ # mini_httpd configuration file
data_dir=/var/www
port=443
host=0.0.0.0
cgipat=**/api/*|**.cgi|**.php
charset=UTF-8
ssl
certfile=/etc/minihttpd.pem
"""

base.API_FLASH = r"""#!/bin/sh
. /var/www/api/_lib
header_json
echo '{"ok":true,"backend":"firmware.cgi","message":"Use the stock-compatible /firmware.cgi multipart endpoint for firmware uploads. The modern UI posts there directly."}'
"""

_copy_runtime = base.copy_runtime
_write_web = base.write_web


def copy_runtime_043() -> None:
    _copy_runtime()
    base.write(
        base.OVERLAY / "etc" / "minihttpd.conf",
        base.MINIHTTPD,
    )
    base.write(
        base.OVERLAY / "etc" / "minihttpd_ssl.conf",
        base.MINIHTTPD_SSL,
    )
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.3-modern-ui-full-flashfix\n"
        "OPENMITRASTAR_MODE=modern-ui-full-flashfix\n",
    )


def write_web_043() -> None:
    _write_web()
    www = base.OVERLAY / "var" / "www"
    flash_api = www / "api" / "flash"
    if flash_api.exists():
        flash_api.unlink()
    base.write(flash_api, base.API_FLASH, 0o755)
    shutil.copy2(base.SRC_WWW / "firmware.cgi", www / "firmware.cgi")
    (www / "firmware.cgi").chmod(0o755)


base.copy_runtime = copy_runtime_043
base.write_web = write_web_043


if __name__ == "__main__":
    raise SystemExit(base.main())
