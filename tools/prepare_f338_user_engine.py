"""Seed a NEW F338 userspace math tree; no kernel/module/host modifications."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/kernel-port/f338/userspace'
def main():
 if OUT.exists():raise SystemExit('F338 source directory already exists; preserve it')
 OUT.mkdir(parents=True);rows={}
 for folder,names in (('f332_dfs_provider/engine',('f332_detector_core.c','f332_detector.h','f328_legacy_abi.c','f328_legacy_abi.h')),('f330_oem_preprocess',('f330_preprocess.c','f330_preprocess.h'))):
  for name in names:
   p=ROOT/'work/kernel-port/modules'/folder/name;(OUT/name).write_bytes(p.read_bytes());rows[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
 # The OEM was compiled with gp usable as scratch. A userspace libc may keep
 # its data base there, so every OEM boundary uses an ABI-preserving thunk.
 p=OUT/'f328_legacy_abi.c';s=p.read_text();s=s.replace('#include "f328_legacy_abi.h"','#include "f328_legacy_abi.h"\nextern void f338_oem_timer_call(uint32_t function,uint32_t argument);')
 old='((void (*)(uint32_t))(uintptr_t)fn)(t->data);'
 if s.count(old)!=1:raise ValueError('timer ABI source changed')
 p.write_text(s.replace(old,'f338_oem_timer_call(fn,t->data);'),newline='\n')
 (OUT/'provenance.json').write_text(json.dumps({'source_hashes':rows,'adaptation':'GP-preserving userspace entry/return; timer callbacks use the same wrapper','OEM_code_modified':False},indent=2)+'\n');print(OUT)
if __name__=='__main__':main()
