#!/bin/ash

# RAM-only wrapper used during Quantenna crash localization.
set -u
real=/usr/sbin/ram-insmod-qtn.real

[ -x "$real" ] || exit 126
[ "$#" -ge 1 ] || exit 2
module_path=$1
"$real" "$@" || exit $?

base=${module_path##*/}
name=${base%.ko}
text_addr=$(cat "/sys/module/$name/sections/.text" 2>/dev/null || true)
[ -n "$text_addr" ] || text_addr=unavailable
printf 'OMMODULEMAP name=%s text=%s\n' "$name" "$text_addr" \
	>/dev/console 2>/dev/null || true
exit 0
