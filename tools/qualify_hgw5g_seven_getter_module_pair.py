"""Whole-module canonical delta audit for the exact seven-entry source pair.

All unchanged executable bytes and relocations are compared by original function
range; changed getter bodies are explicitly inventoried rather than called
equivalent. Every allocated data byte, symbol and relocation outside those
bodies must match after declared path/table/count/diagnostic-line normalization.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
from functools import lru_cache

from qualify_f370_qdrv_module import Elf, normalized_path
from recover_hgw5g_driver_ops import Elf as OpsElf


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def functions(elf):
    return {(s['name'],elf.symsection(s)):s for s in elf.syms if s['type']==2 and s['size']}


def range_owner(elf,section,value,types=(1,2)):
    found=[s for s in elf.syms if s['type'] in types and elf.symsection(s)==section and s['size'] and s['value']<=value<s['value']+s['size']]
    return min(found,key=lambda s:(s['size'],s['name'])) if found else None


def line_delta(before,after,expected):
    """Accept only exact ARC32ME line immediate deltas in unchanged diagnostics."""
    assert len(before)==len(after)
    changes=[]
    normalized=bytearray(after)
    for i in range(4,len(before)-3,2):
        if before[i-4:i]==after[i-4:i] and before[i-4:i] in (bytes.fromhex('0a22800f'),bytes.fromhex('0a21800f')):
            high,low=struct.unpack_from('<HH',before,i)
            nh,nl=struct.unpack_from('<HH',after,i)
            old=(high<<16)|low;new=(nh<<16)|nl
            if new!=old:
                assert new-old==expected,(i,old,new,expected)
                normalized[i:i+4]=before[i:i+4]
                changes.append({'offset':i-4,'instruction':'mov r2/r1, diagnostic source line','old_line':old,'new_line':new})
    # One baseline assertion uses ARC's compact four-byte MOV immediate form.
    # Require exact observed instruction pairs, not arbitrary bit-field masking.
    if expected==6 and before[74:78]==bytes.fromhex('8a229807') and after[74:78]==bytes.fromhex('8a221809'):
        normalized[74:78]=before[74:78]
        changes.append({'offset':74,'instruction':'mov r2, compact diagnostic source line','old_line':1566,'new_line':1572})
    assert bytes(normalized)==before,'non-diagnostic instruction delta'
    return changes


def audit(old_path,new_path,component):
    old,new=Elf(old_path),Elf(new_path)
    getter='qdrv_wlan_80211_getparam' if component=='qdrv' else 'ieee80211_ioctl_getparam'
    allowed_diagnostics={'qdrv_wlan_auth_state_change':9,'qdrv_wlan_exit':9} if component=='qdrv' else {'ieee80211_delete_wlanunit':38,'ieee80211_ioctl_giwfreq':6,'ieee80211_param_from_qdrv':6,'ieee80211_ioctl_setparam':6}
    errors=[];diagnostics=[];changed=[]
    of,nf=functions(old),functions(new)
    assert set(of)==set(nf),'function membership'
    for key,o in of.items():
        n=nf[key];section=key[1]
        a=old.byname[section]['data'][o['value']:o['value']+o['size']]
        b=new.byname[section]['data'][n['value']:n['value']+n['size']]
        if key[0]==getter:
            changed.append({'name':getter,'baseline_bytes':o['size'],'candidate_bytes':n['size'],'baseline_sha256':hashlib.sha256(a).hexdigest(),'candidate_sha256':hashlib.sha256(b).hexdigest(),
                            'baseline_relocations':sum(r['section']==section and o['value']<=r['offset']<o['value']+o['size'] for r in old.relas),'candidate_relocations':sum(r['section']==section and n['value']<=r['offset']<n['value']+n['size'] for r in new.relas),
                            'scope':'INTENTIONALLY_CHANGED_GETTER_BODY_NOT_EQUIVALENT; actual-source fixture and ARC field witness are separate evidence'})
        elif a!=b:
            assert key[0] in allowed_diagnostics,'unexpected changed function '+key[0]
            diagnostics.append({'function':key[0],'changes':line_delta(a,b,allowed_diagnostics[key[0]])})
    # Account for ALL executable bytes, including unsymbolized alignment and
    # GCC-generated code holes: remove only the changed getter's size increase
    # and its intentionally changed body, restoring exact diagnostic immediates.
    executable_sections=[]
    for name,section in old.byname.items():
        if not section['flags']&4:
            continue
        candidate_section=new.byname[name]
        x=bytearray(section['data']);y=bytearray(candidate_section['data'])
        for diagnostic in diagnostics:
            key=(diagnostic['function'],name)
            if key not in of:
                continue
            o,n=of[key],nf[key]
            y[n['value']:n['value']+n['size']]=x[o['value']:o['value']+o['size']]
        if (getter,name) in of:
            o,n=of[(getter,name)],nf[(getter,name)]
            assert o['value']==n['value'],'getter insertion start'
            y[n['value']:n['value']+n['size']]=x[o['value']:o['value']+o['size']]
        assert x==y,'executable bytes outside declared getter/diagnostics '+name
        executable_sections.append({'section':name,'baseline_bytes':len(x),'candidate_bytes':section['size']+(nf[(getter,name)]['size']-of[(getter,name)]['size'] if (getter,name) in of else 0),'all_bytes_outside_declared_delta_match':True})
    # Function symbols and data object ranges provide canonical target addresses
    # despite insertion inside one getter moving later code globally.
    @lru_cache(maxsize=None)
    def address(elf,section,value):
        if section=='.rodata.str1.4':
            text=elf.cstring(section,value)
            if component=='qdrv':
                text=text.replace('/named-cca-getters-candidate-20261022T133300Z-r2/source/qdrv','/f364-qdrv/qdrv')
                text=text.replace('/outputs/rea/named-cca-getters-candidate-20261022T133300Z-r2/source/qdrv','/f364-qdrv/qdrv')
            return ('string',normalized_path(text))
        # Unsymbolized executable bytes after the single changed getter retain
        # the exact piecewise mapping proven by the whole-section comparison.
        if elf is new and section==new.symsection(nf[(getter,'.text')]) and value>=nf[(getter,'.text')]['value']+nf[(getter,'.text')]['size']:
            canonical_value=value-(nf[(getter,'.text')]['size']-of[(getter,'.text')]['size'])
        else:
            canonical_value=value
        owner=range_owner(elf,section,value)
        if owner:
            relative=value-owner['value']
            return ('object',owner['name'],section,relative)
        # Offsets into unsymbolized pools after the inserted WLAN args table.
        if component=='wlan' and section=='.rodata':
            table=next(s for s in elf.syms if s['name']=='ieee80211_priv_args')
            if elf is new and value>=table['value']+table['size']:
                value-=168
        return ('section',section,canonical_value if section=='.text' else value)
    def relocation(elf,r):
        section=r['section'];owner=range_owner(elf,section,r['offset'])
        if owner and owner['name']==getter:
            return None
        site=address(elf,section,r['offset'])
        s=elf.syms[r['symbol']];target_section=elf.symsection(s)
        if s['type']==3:
            target=address(elf,target_section,s['value']+r['addend'])
        elif target_section=='.rodata.str1.4':
            target=address(elf,target_section,s['value']+r['addend'])
        else:
            target=(s['name'],target_section,s['type'],s['bind'],r['addend'])
        return (site,r['type'],target)
    ar=Counter(x for r in old.relas if (x:=relocation(old,r)) is not None)
    br=Counter(x for r in new.relas if (x:=relocation(new,r)) is not None)
    delta=list((ar-br).elements())+list((br-ar).elements())
    assert not delta,'relocations outside getters changed '+str(delta[:8])
    # Compare data and metadata after only the exact private-argument insertion
    # and count. Build-id and reloc/symbol tables have independent semantic gates.
    section_rows=[]
    for name in set(old.byname)|set(new.byname):
        a=old.byname.get(name);b=new.byname.get(name)
        assert a is not None and b is not None,'section membership '+name
        if a['flags']&4 or a['type']==4 or name in ('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):
            continue
        x,y=a['data'],b['data']
        if name=='.rodata.str1.4':
            strings=lambda e:Counter(normalized_path(x.decode('latin1')) for x in e.byname[name]['data'].split(b'\0') if x)
            assert strings(old)==strings(new),'string symbols differ'
        elif name=='.rodata' and component=='wlan':
            o=next(s for s in old.syms if s['name']=='ieee80211_priv_args');n=next(s for s in new.syms if s['name']=='ieee80211_priv_args')
            assert o['value']==n['value'] and o['size']==566*24 and n['size']==573*24
            cut=o['value']+o['size']
            expected=[(246,18433,0,'tx_maxmpdu'),(246,0,18433,'get_tx_maxmpdu'),(450,0,18433,'get_min_cac'),(496,0,18433,'get_sretry_lmt'),(497,0,18433,'get_lretry_lmt'),(331,0,18433,'get_cca_fixed'),(275,0,18433,'get_auto_cca_en')]
            payload=b''.join(struct.pack('<IHH',cmd,st,gt)+n.encode().ljust(16,b'\0') for cmd,st,gt,n in expected)
            assert y[cut:cut+168]==payload
            y=y[:cut]+y[cut+168:]
            assert x==y,'allocated rodata outside7aliases'
        elif name=='.data' and component=='wlan':
            h=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def')
            pos=h['value']+8;y=bytearray(y)
            assert struct.unpack_from('<H',x,pos)[0]==566 and struct.unpack_from('<H',y,pos)[0]==573
            struct.pack_into('<H',y,pos,566)
            assert x==bytes(y),'data outside privateargs count'
        elif a['type']==8:
            assert (a['size'],a['align'],a['flags'])==(b['size'],b['align'],b['flags']),'BSS'
        else:
            assert x==y,'allocated/data section '+name
        section_rows.append({'section':name,'compared':True})
    # Every symbol's semantic attributes; positions normalize via owners.
    def symbol(elf,s):
        sec=elf.symsection(s)
        size=s['size']
        if s['name']==getter:
            size=of[(getter,sec)]['size']
        if component=='wlan' and s['name']=='ieee80211_priv_args':
            size=566*24
        value=address(elf,sec,s['value']) if s['type']!=3 else ('section_start',sec)
        return (s['name'],sec,s['type'],s['bind'],s['other'],size,value)
    os=Counter(symbol(old,s) for s in old.syms);ns=Counter(symbol(new,s) for s in new.syms)
    symdelta=list((os-ns).elements())+list((ns-os).elements())
    assert not symdelta,'symbol semantic delta '+str(symdelta[:8])
    return {'status':'PASS_WHOLE_MODULE_DECLARED_GETTER_DELTA','functions_total':len(of),'unchanged_function_bodies':len(of)-1-len(diagnostics),
            'changed_getter':changed,'diagnostic_only_functions':diagnostics,'baseline_relocations_total':len(old.relas),'candidate_relocations_total':len(new.relas),
            'relocations_outside_changed_getter_qualified':sum(ar.values()),'symbols_total':len(old.syms),'data_sections':section_rows,'all_executable_bytes':executable_sections,
            'limits':'Changed getter CFG/semantic correctness is supported separately by actual source fixture; no firmware timing or hardware claim.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
    proof=json.loads((a.build/'result.json').read_text());assert proof['status']=='PASS_TWO_COMPLETE_MODULES_PENDING_DELTA_QUALIFICATION'
    qbase=Path(proof['qdrv_baseline_build'])/'baseline/qdrv.ko'
    wbase=Path(proof['wlan_baseline_build'])/'a/wlan.ko'
    result={'schema':'openmitrastar.seven-getter-module-pair-qualification/v1','status':'NO_GO_DELTA_QUALIFICATION','hardware_accessed':False,'firmware_eligible':False,'physical_gates':'UNRUN','remaining_oem_table_gaps':37}
    try:
        # Bind every module and source/build input to the completed build receipt.
        pins=json.loads((a.build/'input-pins.json').read_text())
        for path,digest in pins.items():
            assert sha(path)==digest,'build input drift '+path
        for row in proof['modules']:
            assert sha(row['path'])==row['sha256'] and Path(row['path']).stat().st_size==row['bytes'],'module receipt identity'
        fixture=Path(proof['candidate']).parent/'named-cca-getters-fixture-20261022T133600Z-r3/result.json'
        fixture_proof=json.loads(fixture.read_text())
        assert fixture_proof['status']=='PASS_OFFLINE_ARC_ABI_AND_ACTUAL_GETTER_FIXTURE'
        assert fixture_proof['fixture_checks']==196609 and fixture_proof['wlan_high16_forward_checks']==131072
        evidence={}
        for component,baseline in (('qdrv',qbase),('wlan',wbase)):
            candidate=a.build/'a'/component/(component+'.ko')
            assert sha(candidate)==sha(a.build/'b'/component/(component+'.ko'))
            evidence[component]=audit(baseline,candidate,component)
        (a.output/'whole-module-audit.json').write_text(json.dumps(evidence,indent=2)+'\n')
        result.update(status='PASS_OFFLINE_COMPLETE_SEVEN_ENTRY_PAIR',modules=proof['modules'],reproducible=True,total_recovered_entries=7,
                      input_pins_verified=len(pins),actual_getter_and_forward_fixture_checks=327681,
                      arc_field_witness=fixture_proof['arc_port_fields'],fixture_evidence_sha256=sha(fixture),
                      limits='Seven-entry module pair complete; changed getters checked by separate actual source fixture/ARC ABI evidence; remaining37OEM entries unresolved, queue arbitration and physical acceptance unproved.')
    except Exception as exc:
        result['error']=str(exc)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(result['status']!='PASS_OFFLINE_COMPLETE_SEVEN_ENTRY_PAIR')


if __name__=='__main__':
    raise SystemExit(main())
