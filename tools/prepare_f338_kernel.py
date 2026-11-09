"""Seed the new F338 GPL kernel side; never modify the F332 evidence tree."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/modules/f332_dfs_provider/provider'
DST=ROOT/'work/kernel-port/f338/kernel'
names=['f332_provider.c','f332_hardware.c','f332_hardware.h','f332_setup.inc',
       'f332_events.c','f332_events.h','f332_ocac.c','f332_ocac.h',
       'f327_oem_requests.h','f316_portable.h','Makefile']
def main():
    provenance={}
    for name in names:
        p=SRC/name
        target=DST/name
        if target.exists():raise SystemExit('Refusing to replace '+str(target))
        data=p.read_bytes();provenance[name]=hashlib.sha256(data).hexdigest()
        text=data.decode().replace('f332_pipeline.h','f338_pipeline.h')
        if name=='Makefile':
            text=text.replace('-I$(src)/../engine','-I$(src)/../uapi')
            text=text.replace('qtn_radar_f332','qtn_radar_f338').replace('f332_pipeline.o','f338_pipeline.o f338_protocol.o f338_ipc.o f331_postfilter.o')
        if name=='f332_hardware.c':text=text.replace('OMF332','OMF338')
        target.write_bytes(text.encode())
    p=ROOT/'work/kernel-port/modules/f332_dfs_provider/engine/f332_detector.h'
    (DST/p.name).write_bytes(p.read_bytes());provenance[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    for base,names2 in [('f331_postfilter',['f331_postfilter.c','f331_postfilter.h']),('f333_acquisition',['f333_acquisition.c','f333_acquisition.h'])]:
        for name in names2:
            p=ROOT/'work/kernel-port/modules'/base/name
            (DST/name).write_bytes(p.read_bytes());provenance[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (DST/'seed-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
if __name__=='__main__':main()
