"""Restore the exact OEM radar filter-width setter before the unchanged R2 guard."""
import f366r2_runtime_contract as previous
VERSION='lyoko-foundation-6.10.4-f366r3-radar-filter-start-diagnostic'
def native_start(source,base_qdrv_sha,new_qdrv_sha):
 s=previous.native_start(source,base_qdrv_sha,new_qdrv_sha).decode()
 anchor="control_set 'radar enable eu' native-radar-enable"
 if s.count(anchor)!=1:raise ValueError('native enable anchor changed')
 setup='''# Exact OEM start-vap contract. This ioctl case only assigns ic_radar_bw.
# Keep operational mode/channel checks and the strict qdrv cached guard.
/usr/sbin/iwpriv-qtn wifi0 radar_bw 80 >"$state/radar-bw-set.log" 2>&1 || refuse f366-native-radar-bw-set
printf 'OMF366_NATIVE_FILTER_CONFIG radar_bw=80 setter=ieee80211-param-235 authority=0\n'
control_set 'radar enable eu' native-radar-enable'''
 return s.replace(anchor,setup,1).encode()
def overlay():return previous.overlay()
