"""File-only DT/config/ELF/API closure for the qualified F339 sensor kit."""
from pathlib import Path
from datetime import datetime,timezone
import json,re,struct
from elftools.elf.elffile import ELFFile
import build_f339_topaz_hwmon as b
def cfg(path):
    result={}
    for line in Path(path).read_text().splitlines():
        if line.startswith('CONFIG_'):key,value=line.split('=',1);result[key]=value
        elif re.fullmatch(r'# CONFIG_\w+ is not set',line):result[line[2:-11]]='n'
    return result
def elf_symbols(path):
    with Path(path).open('rb') as f:
        e=ELFFile(f);table=e.get_section_by_name('.symtab');symbols=list(table.iter_symbols())
        return {'imports':{s.name for s in symbols if s['st_shndx']=='SHN_UNDEF' and s.name},'exports':{s.name[10:] for s in symbols if s.name.startswith('__ksymtab_')},'machine':e.header['e_machine']}
def embedded(path):
    with Path(path).open('rb') as f:
        e=ELFFile(f);s=e.get_section_by_name('.symtab').get_symbol_by_name('__dtb_topaz_mitrastar_squashfs_begin')[0];address=int(s['st_value'])
        for sec in e.iter_sections():
            start=int(sec['sh_addr'])
            if start<=address<start+int(sec['sh_size']):data=sec.data()[address-start:];return data[:struct.unpack_from('>I',data,4)[0]],address
    raise ValueError('embedded DT missing')
def main():
    kit=b.ROOT/'outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z';report=json.loads((kit/'result.json').read_text());b.require(report['status']=='PASS_OFFLINE_HWMON_OEM_ORACLE','kit not qualified')
    for row in report['artifacts'].values():b.require(b.sha(row['path'])==row['sha256'],'artifact drift')
    out=b.ROOT/'outputs/kernel-port'/('f339-contract-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    base=b.nodes(kit/'base-f321.dtb');default=b.nodes(kit/'f339-default.dtb');example=b.nodes(kit/'f339-ownership-example.dtb');sensor='/soc/temperature-sensor@e0000108'
    checks={
        'all_23_original_nodes_preserved':len(base)==23 and all(default[k]==v for k,v in base.items()),
        'only_sensor_node_added':set(default)-set(base)=={sensor},
        'sensor_default_disabled':default[sensor]['status']==b'disabled\0',
        'exact_sensor_registers':default[sensor]['reg']==struct.pack('>II',0xe0000108,12),
        'no_qualification_claim_in_dt':all(k not in default[sensor] for k in ['quantenna,temperature-experiment','quantenna,clock-map-ownership-qualified']),
        'no_guessed_sensor_clock':all(k not in default[sensor] for k in ['clocks','clock-frequency']),
        'ownership_only_changes_recovery':{k for k in base if example[k]!=base[k]}=={'/soc/recovery@e0000000'},
        'ownership_preserves_other_resources':example['/soc/recovery@e0000000']['reg']==struct.pack('>II',0xe0000000,8)+base['/soc/recovery@e0000000']['reg'][8:],
    }
    body,address=embedded(kit/'kernel-input/f339.vmlinux');(out/'embedded.dtb').write_bytes(body);checks['disabled_sensor_dt_really_embedded']=b.nodes(out/'embedded.dtb')==default
    a=cfg(kit/'base-f321.config');c=cfg(kit/'kernel-input/f339.config');changed={k:[a.get(k,'n'),c.get(k,'n')] for k in set(a)|set(c) if a.get(k,'n')!=c.get(k,'n')}
    checks['only_hwmon_configuration_changes']=changed=={'CONFIG_HWMON':['n','m']}
    old=elf_symbols(b.F321/(b.BASE+'.vmlinux'));core=elf_symbols(kit/'kernel-input/hwmon.ko');driver=elf_symbols(kit/'a/temp_sens.ko')
    exports=old['exports']|core['exports']|driver['exports'];missing=sorted((core['imports']|driver['imports'])-exports)
    checks['f321_export_closure']=not missing;checks['both_modules_arc700']=core['machine']==driver['machine']=='EM_ARC_COMPACT';checks['legacy_symbol_retained']='topaz_read_internal_temp_sens' in driver['exports']
    b.require(all(checks.values()),'contract failed '+str([k for k,v in checks.items() if not v]))
    result=dict(status='PASS_OFFLINE_DT_ABI_CONTRACT',checks=checks,check_count=len(checks),configuration_delta=changed,unresolved_symbols=missing,
        embedded_dtb_address=hex(address),embedded_dtb_sha256=b.sha(out/'embedded.dtb'),hardware_actions=False,physical_sensor_acceptance=False,
        stock_f321_kernel_runtime_abi_accepted=False,kit_result=str(kit/'result.json'),kit_sha256=b.sha(kit/'result.json'))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'output':str(out),'status':result['status'],'checks':len(checks)},indent=2))
if __name__=='__main__':main()
