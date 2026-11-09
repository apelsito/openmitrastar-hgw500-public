"""R5 publishes the sole DFS target via the OEM regulatory subioctl."""
from pathlib import Path
import f367r4_runtime_contract as previous
ROOT=Path(__file__).resolve().parents[1]
VERSION='lyoko-foundation-6.11.4-f367r5-regulatory-profile-device'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay'
def native_start(source,base_qdrv_sha,new_qdrv_sha):
 data=previous.native_start(source,base_qdrv_sha,new_qdrv_sha)
 anchor=b"control_set 'radar enable eu' native-radar-enable"
 assert data.count(anchor)==1
 return data.replace(anchor,b'''# Publish the classification once, before native radar can create a NOP.
/usr/sbin/om-f367-dfs-profile publish || refuse f367-regulatory-profile52
'''+anchor)
def overlay():return {p.relative_to(OVERLAY).as_posix():p.read_bytes() for p in OVERLAY.rglob('*') if p.is_file()}
