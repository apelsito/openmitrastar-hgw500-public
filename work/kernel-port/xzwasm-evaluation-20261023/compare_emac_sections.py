"""Diagnose exact ELF section differences; prints sizes/hashes, never secrets."""
from pathlib import Path
import hashlib,json,struct
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
def sections(p):
 data=p.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
 rows=[struct.unpack_from('<10I',data,h[6]+i*40) for i in range(h[12])]
 s=rows[h[13]];names=data[s[4]:s[4]+s[5]]
 out={}
 for s in rows:
  name=names[s[0]:names.find(b'\0',s[0])].decode()
  content=data[s[4]:s[4]+s[5]] if s[1]!=8 else b''
  out[name]={'bytes':s[5],'flags':s[2],'sha256':hashlib.sha256(content).hexdigest(),'data':content}
 return out
a=sections(BASE/'radioeth73-secure-ram-v1/initramfs/root/qtn-topaz-emac-eth73.ko')
b=sections(BASE/'radioeth73-integrated-r2-revision2-20261022T2232Z/emac-a/qtn-topaz-emac-eth73.ko')
for key in sorted(a.keys()|b.keys()):
 aa=a.get(key,{});bb=b.get(key,{})
 if aa.get('sha256')==bb.get('sha256'):continue
 row={'section':key,'before':{k:v for k,v in aa.items() if k!='data'},'after':{k:v for k,v in bb.items() if k!='data'}}
 if key in ('.modinfo','.comment'):row.update(before_text=aa.get('data',b'').decode(errors='replace'),after_text=bb.get('data',b'').decode(errors='replace'))
 if key=='.rodata':
  left=set(aa['data'].split(b'\0'));right=set(bb['data'].split(b'\0'))
  row['changed_strings_before']=[s.decode(errors='replace') for s in left-right if len(s)>4]
  row['changed_strings_after']=[s.decode(errors='replace') for s in right-left if len(s)>4]
 print(json.dumps(row))
