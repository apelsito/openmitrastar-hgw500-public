"""File-only ABI/import and possible hardware-WDT producer audit of F321 peers."""
from pathlib import Path
import argparse,hashlib,io,json,struct,subprocess
from elftools.elf.elffile import ELFFile
import f336_wdt_ram_contract as c
def digest(b):return hashlib.sha256(b).hexdigest()
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def symbols(data):
    elf=ELFFile(io.BytesIO(data));table=elf.get_section_by_name('.symtab');rows=list(table.iter_symbols()) if table else []
    imports=sorted({s.name for s in rows if s['st_shndx']=='SHN_UNDEF' and s.name and s['st_info']['bind']!='STB_WEAK'})
    exports=sorted({s.name[len('__ksymtab_'):] for s in rows if s.name.startswith('__ksymtab_')})
    named=[s.name for s in rows if any(x in s.name.lower() for x in ('watchdog','disable_wd','wdt'))]
    hits=[]
    values=(0xf4000000,0xf4000004,0xf4000008,0xf400000c,0xe40c0000,0xe40c0004,0xe40c0008,0xe40c000c)
    regions=[(sec.name,sec.data()) for sec in elf.iter_sections() if int(sec['sh_flags'])&4]
    region_source='SHF_EXECINSTR sections'
    if not regions:
        regions=[('PT_LOAD_'+str(i),seg.data()) for i,seg in enumerate(elf.iter_segments()) if seg['p_type']=='PT_LOAD' and int(seg['p_flags'])&1]
        region_source='PF_X load segments (section table absent/unusable)'
    for region,body in regions:
        for value in values:
            enc=struct.pack('<I',((value&0xffff)<<16)|(value>>16));start=0
            while True:
                pos=body.find(enc,start)
                if pos<0:break
                hits.append({'section':region,'offset':pos,'constant':hex(value)});start=pos+1
    info=elf.get_section_by_name('.modinfo');vermagic=None
    if info:
        for field in info.data().split(b'\0'):
            if field.startswith(b'vermagic='):vermagic=field[9:].decode('ascii','replace')
    return {'imports':imports,'exports':exports,'related_symbols':named,'executable_wdt_literal_hits':hits,'vermagic':vermagic,'machine':elf.header['e_machine'],
            'executable_region_source':region_source,'executable_bytes_scanned':sum(len(data) for _,data in regions),'symbol_table_present':table is not None}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--kernel',type=Path);args=ap.parse_args()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    rootfs=c.F321/(c.F321_BASE+'.rootfs.squashfs');inventory=json.loads((c.F321/'rootfs-inventory.json').read_text())['after']
    c.require(c.sha(rootfs)=='75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e','rootfs drift')
    selected=[name for name,entry in inventory.items() if entry['type']=='file' and (name.endswith('.ko') or (name.startswith('lib/firmware/') and ('qtn_driver' in name or 'auc_driver' in name or 'rdsp_driver' in name)))]
    entries={}
    for name in selected:
        p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','unsquashfs','-cat',linux(rootfs),name],capture_output=True,check=True)
        c.require(digest(p.stdout)==inventory[name]['sha256'],'peer drift '+name)
        dest=out/'payloads'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.stdout)
        entry={'sha256':digest(p.stdout),'bytes':len(p.stdout)}
        if p.stdout[:4]==b'\x7fELF':entry.update(symbols(p.stdout));entry['format']='ELF'
        else:entry['format']='opaque';entry['producer_analysis']='UNRESOLVED_OPAQUE_FIRMWARE'
        entries[name]=entry
    result={'schema':'openmitrastar.f336-f321-peer-audit/v1','rootfs_sha256':c.sha(rootfs),'entries':entries,
            'hardware_actions':False,'producer_exclusivity_proven':False,
            'scope':'Literal and symbol scan is evidence only, not proof that no computed/indirect/firmware writer exists'}
    if args.kernel:
        kernel=symbols(args.kernel.read_bytes());exports=set(kernel['exports'])
        for item in entries.values():exports.update(item.get('exports',[]))
        missing={name:sorted(set(item.get('imports',[]))-exports) for name,item in entries.items() if name.endswith('.ko')}
        result['missing_imports']={name:items for name,items in missing.items() if items};result['kernel_sha256']=c.sha(args.kernel)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(out),'files':len(entries),'literal_hit_files':[n for n,v in entries.items() if v.get('executable_wdt_literal_hits')],
                      'related_symbol_files':[n for n,v in entries.items() if v.get('related_symbols')],
                      'opaque_files':[n for n,v in entries.items() if v['format']=='opaque'],'missing_imports':result.get('missing_imports','kernel not supplied')}))
if __name__=='__main__':main()
