"""F366r2 adds the actual native enable call and verifies startup before sampling."""
import f366_runtime_contract as old
VERSION='lyoko-foundation-6.10.3-f366r2-native-start-diagnostic'
def native_start(source,base_qdrv_sha,new_qdrv_sha):
 s=old.native_start(source,base_qdrv_sha,new_qdrv_sha).decode()
 anchor='openmitrastar_sequential_bringup=1 openmitrastar_single_vap_create=0'
 if s.count(anchor)!=3:raise ValueError('native qdrv profile branches changed')
 s=s.replace(anchor,anchor+' openmitrastar_native_radar_diagnostic=1')
 anchor='/usr/sbin/om-f366-stage complete radio-nondfs || refuse f366-wdt-radio-complete\n'
 block='''/usr/sbin/om-f366-stage complete radio-nondfs || refuse f366-wdt-radio-complete
/usr/sbin/om-f366-stage begin native-radar 30000 || refuse f366-wdt-native-begin
/usr/sbin/om-f366-stage verify native-radar || refuse f366-wdt-native-health
printf 'OMF366_NATIVE_START_ATTEMPT command=radar-enable-eu authority=0\n'
control_set 'radar enable eu' native-radar-enable
grep -qx 'started=1' /proc/openmitrastar_radar_f366/status || refuse f366-native-not-started
grep -qx 'hardware_dirty=1' /proc/openmitrastar_radar_f366/status || refuse f366-native-not-touched
# IIR and the first transaction are asynchronous after callback registration.
# Observe the same single activation; never retry radar enable.
f366_native_wait=0
f366_native_jobs=0
while [ "$f366_native_wait" -lt 5 ]; do
 /usr/sbin/om-f366-stage verify native-radar || refuse f366-wdt-native-health
 grep -qx 'engine_fault_latched=0' /proc/openmitrastar_radar_f366/status || refuse f366-native-engine-fault
 f366_native_jobs=$(awk -F= '$1=="jobs_completed" {print $2}' /proc/openmitrastar_radar_f366/status)
 case "$f366_native_jobs" in ''|*[!0-9]*) refuse f366-native-invalid-jobs;; esac
 if grep -qx 'hardware_ready=1' /proc/openmitrastar_radar_f366/status && [ "$f366_native_jobs" -gt 0 ]; then break; fi
 f366_native_wait=$((f366_native_wait+1)); sleep 1
done
grep -qx 'hardware_ready=1' /proc/openmitrastar_radar_f366/status || refuse f366-native-not-hardware-ready
[ "$f366_native_jobs" -gt 0 ] || refuse f366-native-no-first-job
grep -qx 'engine_fault_latched=0' /proc/openmitrastar_radar_f366/status || refuse f366-native-engine-fault
grep -qx 'callbacks=0' /proc/openmitrastar_radar_f366/status || refuse f366-native-callback
printf 'OMF366_NATIVE_STARTED started=1 hardware_dirty=1 hardware_ready=1 authority=0\n'
/usr/sbin/om-f366-stage complete native-radar || refuse f366-wdt-native-complete
'''
 s=old.once(s,anchor,block);return s.encode()
def overlay():
 result=old.overlay();key='usr/sbin/om-f366-stage'
 result[key]=result[key].replace(b'module-load|core-start|vap-create|radio-nondfs|pipeline-observe',b'module-load|core-start|vap-create|radio-nondfs|native-radar|pipeline-observe')
 key='usr/sbin/om-f366-diagnostic';s=result[key].decode()
 anchor='"$stage" begin pipeline-observe 30000 || { failure_snapshot observe-phase-failed; exit 49; }'
 s=old.once(s,anchor,"grep -qx 'started=1' \"$provider/status\" || { failure_snapshot native-not-started; exit 58; }\ngrep -qx 'hardware_dirty=1' \"$provider/status\" || { failure_snapshot native-not-touched; exit 58; }\n"+anchor)
 result[key]=s.encode();return result
