"""Compare coherent peers with exact hash-verified module files inside F321."""
from pathlib import Path
from datetime import datetime,timezone
import bisect,hashlib,json,re,shlex,subprocess
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
PEERS=BASE/'analysis/f332-peers-20260921T121519Z'
FIRM=BASE/'firmware/f321-f314-device-bound'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def functions(path):
 with path.open('rb') as f:
  elf=ELFFile(f);sections=list(elf.iter_sections());relocs={}
  for s in sections:
   if isinstance(s,RelocationSection):relocs.setdefault(int(s['sh_info']),[]).extend(int(r['r_offset']) for r in s.iter_relocations())
  for values in relocs.values():values.sort()
  result={};occurrence={}
  for sym in elf.get_section_by_name('.symtab').iter_symbols():
   index=sym['st_shndx'];start=int(sym['st_value']);size=int(sym['st_size'])
   if sym['st_info']['type']!='STT_FUNC' or not size or not isinstance(index,int) or not index:continue
   section=sections[index];body=bytearray(section.data()[start:start+size]);values=relocs.get(index,[])
   for offset in values[bisect.bisect_left(values,start):bisect.bisect_left(values,start+size)]:
    pos=offset-start;body[pos:pos+4]=b'\0'*min(4,size-pos)
   label=section.name+':'+sym.name;number=occurrence.get(label,0);occurrence[label]=number+1
   result[label+'#'+str(number)]={'bytes':size,'sha256':hashlib.sha256(body).hexdigest()}
  return result
def main():
 proof=json.loads((PEERS/'result.json').read_text());require(proof['status']=='PASS_COHERENT_PEERS_OFFLINE','peer build unqualified')
 inventory=json.loads((FIRM/'rootfs-inventory.json').read_text())['after']
 image=FIRM/'openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs'
 out=BASE/('analysis/f332-peer-abi-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True);(out/'baseline').mkdir()
 paths={Path(k).name:(k,v) for k,v in inventory.items() if k.endswith('.ko')};selected=[];script='set -eu\n'
 for row in proof['modules']:
  name=row['name'];require(re.fullmatch(r'[A-Za-z0-9_.-]+\.ko',name),'unsafe module filename');require(sha(PEERS/'a'/name)==row['sha256'],'peer artifact changed')
  if name not in paths:continue
  inside,meta=paths[name];require('..' not in inside.split('/') and not inside.startswith('/'),'unsafe archive path')
  target=out/'baseline'/name;selected.append((name,meta))
  script+='unsquashfs -cat '+shlex.quote(linux(image))+' '+shlex.quote(inside)+' > '+shlex.quote(linux(target))+'\n'
 (out/'extract.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'extract.sh')],capture_output=True,timeout=90)
 (out/'extract.stderr').write_bytes(p.stderr);require(p.returncode==0,'module-only extraction failed')
 rows=[]
 for name,meta in selected:
  old=out/'baseline'/name;new=PEERS/'a'/name;require(sha(old)==meta['sha256'],'F321 module inventory mismatch')
  before=functions(old);after=functions(new);changed=[key for key in sorted(before.keys()|after.keys()) if before.get(key)!=after.get(key)]
  rows.append({'module':name,'old_sha256':sha(old),'new_sha256':sha(new),'old_functions':len(before),'new_functions':len(after),'changed_functions':changed,'normalized_equal':not changed})
 report={'schema':'openmitrastar.f332-peer-abi-comparison/v1','status':'PASS_HASH_BOUND_COMPARISON_PHYSICAL_PENDING','modules':rows,'peer_build':str(PEERS/'result.json'),'peer_build_sha256':sha(PEERS/'result.json'),'hardware':False,'only_module_files_extracted':True,'physical_abi_acceptance':False}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'modules':[(r['module'],len(r['changed_functions'])) for r in rows]},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
