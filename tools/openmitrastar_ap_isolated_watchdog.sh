#!/bin/sh

# Router-local rollback guard for the RAM-only Realtek isolated AP gate.
# It is deliberately stored outside /tmp/openmitrastar-ap so ap-stop.sh can
# remove the AP staging tree without deleting the sleeping guard itself.

set -u

ACK_VALUE=OPENMITRASTAR_RAM_ONLY_AP_LOCAL_WATCHDOG
MODE=
TIMEOUT=300
TOKEN=
ACK=
STATE=/tmp/openmitrastar-ap-isolated-watchdog
AP_ROOT=/tmp/openmitrastar-ap
RECOVERY_IP=192.168.1.200
NETMASK=255.255.255.0

die()
{
	printf 'OMAP_WATCHDOG_FAIL %s\n' "$*" >&2
	exit 2
}

need_arg()
{
	[ "$#" -ge 2 ] || die "missing value for $1"
}

while [ "$#" -gt 0 ]; do
	case "$1" in
	--arm) MODE=arm; shift ;;
	--trigger) MODE=trigger; shift ;;
	--disarm) MODE=disarm; shift ;;
	--timeout) need_arg "$@"; TIMEOUT=$2; shift 2 ;;
	--token) need_arg "$@"; TOKEN=$2; shift 2 ;;
	--ack) need_arg "$@"; ACK=$2; shift 2 ;;
	*) die "unknown argument: $1" ;;
	esac
done

[ "$ACK" = "$ACK_VALUE" ] || die "exact ACK $ACK_VALUE required"
case "$TOKEN" in
	????????????????????????????????) ;;
	*) die 'token must be exactly 32 lowercase hexadecimal characters' ;;
esac
case "$TOKEN" in *[!0-9a-f]*) die 'token must be lowercase hexadecimal' ;; esac
case "$TIMEOUT" in ''|*[!0-9]*) die 'timeout must be numeric' ;; esac
[ "$TIMEOUT" -ge 60 ] && [ "$TIMEOUT" -le 1800 ] || die 'timeout must be 60..1800 seconds'

bundle="$AP_ROOT/bundle"
bb="$bundle/bin/busybox"
hostapd_cli="$bundle/bin/hostapd_cli"
log="$STATE/watchdog.log"

log_line()
{
	printf '%s\n' "$*" >>"$log"
}

token_matches()
{
	[ -r "$STATE/token" ] || return 1
	[ "$(cat "$STATE/token")" = "$TOKEN" ]
}

rollback()
{
	reason=$1
	mkdir "$STATE/rollback.lock" 2>/dev/null || {
		log_line "OMAP_WATCHDOG_ROLLBACK_ALREADY_RUNNING reason=$reason"
		return 0
	}
	log_line "OMAP_WATCHDOG_ROLLBACK_BEGIN reason=$reason"
	if [ -x "$hostapd_cli" ]; then
		"$hostapd_cli" -p "$AP_ROOT/ctrl" -i wlan0 terminate >>"$log" 2>&1 || true
	fi
	if [ -x "$bb" ]; then
		if [ -r "$AP_ROOT/hostapd.pid" ]; then
			"$bb" kill "$(cat "$AP_ROOT/hostapd.pid")" >>"$log" 2>&1 || true
		fi
		# The gate never creates br0. Remove it only as a fail-safe if an
		# unexpected partial mutation is observed during rollback.
		if [ -e /sys/class/net/br0 ]; then
			log_line 'OMAP_WATCHDOG_UNEXPECTED_BRIDGE=br0'
			"$bb" brctl delif br0 wlan0 >>"$log" 2>&1 || true
			"$bb" brctl delif br0 eth0 >>"$log" 2>&1 || true
			"$bb" ifconfig br0 0.0.0.0 down >>"$log" 2>&1 || true
			"$bb" brctl delbr br0 >>"$log" 2>&1 || true
		fi
		"$bb" ifconfig wlan0 0.0.0.0 down >>"$log" 2>&1 || true
		"$bb" ifconfig eth0 "$RECOVERY_IP" netmask "$NETMASK" up >>"$log" 2>&1 || true
		if "$bb" ifconfig eth0 | "$bb" grep -Eq "inet (addr:)?$RECOVERY_IP([[:space:]]|$)"; then
			if [ -f "$AP_ROOT/regdb-installed" ]; then
				"$bb" rm -f /lib/firmware/regulatory.db
			fi
			"$bb" rm -f "$AP_ROOT/secret.psk" "$AP_ROOT/hostapd.conf" "$AP_ROOT/hostapd.pid"
			"$bb" rm -rf "$AP_ROOT/ctrl"
			log_line "OMAP_WATCHDOG_ROLLBACK_PASS eth0=$RECOVERY_IP wlan0=down"
			: >"$STATE/rollback.done"
		else
			log_line "OMAP_WATCHDOG_ROLLBACK_FAIL eth0=$RECOVERY_IP"
			return 1
		fi
	else
		log_line 'OMAP_WATCHDOG_ROLLBACK_FAIL toolbox=missing'
		return 1
	fi
}

case "$MODE" in
arm)
	[ -x "$bb" ] || die 'RAM AP toolbox missing'
	[ -x "$hostapd_cli" ] || die 'hostapd_cli missing'
	if [ -r "$STATE/pid" ]; then
		old_pid=$(cat "$STATE/pid")
		case "$old_pid" in ''|*[!0-9]*) old_pid=0 ;; esac
		[ "$old_pid" -eq 0 ] || ! kill -0 "$old_pid" 2>/dev/null || die 'an isolated AP watchdog is already armed'
	fi
	rm -rf "$STATE"
	mkdir -p "$STATE" || die 'cannot create watchdog state'
	printf '%s\n' "$TOKEN" >"$STATE/token"
	chmod 0600 "$STATE/token"
	printf '%s\n' "$$" >"$STATE/pid"
	log_line "OMAP_WATCHDOG_ARMED timeout_s=$TIMEOUT scope=router-local rollback_transport=none"
	trap 'rollback signal; exit 1' HUP INT TERM
	elapsed=0
	while [ "$elapsed" -lt "$TIMEOUT" ]; do
		[ ! -e "$STATE/disarmed" ] || {
			log_line 'OMAP_WATCHDOG_DISARMED_AFTER_PASS=1'
			exit 0
		}
		[ ! -e "$STATE/trigger" ] || {
			rollback explicit-trigger
			exit $?
		}
		"$bb" sleep 1
		elapsed=$((elapsed + 1))
	done
	rollback timeout
	;;
trigger)
	token_matches || die 'watchdog token mismatch'
	: >"$STATE/trigger"
	waited=0
	while [ "$waited" -lt 30 ]; do
		[ ! -e "$STATE/rollback.done" ] || {
			printf 'OMAP_WATCHDOG_TRIGGER_PASS=1\n'
			exit 0
		}
		"$bb" sleep 1
		waited=$((waited + 1))
	done
	rollback trigger-fallback
	;;
disarm)
	token_matches || die 'watchdog token mismatch'
	[ ! -d "$STATE/rollback.lock" ] || die 'rollback already started'
	: >"$STATE/disarmed"
	log_line 'OMAP_WATCHDOG_DISARM_REQUESTED=1'
	printf 'OMAP_WATCHDOG_DISARM_PASS=1\n'
	;;
*)
	die 'select exactly one of --arm, --trigger or --disarm'
	;;
esac
