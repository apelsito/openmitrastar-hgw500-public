"""Bounded consumer ledger from existing exact OEM Ghidra export, offline only.

Offset matching is lexical in derived pseudocode, not a CFG/alias proof. It
helps identify required behavior consumers before appending recovered state.
No binary strings, client identities, calibration payloads or runtime logs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT=Path(__file__).resolve().parents[1]
FIELDS={
 'coexistence449':('0x5dac',), 'autosel461':('0x4df0',), 'maxbw460':('0x4df1',),
 'vopt481':('0x4df4','0x4df5'), 'channelcurrent464':('0x4e2c',),
 'rbsmeasurement466':('0x5d88',), 'rbsclose468':('0x5da8',),
 'weather478':('0xbf4',), 'bbdf483':('0x5d3d',),
 'amsdu11n484':('0xc55',), 'coc491':('0x5e14',), 'neighbor492':('0x5e18',),
 'bsstm493':('0x5e1c',), 'mdid494':('0xf8c',), 'ftoverds495':('0xf8e',),
 'duprts498':('0x535c',),
}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def blocks(text):
 matches=list(re.finditer(r'/\* =+\n \* ([^\n]+) @ ([^\n]+)\n \* bytes=(\d+) instructions=(\d+)\n \* =+ \*/',text))
 for i,m in enumerate(matches):
  end=matches[i+1].start() if i+1<len(matches)else len(text)
  yield dict(name=m[1],address=m[2],bytes=int(m[3]),instructions=int(m[4]),text=text[m.end():end])


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 sources={n:ROOT/'outputs/radio-re/decompiled/full'/(n+'.ko.decompiled.c')for n in('qdrv','wlan')}
 entries={name:[]for name in FIELDS};function_count={}
 for lane,path in sources.items():
  text=path.read_text(encoding='utf-8');count=0
  for body in blocks(text):
   count+=1
   for name,offsets in FIELDS.items():
    hits=[]
    for line in body['text'].splitlines():
     if any(re.search(re.escape(offset)+r'\b',line)for offset in offsets):hits.append(line.strip())
    if hits:
     entries[name].append(dict(lane=lane,function=body['name'],analysis_address=body['address'],body_bytes=body['bytes'],pseudocode_sha256=hashlib.sha256(body['text'].encode()).hexdigest(),hits=hits,evidence='LEXICAL_OFFSET_HITS_IN_DERIVED_PSEUDOCODE_NOT_ALIAS_OR_RUNTIME_PROOF'))
  function_count[lane]=count
 a.output.mkdir(parents=True,exist_ok=False)
 result=dict(status='PASS_OEM_DERIVED_FIELD_CONSUMER_INDEX',hardware_accessed=False,firmware_eligible=False,source_exports={n:dict(path=str(p),sha256=sha(p))for n,p in sources.items()},function_count=function_count,fields={n:dict(oem_offsets=offsets,consumers=entries[n])for n,offsets in FIELDS.items()},limits=['A matchingnumericaloffsetmayoccurinotherobjects; checkbase/type first.','No-hitsdoesnotproveabsence becausedecompilerforms/indirectaliases vary.','Existingexportsarederivedevidence; exactfreshREA/assembly usedforpromotion.'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({n:[x['lane']+':'+x['function']for x in values]for n,values in entries.items()}))


if __name__=='__main__':main()
