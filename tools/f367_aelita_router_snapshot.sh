#!/bin/sh
# Root runs this only over the independently pinned HGW SSH connection.
# argv: run nonce, exact future version. No station MAC is emitted.
set -eu
nonce=$1
expected=$2
case "$nonce" in *[!0-9a-f]*|'') exit 20;; esac
[ "${#nonce}" = 32 ] || exit 20
case "$expected" in lyoko-*-f367*) ;; *) exit 21;; esac
version=$(sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release)
[ "$version" = "$expected" ] || exit 22
boot=$(cat /proc/sys/kernel/random/boot_id)
rx=$(cat /sys/class/net/wifi0/statistics/rx_bytes)
tx=$(cat /sys/class/net/wifi0/statistics/tx_bytes)
bssid=$(cat /sys/class/net/wifi0/address)
tag=$(printf '%s%s' "$nonce" "$bssid" | sha256sum | awk '{print $1}')
printf 'OMF367_ROUTER run_id=%s firmware=%s boot_id=%s wifi_rx_bytes=%s wifi_tx_bytes=%s target_bssid_tag=%s\n' "$nonce" "$version" "$boot" "$rx" "$tx" "$tag"
stations=$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta)
printf '%s\n' "$stations" | awk '
 /^[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:/ { mac=tolower($0) }
 /^flags=/ { print mac, (index($0,"[AUTH]")>0), (index($0,"[ASSOC]")>0), (index($0,"[AUTHORIZED]")>0) }
' | while read -r mac auth assoc authorized; do
 tag=$(printf '%s%s' "$nonce" "$mac" | sha256sum | awk '{print $1}')
 printf 'OMF367_STATION tag=%s auth=%s assoc=%s authorized=%s\n' "$tag" "$auth" "$assoc" "$authorized"
done
