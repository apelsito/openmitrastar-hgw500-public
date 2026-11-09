#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.7 ops stability build.

This version keeps the proven 0.4.6 HTTP/HTTPS stack and does not replace
Dropbear: tested Dropbear 2019/2020/2022/2026 server builds segfault on this
ARC/uClibc runtime after hostkey loading. 0.4.7 instead improves the operations
plane safely: fixed JSON escaping, persistent fast profile, lightweight service
watchdog, and explicit release notes.
"""

from __future__ import annotations

import importlib.util


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_046_overlay.py"

spec = importlib.util.spec_from_file_location("omt046", BASE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
base = mod.base

base.VERSION = "openmitrastar-0.4.7-ops-stability"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

API_LIB = r"""#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH
json_escape() { awk 'BEGIN{ORS=""}{gsub(/\\/,"\\\\"); gsub(/"/,"\\\""); gsub(/\r/," "); if(NR>1) printf " "; printf "%s",$0}'; }
header_json() { echo "Content-Type: application/json"; echo "Cache-Control: no-store"; echo; }
header_bin() { echo "Content-Type: application/octet-stream"; echo "Cache-Control: no-store"; echo "Content-Disposition: attachment; filename=\"$1\""; echo; }
url_decode_common() { sed 's/+/ /g;s/%2F/\//g;s/%2f/\//g;s/%3A/:/g;s/%3a/:/g;s/%2E/./g;s/%2e/./g;s/%2D/-/g;s/%2d/-/g;s/%5F/_/g;s/%5f/_/g;s/%20/ /g'; }
kv_from() {
  source="$1"; key="$2"
  for pair in $(echo "$source" | sed 's/&/ /g'); do
    case "$pair" in "$key="*) echo "${pair#*=}" | url_decode_common; return 0;; esac
  done
  return 0
}
kv() { kv_from "$BODY" "$1"; }
qv() { kv_from "$QUERY_STRING" "$1"; }
read_body() { BODY=""; [ -n "$CONTENT_LENGTH" ] && BODY="$(dd bs=1 count="$CONTENT_LENGTH" 2>/dev/null)"; }
pid_state() { p="$(ps | grep "$1" | grep -v grep | awk 'NR==1{print $1}')"; [ -n "$p" ] && echo "running:$p" || echo "stopped"; }
"""

OPENMITRASTAR_CONF = """# Open MitraStar fast operations profile.
# Runtime rollback: touch /mnt/ccc/openmitrastar-disable && reboot

OPENMITRASTAR_PROFILE=fast
OPENMITRASTAR_PRESERVE_CONFIG=1
OPENMITRASTAR_DISABLE_TR069=1
OPENMITRASTAR_DISABLE_QHARVESTD=1
OPENMITRASTAR_DISABLE_PKTLOGGER=1
OPENMITRASTAR_SINGLE_HTTPD=0
OPENMITRASTAR_APPLY_DELAY=15
OPENMITRASTAR_WATCHDOG_INTERVAL=90
"""

WATCHDOG = r"""#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH

CONF=/etc/openmitrastar.conf
DISABLE_FLAG=/mnt/ccc/openmitrastar-disable
LOG=/tmp/openmitrastar-watchdog.log

[ -f "$CONF" ] && . "$CONF"
: ${OPENMITRASTAR_WATCHDOG_INTERVAL:=90}

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null) openmitrastar-watchdog: $*" >> "$LOG"
}

dropbear_listening() {
    netstat -an 2>/dev/null | grep -q '0\.0\.0\.0:22 .*LISTEN'
}

start_dropbear_if_needed() {
    dropbear_listening && return 0
    if [ -x /usr/sbin/dropbear ]; then
        log "dropbear port 22 not listening; starting stock server"
        /usr/sbin/dropbear -r /etc/mycert/ssh.rsa -p 22 -P /var/run/dropbear.pid >/dev/null 2>&1
    fi
}

(
    sleep 20
    while true; do
        [ -f "$DISABLE_FLAG" ] && exit 0
        OPENMITRASTAR_PROFILE=fast /scripts/openmitrastar-apply now >/dev/null 2>&1
        start_dropbear_if_needed
        sleep "$OPENMITRASTAR_WATCHDOG_INTERVAL"
    done
) &

exit 0
"""

S93WATCHDOG = """#!/bin/sh
case "$1" in
  start)
    [ -x /scripts/openmitrastar-watchdog ] && /scripts/openmitrastar-watchdog
    ;;
  stop)
    for pid in $(ps | grep openmitrastar-watchdog | grep -v grep | awk '{print $1}'); do
      kill "$pid" 2>/dev/null
    done
    ;;
  restart|reload)
    $0 stop
    $0 start
    ;;
  *)
    echo "Usage: $0 {start|stop|restart}"
    exit 1
    ;;
esac
exit 0
"""

NOTES = """# OpenMitraStar 0.4.7 - ops stability

This build keeps the 0.4.6 HTTP/HTTPS stack and original stock Dropbear server.

Validated decision:
- Dropbear 2026.94, 2022.83, 2020.81, and 2019.78 were cross-compiled on the PC for ARC/uClibc.
- Each binary executed help/version output on the router.
- Each server build segfaulted on the router after crypto init and hostkey loading, before listening.
- Therefore no unproven Dropbear replacement is packaged in this firmware.

Included changes:
- Fixed BusyBox-compatible JSON escaping for /api/status.
- Default profile is fast.
- Lightweight watchdog reapplies service reductions and restarts stock Dropbear if port 22 is not listening.
- No secrets are emitted in UI/API output.
"""

_copy_runtime = base.copy_runtime
_write_web = base.write_web


def copy_runtime_047() -> None:
    _copy_runtime()
    base.write(base.OVERLAY / "etc" / "openmitrastar.conf", OPENMITRASTAR_CONF)
    base.write(base.OVERLAY / "scripts" / "openmitrastar-watchdog", WATCHDOG, 0o755)
    base.write(base.OVERLAY / "etc" / "init.d" / "S93openmitrastar-watchdog", S93WATCHDOG, 0o755)
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.7-ops-stability\n"
        "OPENMITRASTAR_MODE=http130-https-stockssl-fast-watchdog-stock-dropbear\n",
    )
    base.write(base.VERSION_DIR / "DROPBEAR_COMPAT_NOTES.md", NOTES)


def write_web_047() -> None:
    _write_web()
    api = base.OVERLAY / "var" / "www" / "api"
    base.write(api / "_lib", API_LIB, 0o755)


base.copy_runtime = copy_runtime_047
base.write_web = write_web_047


if __name__ == "__main__":
    raise SystemExit(base.main())
