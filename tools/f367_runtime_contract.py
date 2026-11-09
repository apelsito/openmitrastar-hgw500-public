"""F367 AP gate runtime derived from the physically accepted R3 bootstrap."""
from pathlib import Path
import f366r3_runtime_contract as r3
ROOT=Path(__file__).resolve().parents[1]
VERSION='lyoko-foundation-6.11.0-f367-ap-dfs-device'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.0-f367-ap-dfs/overlay'
def native_start(source,base_qdrv_sha,new_qdrv_sha):
 s=r3.native_start(source,base_qdrv_sha,new_qdrv_sha).decode().replace('f366','f367').replace('F366','F367')
 s=s.replace('authoritative_enable=0','authoritative_enable=1').replace('authority=0','authority=1')
 return s.encode()
def overlay():
 return {p.relative_to(OVERLAY).as_posix():p.read_bytes() for p in OVERLAY.rglob('*') if p.is_file()}
