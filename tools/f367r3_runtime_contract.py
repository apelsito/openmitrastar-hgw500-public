"""F367r3 retains the protected preamble and fixes lock release on actual HGW tools."""
from pathlib import Path
import f367r2_runtime_contract as previous
ROOT=Path(__file__).resolve().parents[1]
VERSION='lyoko-foundation-6.11.2-f367r3-owned-lock-release-device'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.2-f367r3-owned-lock-release/overlay'
def native_start(source,base_qdrv_sha,new_qdrv_sha):return previous.native_start(source,base_qdrv_sha,new_qdrv_sha)
def overlay():return {p.relative_to(OVERLAY).as_posix():p.read_bytes() for p in OVERLAY.rglob('*') if p.is_file()}
