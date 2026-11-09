#!/usr/bin/env python3
"""Offline paired kernel/module build from pinned archive and candidate inputs.
New output only; no downloads, router or serial operations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
BASIC = HERE.parent/'linux-7.3-basic'
if not BASIC.exists():
    BASIC = HERE.parent/'basic-linux-7.3'
ARCHIVE_SHA = '87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953'
PATCH_SHA = 'd36ed090cdcb9470eb301933c066b2c7cde12de3af5c1cf3d02d9a7509088192'
GCC_SHA = '3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def run(cmd, log, env):
    print('RUN '+str(log),flush=True)
    with log.open('xb') as stream:
        subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, check=True, env=env, timeout=1800)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--toolchain',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--composed-source',type=Path,help='Reuse a verified composed source; build only into a new O= directory.')
    p.add_argument('--plan-only',action='store_true')
    a=p.parse_args()
    assert not a.output.exists(),'New output required'
    assert sha(a.archive)==ARCHIVE_SHA
    assert sha(BASIC/'basic73.patch')==PATCH_SHA
    tc=str(a.toolchain.resolve()/'bin/arc-snps-linux-uclibc-')
    assert sha(Path(tc+'gcc'))==GCC_SHA
    manifest=json.loads((a.candidate/'manifest.json').read_text())
    for row in manifest['outputs']:
        f=a.candidate/row['path'].replace('\\','/')
        assert f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],row['path']
    report={'schema':'openmitrastar.eth73-paired-build/v1','hardware_accessed':False,
            'candidate_manifest_sha256':sha(a.candidate/'manifest.json'),'archive_sha256':ARCHIVE_SHA,
            'basic_patch_sha256':PATCH_SHA,'compiler_sha256':GCC_SHA,
            'physical_boot':'UNRUN','ethernet_traffic':'UNRUN','status':'PLAN_ONLY'}
    if a.plan_only:
        print(json.dumps(report,indent=2));return
    a.output.mkdir(parents=True)
    env=os.environ.copy()
    env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',
               KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='eth73',KBUILD_BUILD_VERSION='1')
    extra_kconfig='\nconfig QTN_TOPAZ_ETH73\n    bool "Topaz direct Ethernet IRQ gates 19/20"\n    depends on ARC_PLAT_TOPAZ_BASIC && NET\n    select ARCH_NO_PREEMPT\n'
    if a.composed_source:
        source=a.composed_source.resolve()
        for row in json.loads((BASIC/'SOURCE_MANIFEST.json').read_text())['files']:
            if row['path']=='arch/arc/kernel/intc-compact.c':
                expected=sha(a.candidate/'overlay'/row['path'])
            elif row['path']=='arch/arc/plat-topaz-basic/Kconfig':
                assert (source/row['path']).read_text()==(BASIC/'overlay'/row['path']).read_text()+extra_kconfig
                continue
            else:
                expected=row['sha256']
            assert sha(source/row['path'])==expected,row['path']
        for relative,expected in [('include/linux/soc/qtn/topaz-ethernet.h',a.candidate/'driver/topaz-ethernet.h'),
                                 ('arch/arc/boot/dts/topaz_mitrastar_eth73.dts',a.candidate/'overlay/arch/arc/boot/dts/topaz_mitrastar_eth73.dts')]:
            assert sha(source/relative)==sha(expected),relative
        report['reused_composed_source']=str(source)
    else:
        source_root=a.output/'source';source_root.mkdir()
        with tarfile.open(a.archive) as tar:
            tar.extractall(source_root,filter='data')
        source=source_root/'linux-7.3'
        run(['patch','--batch','--fuzz=0','-p1','-d',str(source),'-i',str(BASIC/'basic73.patch')],a.output/'patch.log',env)
        for f in (a.candidate/'overlay').rglob('*'):
            if f.is_file():
                dest=source/f.relative_to(a.candidate/'overlay');dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(f,dest)
        kconfig=source/'arch/arc/plat-topaz-basic/Kconfig'
        with kconfig.open('a') as stream:
            stream.write(extra_kconfig)
        header=source/'include/linux/soc/qtn/topaz-ethernet.h';header.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(a.candidate/'driver/topaz-ethernet.h',header)
    ir=a.output/'initramfs';ir.mkdir()
    # STT_FILE retains the original basename; executable bytes already match.
    init_source=ir/'basic73_init_nolibc_time64_nonce.c'
    shutil.copyfile(BASIC/'init.c',init_source)
    run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles',
         '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra',
         '-Wl,-e,_start','-Wl,--build-id=none','-o',str(ir/'init'),str(init_source)],a.output/'init-build.log',env)
    assert sha(ir/'init')=='9380f5c7b85231ae9320fc70b7b6a922316978c61f69d473907271168ca36194'
    irlist=ir/'initramfs.list'
    irlist.write_text('dir /dev 755 0 0\ndir /proc 755 0 0\ndir /sys 755 0 0\n'
                      'nod /dev/console 600 0 0 c 5 1\nnod /dev/ttyS0 600 0 0 c 4 64\n'
                      'file /init '+str(ir/'init')+' 755 0 0\n')
    lanes=[]
    for lane in ['a','b']:
        out=a.output/lane;out.mkdir()
        module=a.output/('module-'+lane);shutil.copytree(a.candidate/'driver',module)
        (out/'.config').write_text((a.candidate/'eth73.config.template').read_text().replace('@INITRAMFS_LIST@',str(irlist)))
        make=['make','-C',str(source),'O='+str(out),'ARCH=arc','CROSS_COMPILE='+tc]
        flags='KCFLAGS=-ffile-prefix-map='+str(out)+'=/eth73-build -ffile-prefix-map='+str(module)+'=/eth73-module'
        run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
        conf=(out/'.config').read_text()
        for key in ['NET','INET','NETDEVICES','ETHERNET','SYSFS','MODULES','PREEMPT_NONE','QTN_TOPAZ_ETH73','ARC_CPU_750D','ARC_PAGE_SIZE_8K']:
            assert 'CONFIG_'+key+'=y' in conf,key
        for key in ['SMP','PCI','MTD','WLAN','WATCHDOG','ARC_HAS_SWAPE','ARC_HAS_LLSC','PREEMPT_VOLUNTARY']:
            assert 'CONFIG_'+key+'=y' not in conf,key
        run(make+[flags,'-j6','vmlinux','dtbs','modules'],a.output/('build-'+lane+'.log'),env)
        run(make+[flags,'M='+str(module),'-j6','modules'],a.output/('module-'+lane+'.log'),env)
        elf=out/'vmlinux';ko=module/'qtn-topaz-emac-eth73.ko'
        for artifact in [elf,ko,ir/'init']:
            asm=subprocess.check_output([tc+'objdump','-d',str(artifact)],text=True)
            bad=[l for l in asm.splitlines() if re.search(r'\t(?:swape|llock|scond)(?:\t| )',l)]
            assert not bad,(artifact,bad[:4])
        assert not subprocess.check_output([tc+'nm','-u',str(elf)],text=True).strip()
        imports=[l.split()[-1] for l in subprocess.check_output([tc+'nm','-u',str(ko)],text=True).splitlines()]
        exports={l.split()[1] for l in (out/'Module.symvers').read_text().splitlines()}
        assert not set(imports)-exports,sorted(set(imports)-exports)
        dtb=out/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb'
        dts=subprocess.check_output([str(out/'scripts/dtc/dtc'),'-I','dtb','-O','dts',str(dtb)],text=True,stderr=subprocess.DEVNULL)
        (a.output/('resolved-'+lane+'.dts')).write_text(dts)
        assert 'dma-ranges = <0x00 0x80000000 0x8000000>;' in dts
        eth_start=dts.index('ethernet@e8000000 {')
        eth=dts[eth_start:dts.index('serial@f0000000 {',eth_start)]
        assert 'status = "disabled";' in eth and 'mac-address' not in eth
        lanes.append({'lane':lane,'vmlinux_sha256':sha(elf),'vmlinux_bytes':elf.stat().st_size,
                      'module_sha256':sha(ko),'module_bytes':ko.stat().st_size,'module_imports':len(imports),
                      'config_sha256':sha(out/'.config'),'dtb_sha256':sha(dtb),'forbidden_instructions':0})
    report.update(status='PASS_OFFLINE_PAIRED_KERNEL_MODULE_NO_GO_HARDWARE',lanes=lanes,
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  paired_identical=all(lanes[0][k]==lanes[1][k] for k in ['vmlinux_sha256','module_sha256','config_sha256','dtb_sha256']),
                  module_loaded=False,dt_ethernet_enabled=False)
    assert report['paired_identical'],'Paired builds differ'
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
