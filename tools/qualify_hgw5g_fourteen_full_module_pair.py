"""Strict complete-byte/symbol/relocation scope qualification for14entry pair.

Every C unit is rebuilt. The intentionally changed get/set bodies are bounded;
all remaining executable bytes, allocated data and RELA must match after exact
declared size/diagnostic/table insertions. No hardware or source mutation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf, normalized_path
from recover_hgw5g_driver_ops import Elf as OpsElf


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_pinned_json(path,pins):
    raw=Path(path).read_bytes();pins[str(Path(path))]=hashlib.sha256(raw).hexdigest()
    return json.loads(raw.decode('utf-8'))


def normalize_extra(old,new,name,component):
    assert len(old)==len(new)
    result=bytearray(new);changes=[]
    expected={'qdrv_wlan_auth_state_change':18,'qdrv_wlan_exit':18,
              'ieee80211_delete_wlanunit':91,'ieee80211_param_from_qdrv':14,
              'ieee80211_ioctl_giwfreq':14}.get(name)
    if expected:
        for p in range(4,len(old)-3,2):
            if old[p-4:p]==new[p-4:p] and old[p-4:p] in (bytes.fromhex('0a22800f'),bytes.fromhex('0a21800f')):
                h,l=struct.unpack_from('<HH',old,p);nh,nl=struct.unpack_from('<HH',new,p)
                a=(h<<16)|l;b=(nh<<16)|nl
                if a!=b:
                    assert b-a==expected,(name,p,a,b,expected)
                    result[p:p+4]=old[p:p+4];changes.append({'offset':p-4,'kind':'diagnostic_line','old':a,'new':b})
    compact={'qdrv_wlan_get_ocs_frame':(98,'8a22d100','8a221101',36),
             'ieee80211_ioctl_giwfreq':(74,'8a229807','8a22180b',14)}
    if name in compact:
        p,a,b,delta=compact[name]
        assert old[p:p+4]==bytes.fromhex(a) and new[p:p+4]==bytes.fromhex(b),(name,'compact diagnostic encoding')
        result[p:p+4]=old[p:p+4];changes.append({'offset':p,'kind':'compact_diagnostic_line','delta':delta})
    if name=='qdrv_wlan_init':
        for p in (230,252,436):
            assert old[p:p+4]==new[p:p+4] and old[p:p+4] in (bytes.fromhex('0a20800f'),bytes.fromhex('0a22800f'))
            assert old[p+4:p+8]==struct.pack('<HH',0,30552) and new[p+4:p+8]==struct.pack('<HH',0,30556)
            result[p+4:p+8]=old[p+4:p+8];changes.append({'offset':p,'kind':'private_structure_allocation_or_zero_size','old':30552,'new':30556})
    assert bytes(result)==old,'unrelated executable change '+name
    return changes


def audit(oldpath,newpath,component):
    old,new=Elf(oldpath),Elf(newpath)
    assert set(old.byname)==set(new.byname),'exact section membership'
    for name,before in old.byname.items():
        after=new.byname[name]
        for attribute in ('type','flags','align','entsize'):
            assert before[attribute]==after[attribute],'section attribute '+name+' '+attribute
    section_contract={'membership_exact':True,'attributes_checked':['type','flags','align','entsize'],'sections':len(old.byname)}
    assert len(old.syms)==len(new.syms),'symbol membership'
    changed_names={'qdrv_wlan_80211_getparam','qdrv_wlan_80211_setparam'} if component=='qdrv' else {'ieee80211_ioctl_getparam','ieee80211_ioctl_setparam'}
    modified=[];extras=[]
    generated_symbol_renames=[]
    # Match duplicate local function names by unchanged symbol-table order.
    # Every symbol attribute is checked later; no last-name-wins collapse.
    for i,(a,b) in enumerate(zip(old.syms,new.syms)):
        if component=='wlan' and a['name']!=b['name']:
            expected={'CSWTCH.662':'CSWTCH.663','CSWTCH.651':'CSWTCH.652','CSWTCH.717':'CSWTCH.718','CSWTCH.700':'CSWTCH.701','CSWTCH.664':'CSWTCH.665','CSWTCH.715':'CSWTCH.716'}
            assert expected.get(a['name'])==b['name'] and a['type']==b['type']==1 and a['size']==b['size'],'unexpected generated symbol rename'
            generated_symbol_renames.append({'symbol_index':i,'old':a['name'],'new':b['name']})
            b['name']=a['name']
        assert (a['name'],a['type'],a['bind'],a['other'],old.symsection(a))==(b['name'],b['type'],b['bind'],b['other'],new.symsection(b)),'symbol identity '+str(i)
        if a['type']!=2 or not a['size']:continue
        sec=old.symsection(a);x=old.byname[sec]['data'][a['value']:a['value']+a['size']];y=new.byname[sec]['data'][b['value']:b['value']+b['size']]
        if a['name'] in changed_names:
            modified.append({'symbol_index':i,'name':a['name'],'section':sec,'old_value':a['value'],'new_value':b['value'],'old_bytes':a['size'],'new_bytes':b['size'],
                             'old_sha256':hashlib.sha256(x).hexdigest(),'new_sha256':hashlib.sha256(y).hexdigest(),'scope':'INTENTIONALLY_CHANGED_GET_SET_BODY; separate actual-source/ABI fixtures required'})
        elif x!=y:
            extras.append({'symbol_index':i,'name':a['name'],'changes':normalize_extra(x,y,a['name'],component)})
    assert len(modified)==2,'exact2getsetfunctions'
    # QDRV's getter grows54bytes and compiler emits one exact two-byte NOP to
    # retain four-byte alignment of its following anonymous helper body.
    if component in ('qdrv','wlan'):
        row=next(r for r in modified if r['name']==('qdrv_wlan_80211_getparam' if component=='qdrv' else 'ieee80211_ioctl_getparam'))
        end=row['new_value']+row['new_bytes']
        assert new.byname[row['section']]['data'][end:end+2]==bytes.fromhex('e078'),'exact getter alignment NOP'
        row['alignment_nop_bytes']=2
    for row in modified:row['layout_growth']=row['new_bytes']-row['old_bytes']+row.get('alignment_nop_bytes',0)
    executable=[]
    for sec,a in old.byname.items():
        if not a['flags']&4:continue
        x=a['data'];y=bytearray(new.byname[sec]['data'])
        replacements=[]
        for row in modified+extras:
            i=row['symbol_index'];o,n=old.syms[i],new.syms[i]
            if old.symsection(o)==sec:
                replacements.append((n['value'],n['size']+row.get('alignment_nop_bytes',0),x[o['value']:o['value']+o['size']]))
        for value,size,payload in sorted(replacements,reverse=True):y[value:value+size]=payload
        assert x==bytes(y),'all executable bytes outside bounded changes '+sec
        executable.append({'section':sec,'old_bytes':a['size'],'new_bytes':new.byname[sec]['size'],'all_residual_bytes_exact':True})
    @lru_cache(maxsize=None)
    def point(elf,sec,value):
        if sec=='.rodata.str1.4':return ('string',normalized_path(elf.cstring(sec,value)))
        if elf is new:
            original_value=value
            value-=sum(row['layout_growth'] for row in modified
                       if row['section']==sec and original_value>=row['new_value']+row['new_bytes'])
        if component=='wlan' and sec=='.rodata' and elf is new:
            t=next(s for s in new.syms if s['name']=='ieee80211_priv_args')
            if value>=t['value']+t['size']:value-=336
        return ('section',sec,value)
    def is_changed_site(elf,r):
        for row in modified:
            s=elf.syms[row['symbol_index']]
            if r['section']==elf.symsection(s) and s['value']<=r['offset']<s['value']+s['size']:return True
        return False
    def relocation(elf,r):
        if is_changed_site(elf,r):return None
        s=elf.syms[r['symbol']];sec=elf.symsection(s)
        target=point(elf,sec,s['value']+r['addend']) if s['type']==3 or sec=='.rodata.str1.4' else (s['name'],sec,s['type'],s['bind'],r['addend'])
        return (point(elf,r['section'],r['offset']),r['type'],target)
    ar=Counter(v for r in old.relas if (v:=relocation(old,r)) is not None);br=Counter(v for r in new.relas if (v:=relocation(new,r)) is not None)
    delta=list((ar-br).elements())+list((br-ar).elements());assert not delta,'unrelated RELA delta '+str(delta[:5])
    for a,b in zip(old.syms,new.syms):
        if a['type']==3:continue
        size=b['size']
        if a['name'] in changed_names:size=a['size']
        if component=='wlan' and a['name']=='ieee80211_priv_args':size=a['size']
        assert a['size']==size,'symbol size '+a['name']
        if a['name'] in changed_names:continue
        assert point(old,old.symsection(a),a['value'])==point(new,new.symsection(b),b['value']),'symbol position '+a['name']
    data=[]
    for sec,a in old.byname.items():
        b=new.byname.get(sec);assert b is not None,'section membership'
        if a['flags']&4 or a['type']==4 or sec in ('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
        x,y=a['data'],b['data']
        if sec=='.rodata.str1.4':
            norm=lambda value:Counter(normalized_path(z.decode('latin1')) for z in value.split(b'\0') if z)
            assert norm(x)==norm(y),'allstrings'
        elif component=='wlan' and sec=='.rodata':
            t=next(s for s in old.syms if s['name']=='ieee80211_priv_args');n=next(s for s in new.syms if s['name']=='ieee80211_priv_args')
            assert t['size']==566*24 and n['size']==580*24 and t['value']==n['value'];cut=t['value']+t['size']
            oldops=OpsElf(oldpath).ioctl_records();newops=OpsElf(newpath).ioctl_records()
            assert len(oldops)==566 and len(newops)==580
            assert newops[:566]==oldops,'original entries bytecontract'
            expected=[(246,18433,0,'tx_maxmpdu'),(246,0,18433,'get_tx_maxmpdu'),(450,0,18433,'get_min_cac'),(496,0,18433,'get_sretry_lmt'),(497,0,18433,'get_lretry_lmt'),(331,0,18433,'get_cca_fixed'),(275,0,18433,'get_auto_cca_en'),(451,0,18433,'get_dev_mode'),(465,18433,0,'ignr_icac_sel'),(495,0,18433,'get_ft_over_ds'),(460,18433,0,'set_max_bw'),(460,0,18433,'get_max_bw'),(483,18433,0,'bbdf_war_en'),(483,0,18433,'get_bbdfwar_en')]
            fields=lambda row:(row['cmd'],row['set_args'],row['get_args'],row['name'])
            assert list(map(fields,newops[566:]))==expected,'exact14appended OEM contracts'
            assert x==y[:cut]+y[cut+336:],'rodata outside14tableappend'
        elif component=='wlan' and sec=='.data':
            t=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def');p=t['value']+8;y=bytearray(y)
            assert struct.unpack_from('<H',x,p)[0]==566 and struct.unpack_from('<H',y,p)[0]==580
            struct.pack_into('<H',y,p,566);assert x==bytes(y),'dataoutsidetransportcount'
        elif a['type']==8:assert (a['size'],a['align'],a['flags'])==(b['size'],b['align'],b['flags']),'BSS'
        else:assert x==y,'unrelated allocated data '+sec
        data.append(sec)
    return {'status':'PASS_COMPLETE_MODULE_BOUNDED_FOURTEEN_DELTA','changed_get_set':modified,'other_exact_changes':extras,'all_executable_sections':executable,
            'section_contract':section_contract,
            'generated_symbol_renames':generated_symbol_renames,
            'symbols_checked':len(old.syms),'baseline_relocations':len(old.relas),'candidate_relocations':len(new.relas),'relocations_outside_changed_bodies_checked':sum(ar.values()),'allocated_data_sections_checked':data}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    qualification_pins={}
    proof=read_pinned_json(a.build/'result.json',qualification_pins);assert proof['status']=='PASS_ALL_UNITS_COMPLETE_FOURTEEN_PAIR_PENDING_DELTA_QUALIFICATION'
    result={'status':'NO_GO_FOURTEEN_DELTA','hardware_accessed':False,'firmware_eligible':False,'physical_gates':'UNRUN','remaining_original_table_gaps':30,'functional_ops_added':12,'faithful_unsupported':2,'nac_prototype_included':False}
    try:
        pins=read_pinned_json(a.build/'input-pins.json',qualification_pins)
        for path,digest in pins.items():assert sha(path)==digest,'buildpin drift '+path
        fixture=Path(proof['candidate']).parent/'bbdf-recovery-fixture-20261022T144600Z-r1/result.json'
        fp=read_pinned_json(fixture,qualification_pins);assert fp['status']=='PASS_OFFLINE_BBDF_PREFIX_ABI_ARC_UNITS_AND_FIXTURE'
        assert fp['lowbool_cases']==131072 and fp['existing_private_prefix_unchanged']
        candidate=Path(proof['candidate']);candidate_proof=read_pinned_json(candidate/'result.json',qualification_pins)
        source_hashes={'qdrv_source_sha256':candidate/'source/qdrv/qdrv_wlan.c','qdrv_header_sha256':candidate/'source/qdrv/qdrv_wlan.h','wlan_source_sha256':candidate/'ieee80211_wireless.c'}
        for field,path in source_hashes.items():
            digest=sha(path);assert digest==candidate_proof[field],'candidate modified source identity '+field
            qualification_pins[str(path)]=digest
        for path in (Path(__file__),Path(__file__).parent/'qualify_f370_qdrv_module.py',Path(__file__).parent/'recover_hgw5g_driver_ops.py'):
            qualification_pins[str(path)]=sha(path)
        for row in proof['modules']:assert sha(row['path'])==row['sha256'] and Path(row['path']).stat().st_size==row['bytes'],'module identity'
        report={}
        for c,base in (('qdrv',Path(proof['qdrv_baseline_build'])/'baseline/qdrv.ko'),('wlan',Path(proof['wlan_baseline_build'])/'a/wlan.ko')):
            assert sha(a.build/'a'/c/(c+'.ko'))==sha(a.build/'b'/c/(c+'.ko'))
            report[c]=audit(base,a.build/'a'/c/(c+'.ko'),c)
        (a.output/'complete-module-audit.json').write_text(json.dumps(report,indent=2)+'\n')
        for path,digest in qualification_pins.items():assert sha(path)==digest,'qualification input changed '+path
        (a.output/'qualification-input-pins.json').write_text(json.dumps(qualification_pins,indent=2)+'\n')
        result.update(status='PASS_OFFLINE_COMPLETE_FOURTEEN_ENTRY_PAIR',modules=proof['modules'],reproducible=True,
                      input_pins_verified=len(pins),private_prefix_abi_fixture_sha256=sha(fixture),bbdf_bool_fixture_cases=131072,
                      limits='14records=12functional+2faithfulunsupported; exact privateprefix/fixtures separate. MuC firmware behavior, TQE arbitration and physical gates remainUNRUN.')
    except Exception as exc:result['error']=str(exc)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(result['status']!='PASS_OFFLINE_COMPLETE_FOURTEEN_ENTRY_PAIR')


if __name__=='__main__':raise SystemExit(main())
