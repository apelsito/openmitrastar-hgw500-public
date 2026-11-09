"""Inventory retained compiled HBM header users and duplicate weak API bodies.

Static evidence only. This maps the closure a future provider fence must rebuild;
it does not replace the header or certify module linkage/hardware ownership.
"""
import argparse
import hashlib
import json
from pathlib import Path
from qualify_f370_qdrv_module import Elf

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1]
    bases=[root/'work/linux510-radio-port/quantenna/qdrv',root/'work/linux510-radio-port/quantenna/platform/topaz',root/'work/linux510-radio-port/quantenna/platform/ruby',root/'work/linux510-radio-port/quantenna/wlan']
    commands=[];modules=[];pins={str(Path(__file__)):sha(Path(__file__))}
    for base in bases:
        if not base.is_dir():continue
        for cmd in sorted(base.glob('.*.o.cmd')):
            if 'topaz_hbm_cpuif.h'not in cmd.read_text():continue
            commands.append(dict(path=str(cmd),unit=cmd.name[1:-6],sha256=sha(cmd)));pins[str(cmd)]=sha(cmd)
        for path in sorted(base.glob('*.ko')):
            e=Elf(path);defined=[dict(name=s['name'],bytes=s['size'],bind=s['bind'],section=e.symsection(s))for s in e.syms if s['section'] and s['type']==2 and s['name']in ('topaz_hbm_put_buf','topaz_hbm_get_buf')]
            imported=sorted(s['name']for s in e.syms if not s['section'] and s['name'].startswith('topaz_hbm'))
            if defined or imported:
                modules.append(dict(path=str(path),sha256=sha(path),weak_or_local_bodies=defined,hbm_imports=imported));pins[str(path)]=sha(path)
    header=root/'work/sources/Quantenna-GPL/include/qtn/topaz_hbm_cpuif.h';pool=root/'work/sources/Quantenna-GPL/common/ruby_mem.h';mem=root/'work/sources/Quantenna-GPL/common/common_mem.h'
    for x in(header,pool,mem):pins[str(x)]=sha(x)
    result=dict(schema='openmitrastar.hbm-lhost-header-closure/v1',status='OBSERVED_RETAINED_HEADER_CONSUMER_AND_DUPLICATE_BODY_CLOSURE_REQUIRED',hardware_accessed=False,firmware_eligible=False,compiled_header_units=len(commands),commands=commands,modules=modules,input_pins=pins,requestor_mapping=dict(linux=0,muc=1,auc=6,dsp=7),source_callers=[dict(path='work/linux510-radio-port/quantenna-f344-peers/platform/topaz/hbm.c',calls=['pool creation','txdone pool consume','safe release','skb copy attach','lifecycle direct release']),dict(path='work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_emac.c',calls=['descriptor buffer free via realign void']),dict(path='work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c',calls=['tqe rx cleanup via void filter']),dict(path='work/linux510-radio-port/quantenna-f344-peers/platform/topaz/topaz_congest_queue.c',calls=['unmarked packet cleanup via void filter']),dict(path='work/sources/Quantenna-GPL/drivers/qdrv/qdrv_rx.c',calls=['receive cleanup','descriptor allocation direct put']),dict(path='work/sources/Quantenna-GPL/drivers/qdrv/qdrv_txbf.c',calls=['beamforming attach failure direct put']),dict(path='work/sources/Quantenna-GPL/drivers/qdrv/qdrv_wlan.c',calls=['buffer release direct realign put'])],integration_required=['Provider must own requestor0 generation/pending operation/lifetime pin; consumer-local static state is insufficient.','Redirect original Linux weak public get/put plus private nowait/direct runtime primitives; rebuild and qualify every compiled header user.','Void release refusal needs durable owner retention before callers discard descriptors/head ownership.','No arbitrary retained-owner ledger capacity: reserve from known actual buffer/requestor bounds before any publication or refcount mutation.','Preserve original ec1/fc0 recycle ABI; hardware/multiple-processor allocation generation and stale duplicate ABA remain unproven.','Pool lifecycle register reset and provider unload need quarantine fences and explicit recovery proof; neither is authorized or implemented here.'],limits='Retained .cmd dependency inventory covers selected historical directories; it is not a complete newly compiled module closure. Source caller list is orientation to active-selected versions and must be reconciled with their actual build pins. Foreign processors, MMIO timing, runtime/client/firmware remain unqualified.')
    for path,h in pins.items():assert sha(Path(path))==h
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ('input_pins','commands','source_callers')},indent=2))

if __name__=='__main__':main()
