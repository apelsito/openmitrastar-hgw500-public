#!/usr/bin/env python3
"""Generate OpenMitraStar 0.5: original firmware, lighter runtime.

This branch deliberately keeps the provider web UI/backend intact and improves
the firmware around boot/runtime services. The goal is lower RAM/log/debug
overhead without removing capabilities: heavy services remain available through
explicit tuning flags in /etc/openmitrastar-tuning.conf or
/mnt/ccc/openmitrastar-tuning.conf.
"""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "work" / "revival" / "rootfs"
VERSION = "openmitrastar-0.5-original-fw-lite"
VERSION_DIR = ROOT / "versions" / VERSION
OVERLAY = VERSION_DIR / "overlay"


TUNING_CONF = """# OpenMitraStar runtime tuning.
# Copy this file to /mnt/ccc/openmitrastar-tuning.conf to override defaults
# without reflashing.
OMT_PROFILE=balanced
OMT_ENABLE_QHARVESTD=0
OMT_ENABLE_PKTLOGGER=0
OMT_ENABLE_OFFLINE_DUMP=0
OMT_ENABLE_COREDUMP=0
OMT_ENABLE_GETINFO_HTTPD=0
OMT_ENABLE_QEVT=1
OMT_ENABLE_TEMP_MONITOR=1
"""


TUNING_HELPER = r"""#!/bin/sh
OMT_PROFILE=balanced
OMT_ENABLE_QHARVESTD=0
OMT_ENABLE_PKTLOGGER=0
OMT_ENABLE_OFFLINE_DUMP=0
OMT_ENABLE_COREDUMP=0
OMT_ENABLE_GETINFO_HTTPD=0
OMT_ENABLE_QEVT=1
OMT_ENABLE_TEMP_MONITOR=1

[ -f /etc/openmitrastar-tuning.conf ] && . /etc/openmitrastar-tuning.conf
[ -f /mnt/ccc/openmitrastar-tuning.conf ] && . /mnt/ccc/openmitrastar-tuning.conf

omt_get() {
	key="$1"
	eval "printf '%s' \"\${$key}\""
}

omt_enabled() {
	key="$1"
	val="$(omt_get "$key")"
	[ "$val" = "1" ] || [ "$val" = "yes" ] || [ "$val" = "true" ] || [ "$val" = "on" ]
}

omt_profile() {
	echo "$OMT_PROFILE"
}
"""


SERVICES_TOOL = r"""#!/bin/sh
CONF=/mnt/ccc/openmitrastar-tuning.conf

show() {
	if [ -f "$CONF" ]; then
		cat "$CONF"
	else
		cat /etc/openmitrastar-tuning.conf
	fi
}

set_key() {
	key="$1"
	value="$2"
	case "$key" in
		OMT_PROFILE|OMT_ENABLE_QHARVESTD|OMT_ENABLE_PKTLOGGER|OMT_ENABLE_OFFLINE_DUMP|OMT_ENABLE_COREDUMP|OMT_ENABLE_GETINFO_HTTPD|OMT_ENABLE_QEVT|OMT_ENABLE_TEMP_MONITOR) ;;
		*) echo "unsupported key: $key"; exit 1 ;;
	esac
	mkdir -p /mnt/ccc
	[ -f "$CONF" ] || cp /etc/openmitrastar-tuning.conf "$CONF"
	if grep -q "^$key=" "$CONF"; then
		sed "s/^$key=.*/$key=$value/" "$CONF" > /tmp/openmitrastar-tuning.$$
		mv /tmp/openmitrastar-tuning.$$ "$CONF"
	else
		echo "$key=$value" >> "$CONF"
	fi
	sync
}

case "$1" in
	show|"") show ;;
	set) set_key "$2" "$3" ;;
	fast)
		mkdir -p /mnt/ccc
		cat > "$CONF" <<EOF
OMT_PROFILE=fast
OMT_ENABLE_QHARVESTD=0
OMT_ENABLE_PKTLOGGER=0
OMT_ENABLE_OFFLINE_DUMP=0
OMT_ENABLE_COREDUMP=0
OMT_ENABLE_GETINFO_HTTPD=0
OMT_ENABLE_QEVT=0
OMT_ENABLE_TEMP_MONITOR=1
EOF
		sync
		;;
	balanced)
		rm -f "$CONF"
		sync
		;;
	debug)
		mkdir -p /mnt/ccc
		cat > "$CONF" <<EOF
OMT_PROFILE=debug
OMT_ENABLE_QHARVESTD=1
OMT_ENABLE_PKTLOGGER=1
OMT_ENABLE_OFFLINE_DUMP=1
OMT_ENABLE_COREDUMP=1
OMT_ENABLE_GETINFO_HTTPD=1
OMT_ENABLE_QEVT=1
OMT_ENABLE_TEMP_MONITOR=1
EOF
		sync
		;;
	*) echo "Usage: $0 [show|balanced|fast|debug|set KEY VALUE]"; exit 1 ;;
esac
"""


S10_COREDUMP = r"""#!/bin/sh

. /scripts/openmitrastar-tuning

base_scripts="/scripts"
core_path="/var/log/core"
platform_file=$base_scripts/platform_id

if ! omt_enabled OMT_ENABLE_COREDUMP; then
	echo "OpenMitraStar: coredumps disabled"
	ulimit -c 0 2>/dev/null || true
	echo 0 > /proc/sys/kernel/core_uses_pid 2>/dev/null || true
	exit 0
fi

if [ -f $platform_file ]; then
	platform_id=`cat $platform_file`
	if [ "$platform_id" = "464" ]; then
		mkdir -p $core_path
		echo "$core_path/core_t%t_%e" > /proc/sys/kernel/core_pattern
	fi
fi
"""


S60_DEBUG = r"""#!/bin/sh
# Setup debug facility only when explicitly requested.

. /scripts/openmitrastar-tuning

if omt_enabled OMT_ENABLE_OFFLINE_DUMP; then
	/scripts/offline_dump on > /dev/null &
else
	echo "OpenMitraStar: offline dump disabled"
fi
"""


S90_MAUI = r"""#!/bin/sh

# This script starts/stops the Quantenna qharvestd/MAUI service.

. /scripts/openmitrastar-tuning

kill_process() {
	pid_name=$1
	pid=`ps | grep "$pid_name" | grep -v "grep $pid_name" | awk '{print $1}'`
	[ -n "$pid" ] && kill $pid
}

start() {
	export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts:/usr/local/bin
	export LD_LIBRARY_PATH=/lib:/usr/lib

	if ! omt_enabled OMT_ENABLE_QHARVESTD; then
		echo "OpenMitraStar: MAUI/qharvestd disabled"
		return 0
	fi

	maui=`get_wifi_config wifi0 maui`
	maui_rc=$?
	if [ "$maui_rc" -ne 0 ] || [ "$maui" = "1" ]; then
		echo "MAUI Service started...."
		if [ -f /sbin/qharvestd ]; then
			[ -d /mnt/jffs2/qharvestd ] && rm -rf /mnt/jffs2/qharvestd
			[ ! -f /mnt/jffs2/qharvestd.conf ] && cp -f /etc/qharvestd.conf /mnt/jffs2/qharvestd.conf
			/scripts/cmdloop /sbin/qharvestd -c/mnt/jffs2/qharvestd.conf &
		fi
	else
		echo "Maui service is not enabled in wireless_conf.txt"
	fi
}

stop() {
	echo "Stopping MAUI service"
	kill_process "ntpclient"
	kill_process "/bin/sh /scripts/cmdloop /sbin/qharvestd -c/mnt/jffs2"
	kill_process "qharvestd"
}

restart() { stop; start; }

case "$1" in
	start) start ;;
	stop) stop ;;
	restart|reload) restart ;;
	*) echo "Usage: $0 {start|stop|restart}"; exit 1 ;;
esac
exit $?
"""


S92_HTTPD = r"""#!/bin/sh

# This script starts and stops mini_httpd. OpenMitraStar keeps the provider UI
# but avoids the extra getinfo listener unless explicitly enabled.

. /scripts/openmitrastar-tuning

kill_process() {
	pid_name=$1
	pid=`ps | grep "$pid_name" | grep -v "grep $pid_name" | awk '{print $1}'`
	[ -n "$pid" ] && kill $pid
}

start() {
	export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts:/usr/local/bin
	export LD_LIBRARY_PATH=/lib:/usr/lib

	platform_file=/scripts/platform_id
	[ -f $platform_file ] && platform_id=`cat $platform_file` || platform_id=00

	if [ "$platform_id" != "425" ]; then
		if [ ! -f /mnt/jffs2/httpd-disabled ]; then
			echo "Starting httpd"
			[ ! -f /mnt/jffs2/minihttpd.conf ] && cp -f /etc/minihttpd.conf /mnt/jffs2/minihttpd.conf
			[ ! -f /mnt/jffs2/admin.conf ] && cp -f /etc/admin.conf /mnt/jffs2/admin.conf
			if [ -f /sbin/mini_httpd ]; then
				/sbin/mini_httpd -r -u root -C /mnt/jffs2/minihttpd.conf
				/sbin/mini_httpd -r -u root -C /etc/minihttpd_ssl.conf
				if omt_enabled OMT_ENABLE_GETINFO_HTTPD; then
					/sbin/mini_httpd -r -u root -C /etc/minihttpd_getinfo.conf
				else
					echo "OpenMitraStar: getinfo httpd disabled"
				fi
			fi
		else
			echo "httpd is not enabled"
		fi
	fi
}

stop() { echo "Stopping httpd"; kill_process "mini_httpd"; }
restart() { stop; start; }

case "$1" in
	start) start ;;
	stop) stop ;;
	restart|reload) restart ;;
	*) echo "Usage: $0 {start|stop|restart}"; exit 1 ;;
esac
exit $?
"""


S41_QEVT = r"""#!/bin/sh

. /scripts/openmitrastar-tuning

check_status() {
	pid=`pidof "$1"`
	[ -n "$pid" ] && echo "$qevt_server service is running" || echo "$qevt_server service is not running"
}

start() {
	export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts:/usr/local/bin
	export LD_LIBRARY_PATH=/lib:/usr/lib

	if ! omt_enabled OMT_ENABLE_QEVT; then
		echo "OpenMitraStar: qevt_server disabled"
		return 0
	fi

	qevt_enabled=`get_wifi_config wifi0 qevt`
	if [ "$qevt_enabled" = "0" ]; then
		echo "$qevt_server is not enabled in wireless_conf.txt"
	else
		if [ -f $qevt_server_path/$qevt_server ]; then
			echo "Starting $qevt_server"
			$base_scripts/launch start $qevt_server &
		else
			echo "$qevt_server_path/$qevt_server not found"
			exit 1
		fi
	fi
}

stop() { $base_scripts/launch stop $qevt_server; }

status() {
	if ! omt_enabled OMT_ENABLE_QEVT; then
		echo "OpenMitraStar: qevt_server disabled"
		return 0
	fi
	qevt_enabled=`get_wifi_config wifi0 qevt`
	[ "$qevt_enabled" = "0" ] && echo "$qevt_server is not enabled in wireless_conf.txt" || check_status "$qevt_server"
}

restart() { stop; start; }

qevt_server_path="/sbin"
qevt_server="qevt_server"
base_scripts="/scripts"

case "$1" in
	start) start ;;
	stop) stop ;;
	status) status ;;
	restart|reload) restart ;;
	*) echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
exit $?
"""


FWUPGRADE = r"""#!/bin/sh

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH

TEMP="/tmp/result_upgrade"
LOG="/tmp/openmitrastar-fwupgrade.log"

fail() {
	echo "error: $1" > "$TEMP"
	echo "error: $1" >> "$LOG"
	exit 1
}

image="$1"
target="$2"
: > "$TEMP"
: > "$LOG"

[ -n "$image" ] || fail "missing firmware image path"
[ -f "$image" ] || fail "firmware image not found"
case "$target" in live|safety) ;; *) fail "invalid target partition" ;; esac

size="$(wc -c < "$image" 2>/dev/null | tr -d ' ')"
case "$size" in *[!0-9]*|"") fail "invalid firmware size" ;; esac
[ "$size" -gt 0 ] || fail "empty firmware image"
[ "$size" -le 7995392 ] || fail "firmware image too large"

if command -v chkimage >/dev/null 2>&1; then
	chkimage -A arc -O linux -T kernel -v "$image" >> "$LOG" 2>&1 || fail "chkimage rejected firmware"
fi

sync
call_qcsapi flash_image_update "$image" "$target" > "$TEMP" 2>> "$LOG"
rc="$?"
sync

if [ "$rc" != "0" ]; then
	echo "call_qcsapi flash_image_update rc=$rc" >> "$LOG"
	exit "$rc"
fi

grep -q complete "$TEMP" 2>/dev/null || {
	echo "backend did not report complete" >> "$LOG"
	exit 1
}

exit 0
"""


QHARVESTD_CONF = """[qharvestd]
baseurl=https://qharvest-prod.quantenna.com/api
rootdir=/mnt/jffs2/qharvestd
debug=0
"""


def write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if mode is not None:
        path.chmod(mode)


def copy_and_patch_start_prod() -> None:
    src = SRC / "scripts" / "start-prod"
    text = src.read_text(encoding="utf-8", errors="ignore")
    old = """# pktlogger daemon
pktlogger_d_cmd="/usr/sbin/pktlogger_d"
if [ -f $pktlogger_d_cmd ]
then
\tintf="pcie0"
\tif [ -e /sys/class/net/$intf ]
\tthen
\t\tpktlogger_d_cmd="$pktlogger_d_cmd -i $intf"
\tfi

\t$pktlogger_d_cmd &
fi
"""
    new = """. /scripts/openmitrastar-tuning

# pktlogger daemon is useful for deep diagnostics, but costs RAM and I/O.
if omt_enabled OMT_ENABLE_PKTLOGGER; then
\tpktlogger_d_cmd="/usr/sbin/pktlogger_d"
\tif [ -f $pktlogger_d_cmd ]; then
\t\tintf="pcie0"
\t\t[ -e /sys/class/net/$intf ] && pktlogger_d_cmd="$pktlogger_d_cmd -i $intf"
\t\t$pktlogger_d_cmd &
\tfi
else
\techo "OpenMitraStar: pktlogger_d disabled"
fi
"""
    if old not in text:
        raise RuntimeError("start-prod pktlogger block not found")
    write(OVERLAY / "scripts" / "start-prod", text.replace(old, new), 0o755)


def main() -> int:
    if not SRC.exists():
        raise FileNotFoundError(SRC)
    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)

    write(OVERLAY / "etc" / "openmitrastar-release",
          "OPENMITRASTAR_VERSION=openmitrastar-0.5-original-fw-lite\n"
          "OPENMITRASTAR_MODE=original-fw-lite\n")
    write(OVERLAY / "etc" / "openmitrastar-tuning.conf", TUNING_CONF)
    write(OVERLAY / "scripts" / "openmitrastar-tuning", TUNING_HELPER, 0o755)
    write(OVERLAY / "scripts" / "openmitrastar-services", SERVICES_TOOL, 0o755)
    write(OVERLAY / "etc" / "init.d" / "S10coredump", S10_COREDUMP, 0o755)
    write(OVERLAY / "etc" / "init.d" / "S41qevt", S41_QEVT, 0o755)
    write(OVERLAY / "etc" / "init.d" / "S60debug", S60_DEBUG, 0o755)
    write(OVERLAY / "etc" / "init.d" / "S90maui", S90_MAUI, 0o755)
    write(OVERLAY / "etc" / "init.d" / "S92httpd", S92_HTTPD, 0o755)
    write(OVERLAY / "etc" / "default" / "FWupgrade.sh", FWUPGRADE, 0o755)
    write(OVERLAY / "etc" / "qharvestd.conf", QHARVESTD_CONF)
    copy_and_patch_start_prod()
    print(f"generated {OVERLAY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
