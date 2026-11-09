"""Global residual byte/data/RELA qualification for immutable bounded pair.

Changed source bodies/new provider functions remain explicitly bounded by exact
compiled hashes and actual-source fixtures; they are not claimed instruction
equivalent. Every other executable byte, symbol and relocation is compared.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from qualify_f370_qdrv_module import Elf, normalized_path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-source-r2'
FIXTURES=[ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-lifecycle-fixture-r2/result.json',ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-four-writer-fixture-r4/result.json',ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-queue-fixture-r3/result.json']
CHANGED={'switch_tqe':{'tqe_push_mcast','tqe_rx_napi_handler','tqe_module_exit','cleanup_module','tqe_tx','topaz_tqe_xmit','topaz_tqe_congest_queue_process','tqe_rx_multicast'},'topaz_congest_queue':{'topaz_congest_queue_clear','topaz_congest_queue_exit','topaz_congest_queue_xmit'}}
EXTRA={'topaz_congest_dequeue','topaz_congest_enqueue','topaz_congest_release_queue','reg_congest_queue_stats'}
NEW={'switch_tqe':{'omtqe_lhost_reserve','omtqe_lhost_submit','omtqe_lhost_submit_reserved'},'topaz_congest_queue':{'omcgq_bank_acquire','omcgq_bank_cancel','omcgq_bank_quarantine','omcgq_bank_quarantined','omcgq_bank_retain','omcgq_bank_retained','omcgq_bank_token_valid','omcgq_record_held','omcgq_token_matches'}}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def funcs(e):
    rows=[s for s in e.syms if s['type']==2 and s['size']]
    assert len(rows)==len({s['name']for s in rows}),'duplicate function name'
    return {s['name']:s for s in rows}
def code(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]

def normalize_extra(old,new,name):
    result=bytearray(new)
    points={'topaz_congest_dequeue':{74:(128,131),82:(1,4)},'topaz_congest_enqueue':{62:(128,131),70:(1,4),76:(128,131),82:(1,4)},'reg_congest_queue_stats':{8:(0,3),10:(33,36)}}
    if name in points:
        assert len(old)==len(new)
        for i,(a,b)in points[name].items():assert old[i]==a and new[i]==b;result[i]=a
        assert bytes(result)==old,'othercode '+name
        return bytes(result),[(p,'BSS anchor field delta +12')for p in points[name]]
    assert name=='topaz_congest_release_queue' and len(new)==len(old)+2
    assert old[26:28]==bytes.fromhex('15eb') and new[26:28]==bytes.fromhex('16eb')
    result[26:28]=old[26:28]
    assert old[38:40]==bytes.fromhex('dcda') and new[38:42]==bytes.fromhex('8a22450d')
    result[38:42]=old[38:40]
    assert bytes(result)==old,'non diagnosticreleasechange'
    return bytes(result),[(26,'branch +2 due diagnostic width'),(38,'assert line220 to373')]

def audit(oldpath,newpath,component):
    old,new=Elf(oldpath),Elf(newpath)
    assert set(old.byname)==set(new.byname),'sectionmembership'
    for name,s in old.byname.items():
        for attr in('type','flags','align','entsize'):assert s[attr]==new.byname[name][attr],(name,attr)
    # All named symbols are unique in this immutable pair. Do not silently
    # collapse duplicate locals or treat relocated data as symbol metadata proof.
    osy={s['name']:s for s in old.syms if s['name']};nsy={s['name']:s for s in new.syms if s['name']}
    assert len(osy)==sum(bool(s['name'])for s in old.syms)and len(nsy)==sum(bool(s['name'])for s in new.syms),'duplicate named symbol'
    renames={'__UNIQUE_ID_license327':'__UNIQUE_ID_license329','__UNIQUE_ID_author326':'__UNIQUE_ID_author328','__UNIQUE_ID_description325':'__UNIQUE_ID_description327'}if component=='topaz_congest_queue'else{}
    for name,s in osy.items():
        name_new=renames.get(name,name);assert name_new in nsy,'symbol removed '+name
        t=nsy[name_new]
        assert(s['type'],s['bind'],s['other'],old.symsection(s))==(t['type'],t['bind'],t['other'],new.symsection(t)),'symbolattributes '+name
        if name not in CHANGED[component]and name!='topaz_congest_release_queue':assert s['size']==t['size'],'symbolsize '+name
    of,nf=funcs(old),funcs(new)
    assert set(nf)-set(of)==NEW[component]
    assert set(of)<=set(nf)
    changed=[];extras=[];same=[]
    for name,s in of.items():
        t=nf[name];a,b=code(old,s),code(new,t)
        if name in CHANGED[component]:changed.append({'name':name,'old_value':s['value'],'new_value':t['value'],'old_bytes':s['size'],'new_bytes':t['size'],'section':old.symsection(s),'old_sha256':digest(a),'new_sha256':digest(b)})
        elif a!=b:
            assert component=='topaz_congest_queue'and name in EXTRA,name
            _,normalization=normalize_extra(a,b,name);extras.append({'name':name,'normalization':normalization})
        else:same.append(name)
    # Remove exact function ranges rather than masking all executable sections.
    # Unnamed padding is retained; compiler emitted changed layouts are checked
    # against exact residual lengths/bytes below.
    residual=[]
    for sec,s in old.byname.items():
        if not s['flags']&4:continue
        a=bytearray(s['data']);b=bytearray(new.byname[sec]['data'])
        # Ignore function-owned content only. Outside all functions must remain
        # padding; exact bytes may differ when 2-byte ARC alignment is shifted.
        oldranges=sorted({(x['value'],x['size'])for x in of.values()if old.symsection(x)==sec},reverse=True)
        newranges=sorted({(x['value'],x['size'])for x in nf.values()if new.symsection(x)==sec},reverse=True)
        for p,n in oldranges:del a[p:p+n]
        for p,n in newranges:del b[p:p+n]
        expected_padding={'switch_tqe':{'.text':(56,52),'.text.unlikely':(2,2),'.init.text':(2,2),'.exit.text':(2,2)},'topaz_congest_queue':{'.text':(32,34),'.sram.text':(2,4),'.init.text':(0,0),'.exit.text':(2,2)}}
        before_count,after_count=expected_padding[component][sec]
        assert bytes(a)==bytes.fromhex('e078')*(before_count//2) and bytes(b)==bytes.fromhex('e078')*(after_count//2),'exact ARC NOP padding '+sec
        residual.append({'section':sec,'old_unowned_bytes':len(a),'new_unowned_bytes':len(b),'old_padding_sha256':digest(a),'new_padding_sha256':digest(b),'padding_exact_declared_nop_count':True})
    def canonical_point(e,sec,value):
        if sec in('.rodata.str1.4','__ksymtab_strings'):return('cstring',normalized_path(e.cstring(sec,value)))
        choices=[x for x in e.syms if e.symsection(x)==sec and x['type']in(1,2)and x['size']and x['value']<=value<x['value']+x['size']]
        if choices:
            names=sorted((x['size'],x['name'],x['value'])for x in choices);_,name,start=names[0]
            off=value-start
            if component=='topaz_congest_queue'and name=='topaz_congest_release_queue'and e is new and off>=42:off-=2
            return('object',sec,name,off)
        return('section',sec,value)
    for name,s in osy.items():
        t=nsy[renames.get(name,name)]
        if name in CHANGED[component]:continue
        if name in renames:
            assert old.symsection(s)==new.symsection(t)=='.modinfo'
            assert old.byname['.modinfo']['data'][s['value']:s['value']+s['size']]==new.byname['.modinfo']['data'][t['value']:t['value']+t['size']],'metadata symbol bytes '+name
            continue
        assert canonical_point(old,old.symsection(s),s['value'])==canonical_point(new,new.symsection(t),t['value']),'symbolvalue '+name
    extra_symbols=set(nsy)-{renames.get(name,name)for name in osy}
    if component=='switch_tqe':
        expected_extra=NEW[component]|{'omcgq_bank_token_valid','omcgq_bank_retain','omcgq_bank_acquire','omcgq_bank_cancel','omcgq_bank_quarantine','omcgq_bank_retained','omcgq_bank_quarantined'}
    else:
        exported={x for x in NEW[component]if x.startswith('omcgq_bank_')}
        expected_extra=NEW[component]|{'omcgq_held','omcgq_quarantined','omcgq_retained','omcgq_reserved','omcgq_generation','omcgq_owner','omcgq_unrecorded','omcgq_held_count','try_module_get','memcpy','module_put','memcmp'}
        expected_extra|={prefix+x for prefix in('__kstrtab_','__kstrtabns_','__ksymtab_')for x in exported}
    assert extra_symbols==expected_extra,'new symbol membership '+str(extra_symbols^expected_extra)
    if component=='topaz_congest_queue':
        bss_expected={'omcgq_quarantined':(0,1),'omcgq_retained':(1,1),'omcgq_reserved':(2,1),'omcgq_generation':(4,4),'omcgq_owner':(8,4),'pktlog_update_cgq_stats':(12,8),'g_congest_queue_ptr':(20,4),'omcgq_unrecorded':(24,4),'omcgq_held_count':(28,4),'omcgq_held':(32,8192)}
        for name,(value,size)in bss_expected.items():
            t=nsy[name];assert(new.symsection(t),t['type'],t['bind'],t['other'],t['value'],t['size'])==('.bss',1,1 if name in('g_congest_queue_ptr','pktlog_update_cgq_stats')else 0,0,value,size),'exact provider BSS layout '+name
        added={x for x in NEW[component]if x.startswith('omcgq_bank_')}
        for name in added:
            record=nsy['__ksymtab_'+name]
            assert(new.symsection(record),record['type'],record['size'])==('__ksymtab',1,12),'kernel exportrecord '+name
            records=[r for r in new.relas if r['section']=='__ksymtab'and record['value']<=r['offset']<record['value']+12]
            assert sorted(r['offset']-record['value']for r in records)==[0,4,8],'export relocation count '+name
            expected_targets={0:name,4:name,8:''}
            for r in records:
                s=new.syms[r['symbol']];sec=new.symsection(s);offset=r['offset']-record['value']
                if offset==0:assert s['name']==name and s['type']==2
                else:assert new.cstring(sec,s['value']+r['addend'])==expected_targets[offset]
    ignored=CHANGED[component]|NEW[component]
    def site(e,r):
        owned=[s for s in e.syms if s['type']==2 and e.symsection(s)==r['section']and s['value']<=r['offset']<s['value']+s['size']]
        return owned
    def reloc(e,r):
        owned=site(e,r)
        if any(s['name']in ignored for s in owned):return None
        if component=='topaz_congest_queue'and r['section']=='__ksymtab':
            targets=[s for s in e.syms if s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+s['size']]
            if targets and targets[0]['name'][10:]in NEW[component]:return None
        s=e.syms[r['symbol']];sec=e.symsection(s)
        if component=='topaz_congest_queue'and e is new and s['type']==3 and sec=='.bss'and owned and owned[0]['name']in('reg_congest_queue_stats','topaz_congest_dequeue','topaz_congest_enqueue')and r['addend']==0:
            # Compiler section-anchor relocation points at sectionbase; checked
            # instructions independently shift both original fields exactly12.
            return(canonical_point(e,r['section'],r['offset']),r['type'],('object','.bss','pktlog_update_cgq_stats',0))
        target=canonical_point(e,sec,s['value']+r['addend'])if s['type']==3 or sec=='.rodata.str1.4'else(s['name'],sec,s['type'],s['bind'],r['addend'])
        return(canonical_point(e,r['section'],r['offset']),r['type'],target)
    a=Counter(v for r in old.relas if(v:=reloc(old,r))is not None);b=Counter(v for r in new.relas if(v:=reloc(new,r))is not None)
    differences=list((a-b).elements())+list((b-a).elements());assert not differences,'residualrelocs '+str(differences[:6])
    data=[]
    for name,s in old.byname.items():
        t=new.byname[name]
        if s['flags']&4 or s['type']==4 or name in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
        if name=='.bss':
            if component=='switch_tqe':assert(s['size'],s['align'])==(t['size'],t['align'])
            else:assert s['size']==12 and t['size']==8224
        elif name=='.rodata.str1.4':
            count=lambda z:Counter(x for x in z.split(b'\0')if x)
            removed=count(s['data'])-count(t['data']);added=count(t['data'])-count(s['data'])
            assert not added and(removed==Counter({b'stuck in topaz_tqe_wait()\n':1})if component=='switch_tqe'else not removed)
        elif component=='topaz_congest_queue'and name in('__ksymtab','__ksymtab_strings'):
            oldexports={s['name'][10:]for s in old.syms if s['name'].startswith('__ksymtab_')};newexports={s['name'][10:]for s in new.syms if s['name'].startswith('__ksymtab_')}
            assert oldexports<=newexports and newexports-oldexports=={x for x in NEW[component]if x.startswith('omcgq_bank_')}
        else:assert s['data']==t['data'],'data '+name
        data.append(name)
    return{'status':'PASS_GLOBAL_RESIDUAL_BOUNDED_PAIR_SCOPE','changed_source_bodies':changed,'new_source_functions':sorted(NEW[component]),'exact_other_changes':extras,'unchanged_function_bodies':same,'named_symbols_checked':len(osy),'new_symbols_exact':sorted(extra_symbols),'residual_relocations_checked':sum(a.values()),'data_sections_checked':data,'unowned_padding':residual,'limits':'Changed/new function bodies pinned and source-fixture-qualified, not instruction equivalent.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
    result={'status':'NO_GO_COMPLETE_PROVIDER_DELTA','hardware_accessed':False,'firmware_eligible':False,'physical_gates':'UNRUN'}
    try:
        ownpaths={Path(__file__),ROOT/'tools/qualify_f370_qdrv_module.py',ROOT/'tools/recover_hgw5g_driver_ops.py',a.build/'result.json',a.build/'input-pins.json',SOURCE/'result.json',SOURCE/'switch_tqe.c',SOURCE/'topaz_congest_queue.c',SOURCE/'openmitrastar_tqe_bounded_ownership.h'}
        ownpaths.update(FIXTURES)
        for f in FIXTURES:ownpaths.update(p for p in f.parent.iterdir()if p.is_file())
        qualification_pins={str(p):sha(p)for p in ownpaths}
        (a.output/'qualification-input-pins.json').write_text(json.dumps(qualification_pins,indent=2)+'\n')
        proof=json.loads((a.build/'result.json').read_text());assert proof['status']=='PASS_OFFLINE_COMPLETE_BOUNDED_PROVIDER_PAIR_PENDING_FIXTURE_AND_DELTA'
        pins=json.loads((a.build/'input-pins.json').read_text())
        for path,h in pins.items():
            path=Path(path.replace('/mnt/c/','C:/').replace('/mnt/d/','D:/'))if __import__('os').name=='nt'else Path(path)
            assert sha(path)==h,str(path)
        for f in FIXTURES:assert json.loads(f.read_text())['status'].startswith('PASS_')
        report={}
        for c in('switch_tqe','topaz_congest_queue'):
            old=a.build/'baseline'/c/(c+'.ko');new=a.build/'a'/c/(c+'.ko');assert sha(new)==sha(a.build/'b'/c/(c+'.ko'))
            rows=[row for row in proof['modules']if row['name']==c]
            assert len(rows)==2 and all(sha(Path(row['path']))==row['sha256']and Path(row['path']).stat().st_size==row['bytes']for row in rows),'bound module artifact '+c
            report[c]=audit(old,new,c)
        for path,h in qualification_pins.items():assert sha(path)==h,'qualification pin drift '+path
        (a.output/'complete-scope-audit.json').write_text(json.dumps(report,indent=2)+'\n')
        result.update(status='PASS_OFFLINE_BOUNDED_PROVIDER_PAIR_GLOBAL_SCOPE_PENDING_RELEASE',reproducible=True,fixtures_cases=171,modules=proof['modules'],pins_verified=len(pins),limits='No retainedpayloadrelease/recovery, no ledger saturation completeness, no foreignbankarbitration, no physical acceptance.')
    except Exception as e:result['error']=str(e)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
