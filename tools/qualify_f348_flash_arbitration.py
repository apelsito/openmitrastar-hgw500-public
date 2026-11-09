"""Bind F348 offline reader tests, immutable kernel and unchanged mapping profile."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,struct
import f340_watchdog_contract as c
from build_f348_flash_arbitration import FILES,OVERLAY,STAGE

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',required=True,type=Path)
    ap.add_argument('--tests',required=True,type=Path)
    args=ap.parse_args();build=args.build.resolve();tests=args.tests.resolve()
    report=json.loads((build/'result.json').read_text())
    test=json.loads((tests/'result.json').read_text())
    checks=[]
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise ValueError(name)
    check('kernel build and native test outcomes',report['status']=='PASS_OFFLINE_READER_ARBITRATION_KERNEL' and test['status']=='PASS')
    check('no hardware or flash authorization',not report['hardware_actions'] and not report['flash_write_api'] and not report['flash_eligible'] and not test['hardware_actions'])
    for name in FILES:
        check('built overlay exact '+name,(build/'overlay'/name).read_bytes()==(OVERLAY/name).read_bytes())
    check('all current tested sources pinned',all(c.sha(Path(p))==h for p,h in test['sources'].items()))
    check('all build source pins current',all(c.sha(Path(p['path']))==p['sha256'] for p in report['sources']))
    check('all artifact hashes current',all(c.sha(Path(p['path']))==p['sha256'] for p in report['artifacts'].values()))
    names=['f348.vmlinux','f348.config','f348.dtb','f348.raw.bin','Module.symvers']
    check('independent build artifacts identical',all((build/'a'/n).read_bytes()==(build/'b'/n).read_bytes() for n in names))
    cfg=(build/'a/f348.config').read_text().splitlines()
    required=['CONFIG_MMU=y','CONFIG_MTD_ROM=y','CONFIG_MTD_PHYSMAP=y','CONFIG_MTD_BLOCK_RO=y',
      '# CONFIG_DEVMEM is not set','# CONFIG_DEVKMEM is not set','# CONFIG_OF_OVERLAY is not set',
      '# CONFIG_MTD_PHRAM is not set','# CONFIG_MTD_RAM is not set','# CONFIG_MTD_BLOCK2MTD is not set']
    check('static read-only mapping and no direct devmem aliases',all(x in cfg for x in required))
    check('F340 full configuration identical',(build/'a/f348.config').read_bytes()==(STAGE/'a/f340.config').read_bytes())
    check('F340 complete device tree identical',(build/'a/f348.dtb').read_bytes()==(STAGE/'a/f340.dtb').read_bytes())
    nodes=c.node_map(build/'a/f348.dtb')
    actual=[]
    for path,props in nodes.items():
        if props.get('compatible')==b'mtd-rom\0':
            cells=struct.unpack('>II',props['reg'])
            actual.append({'path':path,'name':props['linux,mtd-name'].rstrip(b'\0').decode(),
                           'physical':hex(cells[0]),'bytes':cells[1], 'access':'mtd-rom'})
    expected={(0x90020000,0x10000),(0x90030000,0x10000),(0x90f80000,0x80000),(0x90960000,0x460000),(0x90dc0000,0x1c0000)}
    check('exact five protected DT windows',{(int(x['physical'],16),x['bytes']) for x in actual}==expected and len(actual)==5)
    check('single exact store window',sum(x['name']=='lyoko_store' and x['physical']=='0x90dc0000' and x['bytes']==0x1c0000 for x in actual)==1)
    old=(STAGE/'a/Module.symvers').read_text().splitlines()
    new=(build/'a/Module.symvers').read_text().splitlines()
    added={'qtn_topaz_flash_claim','qtn_topaz_flash_release','qtn_topaz_flash_read_store'}
    check('only three GPL API exports added',set(new)-set(old)=={l for l in new if l.split()[1] in added} and set(old)<=set(new))
    check('kernel change confined to four declared files',len(report['source_delta'])==4)
    check('real pthread concurrency test', 'actual_pthread_exclusion=1' in test['tests']['core.log'])
    check('real adapter and MMU mmap executed', 'real_probe=1 real_mmu_mmap=1' in test['tests']['adapter.log'])
    check('GCC analyzer clean',test['tests']['analyzer.log']=='')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=c.ROOT/'outputs/preflight'/('f348-qualified-'+stamp);out.mkdir(parents=True,exist_ok=False)
    result={'schema':'openmitrastar.f348-reader-arbitration-qualification/v1',
       'status':'PASS_OFFLINE_READER_ARBITRATION', 'created_utc':stamp,'checks':checks,
       'kernel_manifest':{'path':str(build/'result.json'),'sha256':c.sha(build/'result.json')},
       'tests':{'path':str(tests/'result.json'),'sha256':c.sha(tests/'result.json')},
       'dt_views':actual,'kernel_identity':'#348; unmodified F340 DT and release',
       'physical_gates':'UNRUN','hardware_actions':False,'flash_write_api':False,'flash_eligible':False,
       'coverage':'cooperating MTD/MTDblock readers and explicit provider claim on this fixed HGW profile',
       'not_proven':['electrical SPI arbitration','command completion/read-array state','DMA or arbitrary external kernel MMIO','physical filesystem acceptance'],
       'lifetime':'claim/release same process-context task; preallocated nonfaulting memory; explicit release only; no mapper changes or recursive mtd_read; provider completion required before release',
       'qualifier':{'path':str(Path(__file__).resolve()),'sha256':c.sha(Path(__file__))}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'result':str(out/'result.json')}))
if __name__=='__main__':main()
