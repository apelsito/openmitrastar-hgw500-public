"""Read-only common-kernel gap inventory; no device or compiler invocation."""
from pathlib import Path
import hashlib,json
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
FIVE=Path('/home/rea/openmitrastar-aelita-source-fullbuild-20261022T233000Z-r1/kernel-context')
SOURCE5=FIVE.parent/'kernel-source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def config(p):
 out={}
 for line in p.read_text().splitlines():
  if line.startswith('CONFIG_'):out[line.split('=',1)[0]]=line.split('=',1)[1]
  elif line.startswith('# CONFIG_') and line.endswith(' is not set'):out[line[2:-11]]='n'
 return out
def main():
 radio=BASE/'radioeth73-events-ram-v2/a'
 for p in [FIVE,SOURCE5]:
  print(json.dumps({'path':str(p),'exists':p.exists(),'children':sorted(x.name for x in p.iterdir())[:20] if p.is_dir() else []}))
 left=config(radio/'.config');right=config(FIVE/'.config')
 changes=[{'option':k,'radio2g':left.get(k),'radio5g':right.get(k)} for k in sorted(left.keys()|right.keys()) if (left.get(k) or 'n')!=(right.get(k) or 'n')]
 print(json.dumps({'radio2g_config_sha256':sha(radio/'.config'),'radio5g_config_sha256':sha(FIVE/'.config'),'config_differences':changes},indent=2))
 for p in [radio/'include/generated/utsrelease.h',FIVE/'include/generated/utsrelease.h']:
  print(json.dumps({'path':str(p),'text':p.read_text().strip()}))
 # Pin the hardware files rather than broadly scan toolchain/source trees.
 for rel in ['include/linux/skbuff.h','include/linux/netdevice.h','arch/arc/mm/init.c','arch/arc/kernel/setup.c','arch/arc/kernel/reset.c','arch/arc/boot/dts/topaz_mitrastar_eth73.dts','arch/arc/mm/ioremap.c']:
  a=BASE/'radioeth73-events-ram-v2/source'/rel
  b=SOURCE5/rel
  print(json.dumps({'file':rel,'radio2g_sha256':sha(a) if a.is_file() else None,'radio5g_sha256':sha(b) if b.is_file() else None}))
 candidate=Path('/workspace/user-home/Desktop/MitraStar/outputs/rea/linux73-carrier-writer-candidate-20261023T053000Z-r24')
 data=json.loads((candidate/'result.json').read_text())
 print(json.dumps({'candidate_keys':list(data),'kernel_overlay':{k:v for k,v in data['files'].items() if k.replace('\\','/').startswith('kernel-overlay/')},'new_kernel_config_required':data.get('new_kernel_config_required')},indent=2))
if __name__=='__main__':main()
