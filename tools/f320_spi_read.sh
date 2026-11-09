#!/bin/sh
# Sent over pinned SSH only after the F320 campaign owns a ready RX capture.
# Placeholders are substituted by f320_campaign.ps1, never by shell evaluation.
set -eu
module=/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-spi-control-probe.ko
name=qtn_topaz_spi_control_probe
fatal_pattern='kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check|MuC:.*exception|MuC has halted|EV_TLB|EV_ProtV|VFS: Unable to mount root'
grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.8.4-f320-spi-control-read-device' /etc/openmitrastar/release
test "$(sha256sum "$module" | cut -d' ' -f1)" = 6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a
# Include the rejected observer and both aliases; a resource claim alone does
# not coordinate code accessing MMIO without request_mem_region().
! grep -Eiq '(^|[ _-])(spi|store).*probe|^qtn_topaz_spi_' /proc/modules
before=$(sha256sum /proc/mtd | cut -d' ' -f1)
fatal_before=$(dmesg | grep -Eic "$fatal_pattern" || true)
test "$fatal_before" = 0
loaded=0
cleanup() { if [ "$loaded" = 1 ]; then rmmod "$name" >/dev/null 2>&1 || true; fi; }
trap cleanup EXIT HUP INT TERM
printf '%s\n' '__CAPTURE_RUN___BEGIN' >/dev/console
# The sole opt-in and the sole load in this campaign. Never retry this command.
insmod "$module" execute_read=1
loaded=1
base=/sys/module/$name/parameters
test "$(cat "$base/execute_read")" = Y
test "$(cat "$base/controller_resource_claimed")" = Y
test "$(cat "$base/controller_mapped")" = Y
test "$(cat "$base/legacy_map_verified")" = Y
test "$(cat "$base/map_read_count")" = 1
test "$(cat "$base/controller_read_count")" = 1
test "$(cat "$base/controller_write_count")" = 0
test "$(cat "$base/transaction_provider_ready")" = N
for key in execute_read controller_resource_claimed controller_mapped legacy_map_verified map_register_value map_read_count controller_value controller_read_count controller_write_count transaction_provider_ready; do
    printf '%s=' "$key"; cat "$base/$key"
done
rmmod "$name"
loaded=0
trap - EXIT HUP INT TERM
after=$(sha256sum /proc/mtd | cut -d' ' -f1)
fatal_after=$(dmesg | grep -Eic "$fatal_pattern" || true)
test "$before" = "$after"
test "$fatal_after" = 0
! grep -q "^$name " /proc/modules
printf 'MTD_TABLE_HASH_BEFORE=%s\nMTD_TABLE_HASH_AFTER=%s\n' "$before" "$after"
printf 'FATAL_BEFORE=%s\nFATAL_AFTER=%s\n' "$fatal_before" "$fatal_after"
echo MODULE_UNLOADED=1
printf '%s\n' '__CAPTURE_RUN___END' >/dev/console
echo OMF320_SPI_CONTROL_PASS
