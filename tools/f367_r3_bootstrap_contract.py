"""Pure source template: R3 bootstrap for the unpromoted F367 AP profile."""
import f366r3_runtime_contract as r3
def native_start(source,base_qdrv_sha,new_qdrv_sha):
 data=r3.native_start(source,base_qdrv_sha,new_qdrv_sha)
 data=data.replace(b'f366',b'f367').replace(b'F366',b'F367')
 # This prepared template cannot be installed/executed as an operational
 # profile. A later, evidence-gated image builder owns promotion explicitly.
 gate=b'''# F367 source preparation only: no installed release/profile gate exists.
printf 'OMF367_BOOTSTRAP_NOT_PROMOTED authority=0 hardware_actions=0\\n' >&2
exit 78
'''
 lines=data.splitlines(keepends=True)
 return lines[0]+gate+b''.join(lines[1:])
def overlay():
 return {name.replace('f366','f367'):data.replace(b'f366',b'f367').replace(b'F366',b'F367') for name,data in r3.overlay().items()}
