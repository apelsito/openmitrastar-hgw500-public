"""Read only cached F363 hwmon activation state; never sample the sensor."""
from f336_wdt_ram_executor import require
def command():
 return r'''printf 'temp_module='; if [ -d /sys/module/temp_sens ]; then echo 1; else echo 0; fi
printf 'hwmon_module='; if [ -d /sys/module/hwmon ]; then echo 1; else echo 0; fi
printf 'module_version='; cat /sys/module/temp_sens/version
count=0
for d in /sys/class/hwmon/hwmon*; do
 [ -r "$d/name" ] || continue
 [ "$(cat "$d/name")" = topaz_internal ] || continue
 count=$((count+1))
 printf 'enabled='; cat "$d/enabled"
 printf 'activation_attempted='; cat "$d/activation_attempted"
 printf 'activation_error='; cat "$d/activation_error"
done
printf 'sensor_count=%s\n' "$count"
'''
def validate(data):
 pairs=[line.split('=',1) for line in data.decode('ascii').splitlines()]
 require(all(len(p)==2 for p in pairs) and len({p[0] for p in pairs})==len(pairs),'thermal_status_response')
 rows=dict(pairs)
 require(rows==dict(temp_module='1',hwmon_module='1',module_version='363',enabled='0',activation_attempted='0',activation_error='-19',sensor_count='1'),'thermal_default_not_inactive')
 return dict(sensor='topaz_internal',module_version=363,enabled=False,activation_attempted=False,activation_error=-19,cached_status_only=True,sensor_mmio_requested=False)
