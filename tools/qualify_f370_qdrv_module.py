"""Exhaustive ELF32 ARC baseline reconstruction + F370 module qualification.

No disassembly assumptions: compares every allocatable section and every RELA
record of the complete module. Only exact __FILE__ pathname substitutions and
source/build identity metadata are normalized in baseline reconstruction.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import build_f370_qdrv_module as build

def digest(x):return hashlib.sha256(x).hexdigest()
def normalized_path(value):
    oem='/workspace/user-home/Desktop/MitraStar/work/sources/Quantenna-GPL'
    old='/workspace/user-home/Desktop/MitraStar/work/linux510-radio-port/quantenna/qdrv'
    value=value.replace('/f364-qdrv/qdrv/../../../sources/Quantenna-GPL',oem)
    return value.replace('/f364-qdrv/qdrv',old)

class Elf:
    def __init__(self,path):
        self.path=path;self.raw=path.read_bytes()
        assert self.raw[:6]==b'\x7fELF\x01\x01','not ELF32 LE'
        assert struct.unpack_from('<HH',self.raw,16)==(1,93),'not ARC ET_REL'
        off=struct.unpack_from('<I',self.raw,32)[0];size,count,strings=struct.unpack_from('<HHH',self.raw,46)
        table=[struct.unpack_from('<10I',self.raw,off+i*size) for i in range(count)]
        stringtable=self.raw[table[strings][4]:table[strings][4]+table[strings][5]]
        self.sections=[]
        for index,s in enumerate(table):
            name=stringtable[s[0]:stringtable.index(0,s[0])].decode()
            self.sections.append(dict(index=index,name=name,type=s[1],flags=s[2],offset=s[4],size=s[5],link=s[6],info=s[7],align=s[8],entsize=s[9],data=b'' if s[1]==8 else self.raw[s[4]:s[4]+s[5]]))
        self.byname={s['name']:s for s in self.sections};self.syms=[]
        sym=self.byname['.symtab'];names=self.sections[sym['link']]['data']
        for p in range(0,len(sym['data']),sym['entsize']):
            name,value,length,info,other,section=struct.unpack_from('<IIIBBH',sym['data'],p)
            self.syms.append(dict(name=names[name:names.index(0,name)].decode(),value=value,size=length,type=info&15,bind=info>>4,other=other,section=section))
        self.relas=[]
        for s in self.sections:
            if s['type']!=4:continue
            for p in range(0,len(s['data']),s['entsize']):
                offset,info,addend=struct.unpack_from('<IIi',s['data'],p)
                self.relas.append(dict(section=self.sections[s['info']]['name'],offset=offset,type=info&255,symbol=info>>8,addend=addend))
    def symsection(self,sym):return self.sections[sym['section']]['name'] if sym['section']<len(self.sections) else str(sym['section'])
    def cstring(self,section,value):
        data=self.byname[section]['data'];assert 0<=value<len(data),(section,value)
        return data[value:data.index(0,value)].decode('latin1')
    def reloc(self,r):
        s=self.syms[r['symbol']];section=self.symsection(s)
        if section=='.rodata.str1.4':
            target=('cstring',normalized_path(self.cstring(section,s['value']+r['addend'])))
        else:target=(s['name'],section,s['value'],s['size'],s['type'],s['bind'],r['addend'])
        return (r['section'],r['offset'],r['type'],target)
    def symbol(self,s):
        section=self.symsection(s)
        value=normalized_path(self.cstring(section,s['value'])) if section=='.rodata.str1.4' and s['type']!=3 else s['value']
        return (s['name'],section,value,s['size'],s['type'],s['bind'],s['other'])

def baseline_compare(parent,baseline):
    sections=[];errors=[]
    metadata={'.symtab','.strtab','.shstrtab','.note.gnu.build-id','.modinfo'}
    for name in sorted(parent.byname.keys()|baseline.byname.keys()):
        a=parent.byname.get(name);b=baseline.byname.get(name)
        if a is None or b is None:errors.append('section membership '+name);continue
        row={'name':name,'parent_bytes':a['size'],'baseline_bytes':b['size'],'type':a['type'],'flags':a['flags']}
        if a['type']==4:row['comparison']='ALL_RELA_RECORDS_CANONICALIZED_SEPARATELY'
        elif name=='.rodata.str1.4':
            strings=lambda s:Counter(normalized_path(x.decode('latin1')) for x in s['data'].split(b'\0') if x)
            row['comparison']='EXACT_STRINGS_AFTER_DECLARED_FILE_PATH_MAP';row['pass']=strings(a)==strings(b)
            row['path_substitutions']=sum(1 for x in b['data'].split(b'\0') if x and normalized_path(x.decode('latin1'))!=x.decode('latin1'))
            if not row['pass']:row['parent_only']=list((strings(a)-strings(b)).elements());row['baseline_only']=list((strings(b)-strings(a)).elements())
        elif name in metadata:row['comparison']='BUILD_METADATA_SEPARATELY_VALIDATED'
        elif a['type']==8:row['comparison']='NOBITS_SIZE_ALIGNMENT_FLAGS';row['pass']=(a['size'],a['align'],a['flags'])==(b['size'],b['align'],b['flags'])
        else:row.update(comparison='BYTE_FOR_BYTE',**{'pass':a['data']==b['data'],'parent_sha256':digest(a['data']),'baseline_sha256':digest(b['data'])})
        if row.get('pass') is False:errors.append('section '+name)
        sections.append(row)
    ar=[parent.reloc(r) for r in parent.relas];br=[baseline.reloc(r) for r in baseline.relas]
    am=Counter(ar);bm=Counter(br);relocerrors=list((am-bm).elements())+list((bm-am).elements())
    if relocerrors:errors.append('relocation semantic delta')
    asy=Counter(parent.symbol(s) for s in parent.syms);bsy=Counter(baseline.symbol(s) for s in baseline.syms)
    symbolerrors=list((asy-bsy).elements())+list((bsy-asy).elements())
    if symbolerrors:errors.append('symbol semantic delta')
    return dict(status='PASS_FULL_BASELINE_RECONSTRUCTION' if not errors else 'FAIL_BASELINE_RECONSTRUCTION',errors=errors,sections=sections,relocations_total=len(ar),relocations_all_match=ar==br or am==bm,relocation_differences=relocerrors,symbols_total=len(parent.syms),symbol_differences=symbolerrors,function_count=sum(s['type']==2 and s['size']>0 for s in parent.syms),code_allocated_bytes=sum(s['size'] for s in parent.sections if s['flags']&4),limits='ET_REL compile/link comparison before runtime relocations; no hardware/firmware acceptance.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    parent=Elf(build.MODULE);baseline=Elf(args.build/'baseline/qdrv.ko');candidate=Elf(args.build/'a/qdrv.ko')
    comparison=baseline_compare(parent,baseline)
    (args.output/'full-baseline-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    result={'schema':'openmitrastar.f370-module-qualification/v1','status':'NO_GO_OFFLINE','hardware_accessed':False,'firmware_eligible':False,'physical_gates':'UNRUN','full_baseline_comparison_status':comparison['status']}
    try:
        assert comparison['status']=='PASS_FULL_BASELINE_RECONSTRUCTION',comparison['errors']
        pins=json.loads((args.build/'input-pins.json').read_text())
        for path,h in pins.items():assert build.sha(path)==h,'input drift '+path
        assert build.sha(args.build/'a/qdrv.ko')==build.sha(args.build/'b/qdrv.ko'),'candidate reproducibility'
        old_imports=build.imports(build.MODULE)
        for lane in ('baseline','a','b'):assert build.imports(args.build/lane/'qdrv.ko')==old_imports,'imports '+lane
        exports=lambda p:sorted(row.split()[1] for row in p.read_text().splitlines())
        old_exports=exports(build.PARENT/'a/Module.symvers')
        for lane in ('baseline','a','b'):assert exports(args.build/lane/'Module.symvers')==old_exports,'exports '+lane
        old_info=build.modinfo(build.MODULE);base_info=build.modinfo(args.build/'baseline/qdrv.ko');info=build.modinfo(args.build/'a/qdrv.ko')
        for key in set(old_info)|set(base_info):
            if key!='srcversion':assert old_info.get(key)==base_info.get(key),'baseline metadata '+key
        for key in set(old_info)|set(info):
            if key not in ('srcversion','parmtype'):assert old_info.get(key)==info.get(key),'candidate metadata '+key
        added=set(info['parmtype'])-set(old_info['parmtype']);assert added=={p+':uint' for p in build.PARAMETERS},added
        assert set(old_info['parmtype'])<=set(info['parmtype'])
        # Actual complete kernel_param records, independent of strings/modinfo.
        # ARC32 Linux5.10 struct kernel_param is 20 bytes: name/mod/ops,
        # u16 perm + s8 level + u8 flags, then the argument union pointer.
        parameter_section=candidate.byname['__param'];width=20
        assert len(parameter_section['data'])%width==0
        permissions={}
        for r in candidate.relas:
            if r['section']!='__param' or r['offset']%width!=0:continue
            sym=candidate.syms[r['symbol']];s=candidate.symsection(sym)
            name=candidate.cstring(s,sym['value']+r['addend'])
            permissions[name]=struct.unpack_from('<H',parameter_section['data'],r['offset']+12)[0]
        assert all(permissions[name]==0o444 for name in build.PARAMETERS),permissions
        (args.output/'module-parameters.json').write_text(json.dumps({'metadata':info,'permissions':permissions},indent=2)+'\n')
        result.update(status='PASS_OFFLINE_COMPLETE_MODULE',module=dict(path=str(args.build/'a/qdrv.ko'),bytes=(args.build/'a/qdrv.ko').stat().st_size,sha256=build.sha(args.build/'a/qdrv.ko')),reproducible=True,inputs_unchanged=True,imports_unchanged=len(old_imports),exports_unchanged=len(old_exports),new_parameters_0444=sorted(build.PARAMETERS),code_allocated_bytes=comparison['code_allocated_bytes'],baseline_functions=comparison['function_count'],baseline_relocations=comparison['relocations_total'],baseline_symbols=comparison['symbols_total'])
    except Exception as error:result['error']=str(error)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return int(result['status']!='PASS_OFFLINE_COMPLETE_MODULE')
if __name__=='__main__':raise SystemExit(main())
