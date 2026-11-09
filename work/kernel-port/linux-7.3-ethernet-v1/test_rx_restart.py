#!/usr/bin/env python3
"""Re-run the existing RX helper/caller fixture using actual Linux7.3 iopoll.
Reads pinned candidate inputs and writes a new output. No hardware access.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--kernel-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    module_path=ROOT/'tools/test_f374_ethernet_rx_quiesce.py'
    if not module_path.exists():
        module_path=HERE/'fixtures/test_f374_ethernet_rx_quiesce.py'
    spec=importlib.util.spec_from_file_location('old_fixture',module_path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    source=a.candidate/'driver/qtn-topaz-emac-eth73.c'
    header=a.candidate/'driver/topaz-ethernet.h'
    poll=a.kernel_source/'include/linux/iopoll.h'
    pins={str(f):old.sha(f) for f in [source,header,poll,module_path,Path(__file__)]}
    text=source.read_text()
    helper=old.extract_function(text,'qtn_emac_restart_rx_dma')
    start=text.index('\t\t\t/* Cool down failed attempts too;')
    end=text.index('\n\t\t}\n\t}\n\nrearm_poll:',start)
    caller=text[start:end]
    definitions=header.read_text().replace('#include <linux/bits.h>','').replace('#include <linux/types.h>','')
    macros=''.join(old.extract_macro(poll.read_text(),name) for name in ['poll_timeout_us','read_poll_timeout','readx_poll_timeout','readl_poll_timeout'])
    # 7.3 executes one operation on the first expired iteration; unlike 5.10
    # it has no separate post-expiry read. Fake clock ticks at 2500us.
    tests=old.TESTS.replace('true,5,variant,call','true,4,variant,call')
    tests=tests.replace('BIT(21),BIT(21),BIT(21),BIT(21),0','BIT(21),BIT(21),BIT(21),0')
    tests=tests.replace('false,5,variant,call','false,4,variant,call')
    fixture=old.PREAMBLE+'\n#define barrier() __asm__ volatile("" ::: "memory")\n'+definitions+old.FAKES+macros+helper+'\n'+tests.replace('__CALLER__',caller)
    f=a.output/'fixture.c';f.write_text(fixture)
    cmd=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(f),'-o',str(a.output/'fixture')]
    c=subprocess.run(cmd,capture_output=True);(a.output/'compile.stderr').write_bytes(c.stderr)
    assert c.returncode==0,c.stderr.decode()
    r=subprocess.run([str(a.output/'fixture')],capture_output=True)
    (a.output/'test.stdout').write_bytes(r.stdout);(a.output/'test.stderr').write_bytes(r.stderr)
    report={'schema':'openmitrastar.eth73-rx-restart-fixture/v1','status':'PASS' if r.returncode==0 else 'FAIL',
            'pins':pins,'hardware_accessed':False,'output':r.stdout.decode(),
            'scope':'Actual RX helper and caller tail; full worker/eligibility/real DMA unrun.'}
    for f,d in pins.items():assert old.sha(f)==d
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'result':str(a.output/'result.json'),'tail':r.stdout.decode().splitlines()[-1:]},indent=2))
    assert r.returncode==0,r.stderr.decode()

if __name__=='__main__':main()
