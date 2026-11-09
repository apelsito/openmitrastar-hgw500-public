"""Build whole F374 module twice on exact byte-proven F352 ABI, offline only."""
import argparse
from datetime import datetime, timezone
import hashlib, json, shutil, sys, struct, re
from collections import Counter
from pathlib import Path
import build_hgw_ethernet_baseline_gate as base
import qualify_f370_qdrv_module as comparison

ROOT = base.ROOT
SOURCE = ROOT/'work/kernel-port/f374-ethernet-rx-quiesce'
BASELINE = ROOT/'outputs/rea/ethernet-baseline-20261022T133249267080Z'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v): p.write_text(json.dumps(v,indent=2)+'\n')

def canonical_target(e,r):
    target=e.syms[r['symbol']]; sec=e.symsection(target)
    if target['type']==3 and target['section']<len(e.sections):
        address=target['value']+r['addend']
        owners=[v for v in e.syms if v['section']==target['section'] and v['type'] in (1,2) and v['size'] and v['value']<=address<v['value']+v['size']]
        if owners:
            owner=min(owners,key=lambda v:(v['size'],v['name']))
            return ('symbol-offset',owner['name'],sec,address-owner['value'],owner['type'],owner['bind'],owner['other'])
        if sec=='.rodata.str1.4':return ('string',e.cstring(sec,address))
        return ('section-offset',sec,address)
    return ('symbol',target['name'],sec,r['addend'],target['type'],target['bind'],target['other'])

def data_deltas(left,right):
    """Audit every allocated non-code byte, relocation and section attribute."""
    rows=[]
    assert set(left.byname)==set(right.byname),'section membership changed'
    for name in sorted(left.byname):
        a,b=left.byname[name],right.byname[name]
        assert (a['type'],a['flags'],a['align'],a['entsize'])==(b['type'],b['flags'],b['align'],b['entsize']),('section attributes changed',name)
        if not a['flags']&2 or a['flags']&4:continue
        if name=='.note.gnu.build-id':
            rows.append({'name':name,'comparison':'EXPECTED_LINK_HASH_METADATA_DELTA','pass':a['size']==b['size']});continue
        if name=='.rodata.str1.4':
            strings=lambda s:Counter(x.decode('latin1') for x in s['data'].split(b'\0') if x)
            before,after=strings(a),strings(b)
            added=list((after-before).elements());removed=list((before-after).elements())
            # One telemetry line is inserted into the single sysfs format.
            expected_removed=[x for x in before if 'schema=1\nirq=' in x]
            expected_added=[x.replace('rx_restart_throttled=%u\n','rx_restart_throttled=%u\nrx_quiesce_timeouts=%u\n') for x in expected_removed]
            good=Counter(removed)==Counter(expected_removed) and Counter(added)==Counter(expected_added)
            rows.append({'name':name,'comparison':'EXACT_STRING_MULTISET_EXCEPT_DECLARED_TIMEOUT_FIELD','pass':good,'added':added,'removed':removed});assert good,('unexpected string delta',name);continue
        assert a['size']==b['size'],('allocated data size changed',name)
        def content(e,s):
            data=bytearray(s['data']);rels=[]
            for r in e.relas:
                if r['section']!=name:continue
                assert r['type'] in (4,27),('unexpected data relocation',r)
                assert 0<=r['offset']<=len(data)-4,('relocation outside data',r)
                data[r['offset']:r['offset']+4]=b'\0'*4
                rels.append((r['offset'],r['type'],canonical_target(e,r)))
            return bytes(data),rels
        x,y=content(left,a),content(right,b)
        good=x==y
        rows.append({'name':name,'comparison':'EVERY_BYTE_AND_CANONICAL_RELOCATION','pass':good,'bytes':a['size'],'relocations':len(x[1])})
        assert good,('unexpected allocated data delta',name)
    def objects(e):
        values=[]
        for s in e.syms:
            if s['type']!=1 or s['section']>=len(e.sections) or not e.sections[s['section']]['flags']&2:continue
            name=s['name'];sec=e.symsection(s)
            # __COUNTER__ names in immutable modinfo move when READ_ONCE is
            # added. Only these three exact roles may normalize numeric ids;
            # their payload bytes, offsets and sizes were already compared.
            if sec=='.modinfo' and re.fullmatch(r'__UNIQUE_ID_(license|description|author)\d+',name):name=re.sub(r'\d+$','<compiler-counter>',name)
            values.append((name,sec,s['value'],s['size'],s['type'],s['bind'],s['other']))
        return Counter(values)
    assert objects(left)==objects(right),'allocated object membership/layout changed'
    return rows

def function_deltas(left, right):
    """Compare every body using canonical per-body relocations and target names.

    Offsets shifted by changed functions are represented by target symbol name
    and intra-symbol offset. Bytes occupied by a relocation are compared through
    that relocation's semantics, not its pre-link layout-dependent encoding.
    """
    def functions(e):
        items=[s for s in e.syms if s['type']==2 and s['size']]
        found={(s['name'], e.symsection(s)):s for s in items}
        assert len(found)==len(items),'duplicate function name/section'
        return found
    def body(e,s):
        section=e.sections[s['section']]
        data=bytearray(section['data'][s['value']:s['value']+s['size']]); rel=[]
        for r in e.relas:
            if r['section']!=section['name'] or not s['value']<=r['offset']<s['value']+s['size']:continue
            target=e.syms[r['symbol']]; targetsection=e.symsection(target)
            offset=r['offset']-s['value']
            assert 0<=offset<=len(data)-4,('code relocation crosses function body',s['name'],r)
            assert not any(offset<previous[0]+4 and previous[0]<offset+4 for previous in rel),('overlapping code relocations',s['name'],r)
            if target['type']==3 and target['section']<len(e.sections):
                address=target['value']+r['addend']
                owners=[v for v in e.syms if v['section']==target['section'] and v['type'] in (1,2) and v['size'] and v['value']<=address<v['value']+v['size']]
                if owners:
                    owner=min(owners,key=lambda v:(v['size'],v['name'])); identity=(owner['name'],targetsection,address-owner['value'])
                elif targetsection=='.rodata.str1.4': identity=('string',e.cstring(targetsection,address))
                else: identity=(target['name'],targetsection,address)
            else: identity=(target['name'],targetsection,r['addend'])
            # ARC32/MIDDLE immediate relocations occupy 4 bytes. All relocation
            # types in these F352 function bodies must be covered explicitly.
            assert r['type'] in (4,27), ('unexpected relocation',r)
            data[offset:offset+4]=b'\0'*4
            rel.append((offset,r['type'],identity))
        return bytes(data),rel
    a,b=functions(left),functions(right); rows=[]
    for key in sorted(a.keys()|b.keys()):
        x,y=a.get(key),b.get(key)
        same=x is not None and y is not None and body(left,x)==body(right,y)
        rows.append({'name':key[0],'section':key[1],'unchanged':same,
                     'parent_bytes':x['size'] if x else None,'candidate_bytes':y['size'] if y else None})
    return rows

def code_gap_deltas(left,right):
    """Compare all executable bytes outside functions, anchored to neighbors.

    Alias symbols at one exact interval share ownership. Any other overlap,
    unknown executable section, or relocation outside a complete body fails.
    Gaps are byte compared even when they contain decoded NOP instructions.
    """
    def gaps(e):
        output={}
        for sec in e.sections:
            if not sec['flags']&4:continue
            intervals={}
            for sym in e.syms:
                if sym['section']!=sec['index'] or sym['type']!=2 or not sym['size']:continue
                assert 0<=sym['value'] and sym['value']+sym['size']<=sec['size'],('function outside section',sym)
                intervals.setdefault((sym['value'],sym['value']+sym['size']),[]).append(sym['name'])
            ordered=sorted(intervals)
            cursor=0;previous=()
            for start,end in ordered:
                assert start>=cursor,('overlapping function bodies',sec['name'],start,cursor)
                current=tuple(sorted(intervals[(start,end)]))
                gap=sec['data'][cursor:start]
                assert len(gap)==((-cursor)&3),('noncanonical executable alignment gap',sec['name'],cursor,start)
                assert gap in (b'',b'\xe0\x78'),('non-NOP bytes outside functions',sec['name'],cursor)
                output[(sec['name'],previous)]=gap
                cursor=end;previous=current
            trailer=sec['data'][cursor:]
            assert len(trailer)<=2 and trailer in (b'',b'\xe0\x78'),('unexplained executable section trailer',sec['name'],cursor)
            output[(sec['name'],previous)]=trailer
            for r in e.relas:
                if r['section']!=sec['name']:continue
                assert r['type'] in (4,27),('unsupported code relocation',r)
                owners=[i for i in ordered if i[0]<=r['offset'] and r['offset']+4<=i[1]]
                assert len(owners)==1,('code relocation lacks unique complete owner',r)
        return output
    a,b=gaps(left),gaps(right)
    assert set(a)==set(b),'code gap previous-owner membership changed'
    assert Counter((key[0],value) for key,value in a.items())==Counter((key[0],value) for key,value in b.items()),'executable padding multiset changed'
    rows=[]
    for key in sorted(a):
        good=a[key]==b[key]
        changed={'qtn_emac_stats','qtn_emac_open','qtn_emac_irq_poll_work','f352_create_port'}
        assert good or set(key[1])<=changed,('unchanged function padding changed',key)
        rows.append({'section':key[0],'previous_symbols':key[1],
            'parent_bytes':len(a[key]),'candidate_bytes':len(b[key]),'byte_exact':good,
            'comparison':'EXACT_BYTES' if good else 'DECLARED_CHANGED_BODY_ALIGNMENT_NOP; per-section exact multiset'})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path)
    p.add_argument('--candidate',type=Path,default=SOURCE);a=p.parse_args()
    source=a.candidate.resolve()
    out=a.output or ROOT/'outputs/rea'/('ethernet-f374-build-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True,exist_ok=False)
    result={'schema':'openmitrastar.f374-ethernet-module/v1','status':'NO_GO_OFFLINE_BUILD',
            'installed':False,'hardware_accessed':False,'firmware_created':False,'firmware_eligible':False,
            'install_status':'NO_GO_INSTALL','physical_gates':'UNRUN'}
    try:
        baseline=json.loads((BASELINE/'result.json').read_text())
        assert baseline['status']=='PASS_OFFLINE_COMPLETE_ETHERNET_BASELINE' and baseline['whole_file_exact']
        assert sha(BASELINE/'a'/f'{base.NAME}.ko')==base.EXPECTED
        manifest=json.loads((source/'manifest.json').read_text())
        config=(base.CONTEXT/'.config').read_text()
        assert '# CONFIG_SMP is not set' in config and 'CONFIG_PREEMPT_NONE=y' in config,'requires retained singlecore nonpreempt kernel'
        for name,h in manifest['baseline_pins'].items():assert sha(base.SOURCE/name)==h
        for name,h in manifest['source_pins'].items():assert sha(source/name)==h
        oldpins=json.loads((BASELINE/'input-pins.json').read_text())
        replacements=[]
        effectivepins={}
        for name,h in oldpins.items():
            path=Path(name)
            if not path.is_file() and path.parent==base.PARENT and path.name in (f'{base.NAME}.ko',f'{base.NAME}.o',f'{base.NAME}.mod.o'):
                replacement=BASELINE/'a'/path.name
                assert sha(replacement)==h,'baseline replacement hash differs'
                replacements.append({'missing_path':name,'exact_existing_path':str(replacement),'sha256':h})
                path=replacement
            assert sha(path)==h,'baseline pin drift '+str(path)
            effectivepins[str(path)]=h
        save(out/'exact-baseline-input-substitutions.json',replacements)
        pins={**effectivepins,**{str(x):sha(x) for x in source.iterdir() if x.is_file()},
              str(Path(__file__).resolve()):sha(__file__),str(BASELINE/'result.json'):sha(BASELINE/'result.json')}
        save(out/'input-pins.json',pins)
        parent=comparison.Elf(BASELINE/'a'/f'{base.NAME}.ko'); modules=[]
        for lane in ('a','b'):
            folder=out/lane;folder.mkdir()
            for name in (f'{base.NAME}.c','f352_contract.h','f352_pair.inc'):shutil.copyfile(source/name,folder/name)
            obj=folder/f'{base.NAME}.o'
            base.run(base.command(folder),base.CONTEXT,folder/'compile-driver')
            deps=base.actual_dependencies(folder/f'{base.NAME}.d')
            assert all(str(x) in pins or x.is_relative_to(folder) for x in deps),'unpinned header dependency'
            save(folder/'actual-header-pins.json',{str(x):sha(x) for x in deps})
            (folder/f'.{base.NAME}.o.cmd').write_text('source_'+str(obj)+' := '+str(folder/f'{base.NAME}.c')+'\n\ndeps_'+str(obj)+' := \\\n'+''.join('  '+str(x)+' \\\n' for x in sorted(deps))+'\n')
            (folder/f'{base.NAME}.mod').write_text(str(obj)+'\n')
            base.run([str(base.CONTEXT/'scripts/mod/modpost'),'-E','-e','-i',str(base.CONTEXT/'Module.symvers'),'-o',str(folder/'Module.symvers'),str(obj)],folder,folder/'modpost')
            base.run(base.command(folder,True),base.CONTEXT,folder/'compile-metadata')
            md=base.actual_dependencies(folder/f'{base.NAME}.mod.d')
            assert all(str(x) in pins or x.is_relative_to(folder) for x in md),'unpinned metadata header'
            base.run([str(base.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(base.CONTEXT/'scripts/module.lds'),'-o',str(folder/f'{base.NAME}.ko'),str(obj),str(folder/f'{base.NAME}.mod.o')],base.CONTEXT,folder/'link-module')
            module=folder/f'{base.NAME}.ko';candidate=comparison.Elf(module)
            old_imports=sorted((x['name'],x['type'],x['bind'],x['other']) for x in parent.syms if x['section']==0 and x['name'])
            new_imports=sorted((x['name'],x['type'],x['bind'],x['other']) for x in candidate.syms if x['section']==0 and x['name'])
            assert old_imports==new_imports,'imports changed'
            assert not (folder/'Module.symvers').read_text().strip(),'exports changed'
            assert base.elf_modinfo(parent)==base.elf_modinfo(candidate),'module metadata changed'
            delta=function_deltas(parent,candidate);save(folder/'function-comparison.json',delta)
            data=data_deltas(parent,candidate);save(folder/'allocated-data-comparison.json',data)
            gaps=code_gap_deltas(parent,candidate);save(folder/'executable-gap-comparison.json',gaps)
            changed=[x['name'] for x in delta if not x['unchanged']]
            # Struct diagnostic counter shifts fields in the open/worker/stats
            # paths. Allowed bodies are explicitly enumerated, never inferred
            # from matching prefixes. Unexpected changes fail this gate.
            allowed={'qtn_emac_stats','qtn_emac_irq_poll_work','qtn_emac_open','f352_create_port'}
            assert set(changed)<=allowed,('unexpected function change',changed)
            base.run([str(base.TC)+'objdump','-dr',str(module)],base.CONTEXT,folder/'disassembly')
            modules.append({'lane':lane,'path':str(module),'sha256':sha(module),'bytes':module.stat().st_size,
                'functions_compared':len(delta),'functions_unchanged':sum(x['unchanged'] for x in delta),'changed_functions':changed,'imports_unchanged':len(new_imports),'modinfo_unchanged':True,'allocated_data_sections_checked':len(data),'executable_gap_bytes_checked':sum(x['parent_bytes'] for x in gaps)})
        assert modules[0]['sha256']==modules[1]['sha256'],'builds differ'
        for name,h in pins.items():assert sha(name)==h,'input drift '+name
        result.update(status='PASS_OFFLINE_F374_COMPLETE_MODULE',modules=modules,reproducible=True,
            candidate_source=str(source),baseline_exact_sha256=base.EXPECTED,inputs_unchanged=True,
            limits=['Only RX-restart ownership on timeout is corrected.',
              'Inherited ndo_stop/remove/open failure DMA lifetime gap remains unresolved.',
              'No local/global reset added. No packet throughput, boot, release or installation acceptance.',
              'Same module/DT identity retained for offline comparisons only; no package created.'])
    except Exception as error:result['error']=str(error)
    save(out/'result.json',result);print(json.dumps({'result':str(out/'result.json'),**result}),flush=True)
    return result['status']!='PASS_OFFLINE_F374_COMPLETE_MODULE'

if __name__=='__main__':sys.exit(main())
