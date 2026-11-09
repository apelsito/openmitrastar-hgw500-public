#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
victim=/home/user/openmitrastar-security-guard-victim
trap 'rm -rf -- "$victim" /tmp/om-realtek-guard.out /tmp/om-candidate-guard.out' EXIT HUP INT TERM
rm -rf -- "$victim"
mkdir -p "$victim"
printf '%s\n' alive >"$victim/sentinel"

set +e
REALTEK_SKIP_BUILD=1 \
REALTEK_BUNDLE_DIR="$root/outputs/kernel-port/realtek-loop/RAM-ONLY-x/../../../../../../home/user/openmitrastar-security-guard-victim" \
sh "$root/tools/build_realtek_8192ee_incremental.sh" >/tmp/om-realtek-guard.out 2>&1
realtek_rc=$?
OM_W2_2G_STAGE_A=/home/user/openmitrastar-build/x/../../openmitrastar-security-guard-victim \
sh "$root/tools/build_w2_2g_parity_ram_candidate.sh" >/tmp/om-candidate-guard.out 2>&1
candidate_rc=$?
set -e

[ "$realtek_rc" -ne 0 ]
[ "$candidate_rc" -ne 0 ]
[ "$(cat "$victim/sentinel")" = alive ]
grep -q 'refusing bundle outside RAM-only output root' /tmp/om-realtek-guard.out
grep -q 'unsafe W2 2G build path' /tmp/om-candidate-guard.out

echo 'SECURITY_PATH_GUARDS_PASS=1'
