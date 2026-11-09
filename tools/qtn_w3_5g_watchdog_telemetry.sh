#!/bin/sh
set -eu

interval=${1:-5}
samples=${2:-48}
root=/tmp/qtn-5g-watchdog-soak
cli=/tmp/hostapd-cli-qtn-v4

case "$interval:$samples" in
	*[!0-9:]*|:*|*:) exit 181 ;;
esac
mkdir -p "$root"
chmod 0700 "$root"

irq_count()
{
	awk -v irq="$1:" '$1 == irq { gsub(/[^0-9]/, "", $2); print $2; found=1 }
		END { if (!found) print 0 }' /proc/interrupts
}

softirq_count()
{
	awk -v name="$1:" '$1 == name { total=0; for (i=2; i<=NF; i++) total += $i;
		print total; found=1 } END { if (!found) print 0 }' /proc/softirqs
}

stat()
{
	file=/sys/class/net/$1/statistics/$2
	if [ -r "$file" ]; then cat "$file"; else echo na; fi
}

i=0
while [ "$i" -lt "$samples" ]; do
	i=$((i + 1))
	uptime=$(cut -d. -f1 /proc/uptime)
	hostapd=DOWN
	if [ -x "$cli" ] && [ -S /var/run/hostapd/wifi0 ] &&
	   "$cli" -p /var/run/hostapd -i wifi0 ping 2>/dev/null | grep -qx PONG; then
		hostapd=PONG
	fi
	rf=na
	[ ! -r /sys/module/qdrv/parameters/openmitrastar_rf_enable ] ||
		rf=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)
	timer_reclaim=na
	[ ! -r /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable ] ||
		timer_reclaim=$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)
	echo "OM5GSOAK sample=$i uptime=$uptime irq8=$(irq_count 8) irq20=$(irq_count 20) soft_timer=$(softirq_count TIMER) soft_netrx=$(softirq_count NET_RX) eth_rx=$(stat eth0 rx_packets) eth_tx=$(stat eth0 tx_packets) wifi_rx=$(stat wifi0 rx_packets) wifi_tx=$(stat wifi0 tx_packets) hostapd=$hostapd rf=$rf hbm_timer_reclaim=$timer_reclaim" >/dev/console
	sleep "$interval"
done

echo "OM5GSOAK complete samples=$samples interval=$interval" >/dev/console
touch "$root/complete"

