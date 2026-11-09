"""Compare rebuilt baseline function bytes with the retained F367r9 module."""
import argparse
from pathlib import Path
import hashlib,json,struct

def symbols(path):
    data=path.read_bytes();assert data[:6]==b'\x7fELF\x01\x01'
    off=struct.unpack_from('<I',data,32)[0];size,count=struct.unpack_from('<HH',data,46)
    sections=[struct.unpack_from('<10I',data,off+i*size) for i in range(count)]
    rows=[]
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];names=data[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4],section[4]+section[5],section[9]):
            name,value,length,info,other,index=struct.unpack_from('<IIIBBH',data,pos)
            if info&15!=2 or not length or not 0<index<len(sections):continue
            text=names[name:names.index(0,name)].decode('utf8','replace');src=sections[index]
            code=data[src[4]+value:src[4]+value+length]
            rows.append((text,code,length))
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--module',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    original=symbols(a.module);index={}
    for name,code,length in original:index.setdefault(name,[]).append((code,length))
    matches=[];mismatch=[];ambiguous=[]
    for unit in ('qdrv_hostlink','qdrv_wlan'):
        for name,code,length in symbols(a.build/'baseline'/(unit+'.o')):
            candidates=index.get(name,[])
            if len(candidates)!=1:ambiguous.append({'unit':unit,'name':name,'candidates':len(candidates)});continue
            old,size=candidates[0]
            row={'unit':unit,'name':name,'bytes':length,'compiled_sha256':hashlib.sha256(code).hexdigest(),'original_bytes':size,'original_sha256':hashlib.sha256(old).hexdigest()}
            (matches if code==old else mismatch).append(row)
    result={'schema':'openmitrastar.f368-baseline-code-comparison/v1','status':'PASS_UNAMBIGUOUS_FUNCTION_BYTES' if not mismatch else 'FAIL_CODE_MISMATCH','matched_count':len(matches),'mismatched':mismatch,'ambiguous':ambiguous,'matches':matches,'hardware_accessed':False,'limits':'Compares defined unambiguous function bodies in ET_REL before runtime relocation; ambiguous static names excluded; no data-layout or complete linked-module equivalence claim.'}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('matches','ambiguous')}));return int(bool(mismatch))

if __name__=='__main__':raise SystemExit(main())
