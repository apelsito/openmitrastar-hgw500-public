#!/bin/ash

set -u
PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PATH
umask 077

state_dir=${OM_MC_STATE_DIR:-/run/openmitrastar/multicast-cert}
snooping=${OM_MC_SNOOPING_PATH:-/sys/class/net/br0/bridge/multicast_snooping}
querier=${OM_MC_QUERIER_PATH:-/sys/class/net/br0/bridge/multicast_querier}
router=${OM_MC_ROUTER_PATH:-/sys/class/net/br0/bridge/multicast_router}
watchdog_seconds=${OM_MC_WATCHDOG_SECONDS:-300}
self=${OM_MC_SELF:-$0}
original=$state_dir/original.env
watchdog_pid=$state_dir/watchdog.pid

valid_bit()
{
	case "${1:-}" in 0|1|2) return 0 ;; *) return 1 ;; esac
}

read_value()
{
	[ -r "$1" ] || return 1
	IFS= read -r value <"$1" || return 1
	valid_bit "$value" || return 1
	printf '%s' "$value"
}

write_value()
{
	printf '%s\n' "$2" >"$1" || return 1
	[ "$(read_value "$1")" = "$2" ]
}

status()
{
	printf 'snooping=%s\nquerier=%s\nrouter=%s\n' \
		"$(read_value "$snooping" || printf unavailable)" \
		"$(read_value "$querier" || printf unavailable)" \
		"$(read_value "$router" || printf unavailable)"
	[ -r "$original" ] && printf 'saved=1\n' || printf 'saved=0\n'
}

restore_values()
{
	[ -r "$original" ] || return 0
	orig_snooping=$(sed -n 's/^snooping=//p' "$original" | head -n 1)
	orig_querier=$(sed -n 's/^querier=//p' "$original" | head -n 1)
	orig_router=$(sed -n 's/^router=//p' "$original" | head -n 1)
	valid_bit "$orig_snooping" && valid_bit "$orig_querier" && valid_bit "$orig_router" || return 1
	write_value "$snooping" "$orig_snooping" || return 1
	write_value "$querier" "$orig_querier" || return 1
	write_value "$router" "$orig_router" || return 1
}

rollback()
{
	if [ -r "$watchdog_pid" ]; then
		pid=$(cat "$watchdog_pid" 2>/dev/null || true)
		case "$pid" in ''|*[!0-9]*) ;; *) [ "$pid" = $$ ] || kill "$pid" 2>/dev/null || true ;; esac
	fi
	restore_values || { echo OMMC_ROLLBACK_FAIL; return 1; }
	rm -rf "$state_dir"
	echo OMMC_ROLLBACK_PASS
}

apply()
{
	for path in "$snooping" "$querier" "$router"; do [ -w "$path" ] || { echo "OMMC_MISSING=$path"; return 1; }; done
	[ ! -e "$original" ] || { echo OMMC_ALREADY_ACTIVE; return 1; }
	mkdir -p "$state_dir" || return 1
	printf 'snooping=%s\nquerier=%s\nrouter=%s\n' \
		"$(read_value "$snooping")" "$(read_value "$querier")" "$(read_value "$router")" >"$original" || return 1
	if ! write_value "$snooping" 1 || ! write_value "$querier" 1 || ! write_value "$router" 0; then
		restore_values || true
		rm -rf "$state_dir"
		echo OMMC_APPLY_FAIL
		return 1
	fi
	case "$watchdog_seconds" in ''|*[!0-9]*) watchdog_seconds=300 ;; esac
	if [ "$watchdog_seconds" -gt 0 ]; then
		( sleep "$watchdog_seconds"; OM_MC_STATE_DIR="$state_dir" OM_MC_SNOOPING_PATH="$snooping" OM_MC_QUERIER_PATH="$querier" OM_MC_ROUTER_PATH="$router" OM_MC_WATCHDOG_SECONDS=0 "$self" rollback-watchdog >/dev/null 2>&1 ) &
		printf '%s\n' $! >"$watchdog_pid"
	fi
	echo OMMC_APPLY_PASS
	status
}

case "${1:-status}" in
apply) apply ;;
rollback|rollback-watchdog) rollback ;;
status) status ;;
*) echo 'usage: q3_multicast_igmp_cert_remote.sh {apply|status|rollback}' >&2; exit 2 ;;
esac
