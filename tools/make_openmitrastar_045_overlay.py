#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.5 with a working mini_httpd 1.30 upgrade.

This version keeps the 0.4.4 modern UI and no-CGI user experience, but replaces
the stock mini_httpd 1.19/bhoc binary with an OpenMitraStar-compatible 1.30
build and fixes API execution:

* no chroot for shell-backed /api/* endpoints
* cgipat matches mini_httpd's relative filenames: api/*|**.cgi|**.php
* API scripts avoid tr, which is absent in the stock rootfs
"""

from __future__ import annotations

import importlib.util
import os
import shutil


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_044_overlay.py"
MINIHTTPD_COMPAT = ROOT / "work" / "tftp" / "mini_httpd-1.30-omt-compat"

spec = importlib.util.spec_from_file_location("omt044", BASE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
base = mod.base

base.VERSION = "openmitrastar-0.4.5-minihttpd-upgrade"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

base.MINIHTTPD = """ # mini_httpd configuration file
data_dir=/var/www
port=80
host=0.0.0.0
cgipat=api/*|**.cgi|**.php
charset=UTF-8
"""

base.MINIHTTPD_SSL = """ # mini_httpd configuration file
data_dir=/var/www
port=443
host=0.0.0.0
cgipat=api/*|**.cgi|**.php
charset=UTF-8
ssl
certfile=/etc/minihttpd.pem
"""

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
                        echo "Starting OpenMitraStar mini_httpd 1.30"
                        cp -f /etc/minihttpd.conf /mnt/jffs2/minihttpd.conf
                        [ ! -f /mnt/jffs2/admin.conf ] && cp -f /etc/admin.conf /mnt/jffs2/admin.conf
                        if [ -f /sbin/mini_httpd ] ; then
                                /sbin/mini_httpd -u root -C /mnt/jffs2/minihttpd.conf
                                /sbin/mini_httpd -u root -C /etc/minihttpd_ssl.conf
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

API_LIB = r"""#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH
json_escape() { sed ':a;N;$!ba;s/\n/ /g;s/\r/ /g;s/\\/\\\\/g;s/"/\\"/g'; }
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

API_STATUS = r"""#!/bin/sh
. /var/www/api/_lib
header_json
rel_ver="$(sed -n 's/^OPENMITRASTAR_VERSION=//p' /etc/openmitrastar-release 2>/dev/null)"
rel_mode="$(sed -n 's/^OPENMITRASTAR_MODE=//p' /etc/openmitrastar-release 2>/dev/null)"
ver="$(echo "$rel_ver $rel_mode" | json_escape)"
mt="$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null)"
mf="$(awk '/MemFree/{print $2}' /proc/meminfo 2>/dev/null)"
up="$(cut -d' ' -f1 /proc/uptime 2>/dev/null)"
br="$(ifconfig br0 2>/dev/null | awk '/inet addr/{print $2}' | sed 's/addr://')"
mode="$(call_qcsapi get_mode wifi0 2>/dev/null | json_escape)"
chan="$(call_qcsapi get_channel wifi0 2>/dev/null | json_escape)"
bw="$(call_qcsapi get_bw wifi0 2>/dev/null | json_escape)"
region="$(call_qcsapi get_regulatory_region wifi0 2>/dev/null | json_escape)"
cat <<EOF
{"version":"$ver","uptime":"$up","mem_total_kb":"$mt","mem_free_kb":"$mf","bridge":"$br","services":{"tr69c":"$(pid_state tr69c)","qharvestd":"$(pid_state qharvestd)","pktlogger":"$(pid_state pktlogger_d)","mini_httpd":"$(pid_state mini_httpd)","telnetd":"$(pid_state telnetd)"},"radio":{"wifi0_mode":"$mode","wifi0_channel":"$chan","wifi0_bw":"$bw","wifi0_region":"$region"}}
EOF
"""

API_WIFI = r"""#!/bin/sh
. /var/www/api/_lib
apply_pair() {
  key="$1"; value="$2"
  [ -z "$key" ] && return 0
  case "$key" in key|value) return 0;; *[!A-Za-z0-9._-]*) echo "skip invalid key $key" >>/tmp/openmitrastar-qweconfig.log; return 0;; esac
  case "$key" in
    channel.wifi0) call_qcsapi -u -q set_channel wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    bw.wifi0) call_qcsapi -u -q set_bw wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    mode.wifi0) call_qcsapi -u -q set_mode wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    tx_power.wifi0) call_qcsapi -u -q set_tx_power wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    *) qweconfig set "$key" "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
  esac
}
if [ "$REQUEST_METHOD" = "POST" ]; then
  read_body
  > /tmp/openmitrastar-qweconfig.log
  if echo "$BODY" | grep -q '^key='; then
    apply_pair "$(kv key)" "$(kv value)"
  else
    for pair in $(echo "$BODY" | sed 's/&/ /g'); do
      k="$(echo "${pair%%=*}" | url_decode_common)"
      v="$(echo "${pair#*=}" | url_decode_common)"
      apply_pair "$k" "$v"
    done
  fi
  header_json
  msg="$(cat /tmp/openmitrastar-qweconfig.log 2>/dev/null | json_escape)"
  echo "{\"ok\":true,\"message\":\"$msg\"}"
  exit 0
fi
header_json
ssid="$(qweconfig get ssid.wlan1 2>/dev/null | json_escape)"
mode="$(qweconfig get mode.wlan1 2>/dev/null | json_escape)"
chan="$(call_qcsapi get_channel wifi0 2>/dev/null | json_escape)"
bw="$(call_qcsapi get_bw wifi0 2>/dev/null | json_escape)"
echo "{\"ssid\":\"$ssid\",\"mode\":\"$mode\",\"wifi0_channel\":\"$chan\",\"wifi0_bw\":\"$bw\"}"
"""

API_FLASH = r"""#!/bin/sh
. /var/www/api/_lib
tmp="/tmp/topaz-linux.lzma.img"
result="/tmp/result_upgrade"
max_size=7995392

fail() {
  header_json
  msg="$(echo "$1" | json_escape)"
  echo "{\"ok\":false,\"error\":\"$msg\"}"
  exit 0
}

[ "$REQUEST_METHOD" = "POST" ] || fail "POST required"
[ -n "$CONTENT_LENGTH" ] || fail "missing Content-Length"

case "$CONTENT_LENGTH" in *[!0-9]*|"") fail "invalid Content-Length";; esac
[ "$CONTENT_LENGTH" -gt 0 ] || fail "empty firmware image"
[ "$CONTENT_LENGTH" -le "$max_size" ] || fail "firmware image too large"

target="$(qv target)"
case "$target" in live|safety) ;; "") target="live" ;; *) fail "invalid target partition";; esac

rm -f "$tmp" "$result"
cat > "$tmp"
set -- $(wc -c < "$tmp" 2>/dev/null)
actual="$1"
[ "$actual" = "$CONTENT_LENGTH" ] || fail "incomplete upload"

if command -v chkimage >/dev/null 2>&1; then
  chkimage -A arc -O linux -T kernel -v "$tmp" >/tmp/openmitrastar-flash-validate.log 2>&1 || {
    err="$(cat /tmp/openmitrastar-flash-validate.log 2>/dev/null)"
    fail "chkimage rejected firmware: $err"
  }
else
  magic="$(dd if="$tmp" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | sed 's/[ \n]//g')"
  [ "$magic" = "27051956" ] || fail "uImage magic not found"
fi

/etc/default/led.sh fwupgrade >/dev/null 2>&1 &
sh /etc/default/FWupgrade.sh "$tmp" "$target" >/tmp/openmitrastar-flash-run.log 2>&1
backend="$(cat "$result" /tmp/openmitrastar-flash-run.log 2>/dev/null | json_escape)"
if echo "$backend" | grep -q complete; then
  (sleep 2; reboot -d 6 >/dev/null 2>&1) &
  header_json
  echo "{\"ok\":true,\"target\":\"$target\",\"message\":\"firmware accepted; reboot scheduled\",\"backend\":\"$backend\"}"
else
  fail "firmware backend did not report complete: $backend"
fi
"""

FWUPGRADE_SH = r"""#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH

RESULT="/tmp/result_upgrade"
LOG="/tmp/openmitrastar-fwupgrade.log"

fail() {
  echo "error: $1" > "$RESULT"
  echo "error: $1" >> "$LOG"
  exit 1
}

image="$1"
target="$2"
: > "$RESULT"
: > "$LOG"

[ -n "$image" ] || fail "missing firmware image path"
[ -f "$image" ] || fail "firmware image not found"
case "$target" in
  live|safety) ;;
  *) fail "invalid target partition" ;;
esac

set -- $(wc -c < "$image" 2>/dev/null)
size="$1"
case "$size" in *[!0-9]*|"") fail "invalid firmware size" ;; esac
[ "$size" -gt 0 ] || fail "empty firmware image"
[ "$size" -le 7995392 ] || fail "firmware image too large"

if command -v chkimage >/dev/null 2>&1; then
  chkimage -A arc -O linux -T kernel -v "$image" >> "$LOG" 2>&1 || fail "chkimage rejected firmware"
fi

sync
call_qcsapi flash_image_update "$image" "$target" > "$RESULT" 2>> "$LOG"
rc="$?"
sync

if [ "$rc" != "0" ]; then
  echo "call_qcsapi flash_image_update rc=$rc" >> "$LOG"
  exit "$rc"
fi

grep -q complete "$RESULT" 2>/dev/null || {
  echo "backend did not report complete" >> "$LOG"
  exit 1
}

exit 0
"""

API_BACKUP_FIRMWARE = r"""#!/bin/sh
. /var/www/api/_lib
part_req="$(qv part)"
case "$part_req" in
  linux_live|"") name="linux_live"; file="raw-linux-live-dump.bin";;
  linux_safety) name="linux_safety"; file="raw-linux-safety-dump.bin";;
  rootfs_live) name="rootfs_live"; file="raw-rootfs-live-dump.squashfs";;
  *) header_json; echo '{"ok":false,"error":"unknown partition"}'; exit 0;;
esac
part="$(grep "\"$name\"" /proc/mtd 2>/dev/null | awk -F: 'NR==1{print $1}')"
header_bin "$file"
if [ -n "$part" ] && [ -e "/dev/$part" ]; then
  cat "/dev/$part"
else
  echo "partition $name not found"
fi
"""

_copy_runtime = base.copy_runtime
_write_web = base.write_web


def copy_runtime_045() -> None:
    _copy_runtime()
    if not MINIHTTPD_COMPAT.exists():
        raise FileNotFoundError(MINIHTTPD_COMPAT)
    sbin = base.OVERLAY / "sbin"
    sbin.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MINIHTTPD_COMPAT, sbin / "mini_httpd")
    os.chmod(sbin / "mini_httpd", 0o755)
    base.write(base.OVERLAY / "etc" / "minihttpd.conf", base.MINIHTTPD)
    base.write(base.OVERLAY / "etc" / "minihttpd_ssl.conf", base.MINIHTTPD_SSL)
    base.write(base.OVERLAY / "etc" / "init.d" / "S92httpd", S92HTTPD, 0o755)
    base.write(base.OVERLAY / "etc" / "default" / "FWupgrade.sh", FWUPGRADE_SH, 0o755)
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.5-minihttpd-upgrade\n"
        "OPENMITRASTAR_MODE=modern-ui-minihttpd-1.30\n",
    )


def write_web_045() -> None:
    _write_web()
    api = base.OVERLAY / "var" / "www" / "api"
    base.write(api / "_lib", API_LIB, 0o755)
    base.write(api / "status", API_STATUS, 0o755)
    base.write(api / "wifi", API_WIFI, 0o755)
    base.write(api / "flash", API_FLASH, 0o755)
    base.write(api / "backup" / "firmware", API_BACKUP_FIRMWARE, 0o755)


base.copy_runtime = copy_runtime_045
base.write_web = write_web_045


if __name__ == "__main__":
    raise SystemExit(base.main())
