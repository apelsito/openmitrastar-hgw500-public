#!/bin/ash

set -eu

for parameter in wifi_hw rfic calstate ext_lna_gain ext_lna_bypass_gain \
	tx_power_cal min_tx_power max_tx_power; do
	value=$(cat "/sys/module/board_compat/parameters/$parameter")
	printf '%s=%s\n' "$parameter" "$value"
done

/usr/sbin/iwpriv-qtn wifi0 get_rfchipid 2>/dev/null || true
/usr/sbin/iwpriv-qtn wifi0 get_rfchip_verid 2>/dev/null || true
/usr/sbin/iwpriv-qtn wifi0 get_mode 2>/dev/null || true
/usr/sbin/iwconfig-qtn wifi0 2>/dev/null | grep -E 'ESSID:|Mode:|Frequency:' || true
dmesg | grep -E 'Current RFIC Chip ID|RFIC version|bb_init: FEM|Unsupported FEM|power calibration' || true
