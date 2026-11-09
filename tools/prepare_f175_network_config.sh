#!/bin/sh
set -eu

# Resolve the F175 network feature fragment without building or touching
# hardware. This deliberately leaves multicast routing disabled.

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
build_tree=${F175_CONFIG_BUILD:-/home/user/openmitrastar-build/f175-network-config-check}
base="$root/work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build/openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH.config"
fragment="$root/configs/lyoko/f175-bridge-multicast.config"
out="$root/outputs/kernel-port/f175-network-capabilities-config-20260901"
cross="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

test -f "$source_tree/Makefile"
test -x "$source_tree/scripts/config"
test -f "$base"
test -f "$fragment"
case "$out" in "$root"/*) ;; *) exit 3 ;; esac

mkdir -p "$build_tree" "$out"
cp "$base" "$build_tree/.config"
while IFS= read -r line; do
	case "$line" in
	CONFIG_*=y) name=${line%%=*}; "$source_tree/scripts/config" --file "$build_tree/.config" --enable "${name#CONFIG_}" ;;
	'# CONFIG_'*' is not set') name=${line#'# CONFIG_'}; name=${name%' is not set'}; "$source_tree/scripts/config" --file "$build_tree/.config" --disable "$name" ;;
	''|'#'*) ;;
	*) echo "unsupported config fragment line: $line" >&2; exit 4 ;;
	esac
done <"$fragment"

make -s -C "$source_tree" O="$build_tree" ARCH=arc CROSS_COMPILE="$cross" olddefconfig
grep -qx 'CONFIG_BRIDGE=y' "$build_tree/.config"
grep -qx 'CONFIG_VLAN_8021Q=y' "$build_tree/.config"
grep -qx 'CONFIG_IP_MULTICAST=y' "$build_tree/.config"
grep -qx 'CONFIG_BRIDGE_IGMP_SNOOPING=y' "$build_tree/.config"
grep -qx '# CONFIG_IP_MROUTE is not set' "$build_tree/.config"
grep -qx '# CONFIG_VLAN_8021Q_GVRP is not set' "$build_tree/.config"
grep -qx '# CONFIG_VLAN_8021Q_MVRP is not set' "$build_tree/.config"

cp "$build_tree/.config" "$out/f175-network.config"
sha256sum "$out/f175-network.config" >"$out/SHA256SUMS"
cat >"$out/manifest.json" <<EOF
{
  "schema": "openmitrastar.f175-network-config/v1",
  "classification": "OFFLINE_CONFIG_ONLY_NOT_A_FLASH_IMAGE",
  "base": "F171",
  "resolved_config": "f175-network.config",
  "sha256": "$(sha256sum "$out/f175-network.config" | cut -d' ' -f1)",
  "enabled": ["CONFIG_IP_MULTICAST", "CONFIG_BRIDGE_IGMP_SNOOPING"],
  "preserved": ["CONFIG_BRIDGE", "CONFIG_VLAN_8021Q"],
  "disabled": ["CONFIG_IP_MROUTE", "CONFIG_VLAN_8021Q_GVRP", "CONFIG_VLAN_8021Q_MVRP"],
  "hardware_actions": {"router": false, "uart": false, "mtd": false},
  "firmware_candidate": false
}
EOF
printf 'OMF175_NETWORK_CONFIG_PASS sha256='
sha256sum "$out/f175-network.config" | cut -d' ' -f1
