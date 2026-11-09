#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.6 with HTTP 1.30 plus preserved HTTPS SSL.

0.4.5 proved mini_httpd 1.30 works for clean /api/* endpoints, but the build is
not SSL-enabled. 0.4.6 keeps 1.30 for HTTP/API and ships the provider SSL-capable
mini_httpd as /sbin/mini_httpd_ssl for port 443.
"""

from __future__ import annotations

import importlib.util
import os
import shutil


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_045_overlay.py"
STOCK_SSL_HTTPD = ROOT / "work" / "revival" / "rootfs" / "sbin" / "mini_httpd"

spec = importlib.util.spec_from_file_location("omt045", BASE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
base = mod.base

base.VERSION = "openmitrastar-0.4.6-http130-https-stockssl"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

S92HTTPD = """#!/bin/sh
kill_process() {
        pid_name=$1
        pid=`ps | grep "$pid_name" | grep -v grep | awk '{print $1}'`
        [ -n "$pid" ] && kill $pid
}
start() {
        export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts:/usr/local/bin
        export LD_LIBRARY_PATH=/lib:/usr/lib
        platform_file=/scripts/platform_id
        [ -f $platform_file ] && platform_id=`cat $platform_file` || platform_id=00
        if [ "$platform_id" != "425" ]; then
                if [ ! -f /mnt/jffs2/httpd-disabled ]; then
                        echo "Starting OpenMitraStar HTTP/HTTPS"
                        cp -f /etc/minihttpd.conf /mnt/jffs2/minihttpd.conf
                        [ ! -f /mnt/jffs2/admin.conf ] && cp -f /etc/admin.conf /mnt/jffs2/admin.conf
                        if [ -f /sbin/mini_httpd ] ; then
                                /sbin/mini_httpd -u root -C /mnt/jffs2/minihttpd.conf
                        fi
                        if [ -f /sbin/mini_httpd_ssl ] ; then
                                /sbin/mini_httpd_ssl -u root -C /etc/minihttpd_ssl.conf
                        fi
                else
                        echo "httpd is not enabled"
                fi
        fi
}
stop() { echo "Stopping httpd"; kill_process "mini_httpd"; }
restart() { stop; start; }
case "$1" in start) start;; stop) stop;; restart|reload) restart;; *) echo "Usage: $0 {start|stop|restart}"; exit 1;; esac
exit $?
"""

_copy_runtime = base.copy_runtime


def copy_runtime_046() -> None:
    _copy_runtime()
    if not STOCK_SSL_HTTPD.exists():
        raise FileNotFoundError(STOCK_SSL_HTTPD)
    sbin = base.OVERLAY / "sbin"
    sbin.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STOCK_SSL_HTTPD, sbin / "mini_httpd_ssl")
    os.chmod(sbin / "mini_httpd_ssl", 0o755)
    base.write(base.OVERLAY / "etc" / "init.d" / "S92httpd", S92HTTPD, 0o755)
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.6-http130-https-stockssl\n"
        "OPENMITRASTAR_MODE=http-minihttpd-1.30-https-stockssl\n",
    )


base.copy_runtime = copy_runtime_046


if __name__ == "__main__":
    raise SystemExit(base.main())
