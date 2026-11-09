#!/usr/bin/env python3
"""Offline ELF/DT/source-identity and failure-injection audit; fresh output only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile

HERE=Path(__file__).resolve().parent
BASIC=HERE.parent/'linux-7.3-basic'
if not BASIC.exists():
    BASIC=HERE.parent/'basic-linux-7.3'

def sha(data):return hashlib.sha256(data).hexdigest()

def elf_at(data,address,size):
    h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    assert h[0][:7]==b'\x7fELF\x01\x01\x01' and h[1:4]==(2,93,1)
    for i in range(h[12]):
        s=struct.unpack_from('<10I',data,h[6]+i*40)
        if s[1]!=8 and s[3]<=address and address+size<=s[3]+s[5]:
            return data[s[4]+address-s[3]:s[4]+address-s[3]+size]
    raise ValueError('Address not backed by ELF section')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--toolchain',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    # Full pristine-source comparison, not only the 16 changed platform files.
    expected={}
    for f in (BASIC/'overlay').rglob('*'):
        if f.is_file():expected[f.relative_to(BASIC/'overlay').as_posix()]=f.read_bytes()
    for f in (a.candidate/'overlay').rglob('*'):
        if f.is_file():expected[f.relative_to(a.candidate/'overlay').as_posix()]=f.read_bytes()
    extra='\nconfig QTN_TOPAZ_ETH73\n    bool "Topaz direct Ethernet IRQ gates 19/20"\n    depends on ARC_PLAT_TOPAZ_BASIC && NET\n    select ARCH_NO_PREEMPT\n'
    expected['arch/arc/plat-topaz-basic/Kconfig']=(BASIC/'overlay/arch/arc/plat-topaz-basic/Kconfig').read_text().encode()+extra.encode()
    expected['include/linux/soc/qtn/topaz-ethernet.h']=(a.candidate/'driver/topaz-ethernet.h').read_bytes()
    checked=0;archive_paths=set()
    with tarfile.open(a.archive) as tar:
        for member in tar:
            relative=member.name.removeprefix('linux-7.3/')
            if member.isfile():
                data=expected.get(relative)
                if data is None:data=tar.extractfile(member).read()
                actual=a.source/relative
                assert actual.is_file() and sha(actual.read_bytes())==sha(data),relative
                checked+=1;archive_paths.add(relative)
            elif member.issym():
                actual=a.source/relative
                # tarfile's data filter normalizes redundant '..' in linknames.
                original_target=(actual.parent/member.linkname).resolve()
                assert actual.is_symlink() and actual.resolve()==original_target,relative
                assert original_target.is_relative_to(a.source.resolve()),relative
                archive_paths.add(relative)
    for relative,data in expected.items():
        assert (a.source/relative).read_bytes()==data,relative
    source_paths={f.relative_to(a.source).as_posix() for f in a.source.rglob('*') if f.is_file() or f.is_symlink()}
    assert not source_paths-(archive_paths|set(expected)),sorted(source_paths-(archive_paths|set(expected)))[:20]
    tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
    dtchecks=[]
    for lane in ['a','b']:
        elf=(a.build/lane/'vmlinux').read_bytes()
        table=subprocess.check_output([tc+'nm',str(a.build/lane/'vmlinux')],text=True)
        symbols={line.split()[-1]:int(line.split()[0],16) for line in table.splitlines() if len(line.split())==3}
        start=symbols['__dtb_topaz_mitrastar_eth73_begin'];end=symbols['__dtb_topaz_mitrastar_eth73_end']
        embedded=elf_at(elf,start,end-start)
        dt=(a.build/lane/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb').read_bytes()
        assert embedded==dt,'Embedded DT differs from sidecar'
        assert struct.unpack_from('>II',dt)==(0xd00dfeed,len(dt))
        assert symbols['_end']<0x88000000
        assert struct.unpack_from('<I',elf,24)[0]==0x8493e000
        assert symbols['res_service']==0x8493e000 and symbols['stext']==0x8493e008
        dtchecks.append({'lane':lane,'dtb_bytes':len(dt),'dtb_sha256':sha(dt),'embedded_equal':True,'kernel_end':hex(symbols['_end'])})
    # Run the real lifecycle fixture with each deliberately broken candidate.
    text=(a.candidate/'driver/qtn-topaz-emac-eth73.c').read_text()
    mutations={
      'ignore-stop-timeout':('ret = qtn_emac_quiesce(emac);\n\tif (ret) {\n\t\tWRITE_ONCE(emac->dma_unsafe, true);\n\t\tnetdev_err', 'ret = qtn_emac_quiesce(emac);\n\tif (ret && false) {\n\t\tWRITE_ONCE(emac->dma_unsafe, true);\n\t\tnetdev_err'),
      'reopen-recycles-descriptors':('if (READ_ONCE(emac->dma_unsafe))\n\t\treturn -EIO;', 'if (false)\n\t\treturn -EIO;'),
      'skip-inherited-quiesce':('ret = qtn_emac_quiesce(emac);\n\tif (ret) {\n\t\tWRITE_ONCE(emac->dma_unsafe, true);\n\t\treturn ret;', 'ret = 0;\n\tif (ret) {\n\t\tWRITE_ONCE(emac->dma_unsafe, true);\n\t\treturn ret;'),
      'free-quarantined-rings':('if (READ_ONCE(emac->dma_unsafe))\n\t\treturn; /* Quarantine until a hardware reset outside this driver. */\n\n\tif (!emac->desc_alloc)', 'if (false)\n\t\treturn; /* Quarantine until a hardware reset outside this driver. */\n\n\tif (!emac->desc_alloc)')}
    negatives=[]
    for name,(old,new) in mutations.items():
        assert text.count(old)==1,name
        folder=a.output/name;shutil.copytree(a.candidate/'driver',folder/'driver')
        (folder/'driver/qtn-topaz-emac-eth73.c').write_text(text.replace(old,new))
        out=a.output/(name+'-fixture')
        cmd=[sys.executable,str(HERE/'test_lifecycle.py'),'--candidate',str(folder),'--kernel-source',str(a.source),'--output',str(out)]
        result=subprocess.run(cmd,capture_output=True)
        (a.output/(name+'.stdout')).write_bytes(result.stdout);(a.output/(name+'.stderr')).write_bytes(result.stderr)
        assert result.returncode!=0,name+' was accepted'
        assert (out/'fixture').exists(),'Mutation rejected before executing fixture'
        assert (out/'test.stderr').read_bytes(),'No executed failure evidence'
        negatives.append({'name':name,'rejected_by_executed_fixture':True,'failure':(out/'test.stderr').read_text().strip()})
    gate=(a.candidate/'overlay/arch/arc/kernel/intc-compact.c').read_text()
    assert '(hwirq != 19 && hwirq != 20)' in gate and 'BIT(hwirq - TOPAZ_BASIC_GATE_BASE)' in gate
    pair=(a.candidate/'driver/f352_pair.inc').read_text()
    assert 'irqdata->hwirq!=irqs[i]' in pair and 'irq_domain_get_of_node' in pair
    report={'schema':'openmitrastar.eth73-audit/v1','status':'PASS_OFFLINE_SOURCE_ELF_AND_NEGATIVE_FIXTURES',
            'hardware_accessed':False,'upstream_files_compared':checked,'source_extra_files':len(set(expected)-archive_paths),
            'embedded_dt':dtchecks,'negative_fixtures':negatives,
            'limits':['No Ethernet physical boot, DMA traffic, cold boot or recovery performed.',
                      'Quarantine retains mapped memory on timeout; it does not recover a hung DMA engine.',
                      'IRQ routing conditions inspected; hardware routing unrun.'],
            'build_result_sha256':sha((a.build/'result.json').read_bytes())}
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
