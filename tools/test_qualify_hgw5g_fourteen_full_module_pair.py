"""Fault-inject parsed copies of actual modules; original ELF files never change."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import qualify_hgw5g_fourteen_full_module_pair as qualify
from qualify_f370_qdrv_module import Elf


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--qdrv-baseline',type=Path,help='Explicit local baseline path for pure offline host parser checks')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
    p=json.loads((a.build/'result.json').read_text())
    old=a.qdrv_baseline if a.qdrv_baseline else Path(p['qdrv_baseline_build'])/'baseline/qdrv.ko'
    new=a.build/'a/qdrv/qdrv.ko'
    cases=[]
    mutations=('correct','text_hole','relocation_target','rodata_byte','string_byte','added_section','section_flags')
    for mutation in mutations:
        def factory(path):
            elf=Elf(path)
            if Path(path)==new:
                if mutation=='text_hole':
                    data=bytearray(elf.byname['.text']['data']);data[133902]^=1;elf.byname['.text']['data']=bytes(data)
                elif mutation=='relocation_target':
                    r=next(r for r in elf.relas if r['section']=='.text' and r['offset']==194)
                    r['addend']+=1
                elif mutation=='rodata_byte':
                    data=bytearray(elf.byname['.rodata']['data']);data[0]^=1;elf.byname['.rodata']['data']=bytes(data)
                elif mutation=='string_byte':
                    data=bytearray(elf.byname['.rodata.str1.4']['data']);data[1]^=1;elf.byname['.rodata.str1.4']['data']=bytes(data)
                elif mutation=='added_section':
                    extra=dict(elf.byname['.rodata']);extra.update(name='.unexpected_extra',index=len(elf.sections))
                    elf.sections.append(extra);elf.byname[extra['name']]=extra
                elif mutation=='section_flags':
                    elf.byname['.rodata']['flags']^=1
            return elf
        error=None
        try:
            with patch.object(qualify,'Elf',factory):
                qualify.audit(old,new,'qdrv')
            passed=True
        except (AssertionError,ValueError,StopIteration) as exc:
            passed=False;error=str(exc)
        # Choose an actual existing relocation deterministically, not a missing
        # fixture anchor; the mutation must reach the audit's comparison gate.
        if mutation=='relocation_target' and isinstance(error,str) and not error:
            raise AssertionError('relocation anchor missing')
        assert passed==(mutation=='correct'),(mutation,passed,error)
        cases.append({'mutation':mutation,'outcome':'PASS' if passed else 'REJECTED','error':error})
    result={'status':'PASS_ACTUAL_MODULE_FAULT_CHECKS','cases':len(cases),'outcomes':cases,'hardware_accessed':False,'original_elf_files_modified':False}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
