"""Read-only inspection of exact local R2 integration inputs; never prints secrets."""
from pathlib import Path
import hashlib,json,os,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
paths=[
 BASE/'radioeth73-events-ram-v2',
 BASE/'radioeth73-secure-ram-v1/initramfs',
 BASE/'radioeth73-events-artifact-v1',
 BASE/'radioeth73-doom-complete-size-v1/root',
 BASE/'uhttpd73-wasm-mime-v1/a/uhttpd',
 BASE/'dropbear73-pie-qualified-v1/dropbearmulti-a',
]
for p in paths:
 row={'path':str(p),'exists':p.exists(),'symlink':p.is_symlink()}
 if p.is_file():row.update(bytes=p.stat().st_size,sha256=sha(p))
 elif p.is_dir():row['children']=sorted(x.name for x in p.iterdir())
 print(json.dumps(row))
root=BASE/'radioeth73-secure-ram-v1/initramfs/root'
for rel in ['etc/lyoko/web.password','bin/id','usr/sbin/dropbearmulti','usr/sbin/uhttpd','init','www/Doom','etc/uhttpd.conf']:
 p=root/rel;row={'relative_path':rel,'exists':p.exists(),'symlink':p.is_symlink()}
 if p.is_file() and not p.is_symlink():
  row.update(bytes=p.stat().st_size,mode=oct(p.stat().st_mode&0o777))
  if rel!='etc/lyoko/web.password':row['sha256']=sha(p)
 print(json.dumps(row))
context=BASE/'radioeth73-events-ram-v2'
for lane in ['a','b']:
 config=(context/lane/'.config').read_text()
 print(json.dumps({'lane':lane,'selected_config':[l for l in config.splitlines() if any(k in l for k in ['BINFMT_SCRIPT','INITRAMFS','LOCALVERSION','MODVERSIONS','DEBUG_INFO'])]}))
for p in (BASE/'radioeth73-events-artifact-v1').glob('*.json'):
 data=json.loads(p.read_text());print(json.dumps({'receipt':str(p),'keys':list(data)}))
game=BASE/'radioeth73-doom-complete-size-v1/root/www/Doom'
print(json.dumps({'game':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(game.iterdir()) if p.is_file()]}))
print(json.dumps({'source_realpath':str((context/'source').resolve()),'source_is_symlink':(context/'source').is_symlink()}))
