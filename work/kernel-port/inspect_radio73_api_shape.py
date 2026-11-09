"""Only public script shapes, never credentials."""
from pathlib import Path
import json,hashlib
root=Path('/home/rea/openmitrastar-linux73-20261022T135100Z/radioeth73-secure-ram-v1/initramfs/root')
for p in sorted((root/'www/api/v1').iterdir()):
 if not p.is_file():continue
 print(json.dumps({'name':p.name,'symlink':p.is_symlink(),'mode':oct(p.stat().st_mode&0o777),'head':repr(p.read_bytes()[:80])}))
p=Path('/workspace/user-home/Desktop/MitraStar/work/kernel-port/linux-7.3-radioeth-ram-v1/init-secure-v2.c')
print(json.dumps({'init_hash':hashlib.sha256(p.read_bytes()).hexdigest()}))
