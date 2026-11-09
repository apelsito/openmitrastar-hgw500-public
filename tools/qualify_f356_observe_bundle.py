"""Qualify immutable F356 RAM artifacts and their source/test links, without hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,lzma,struct,zlib
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(p),'sha256':sha(p)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bundle',type=Path,required=True);a=ap.parse_args();bundle=a.bundle.resolve();r=json.loads((bundle/'result.json').read_text());checks=[]
 def check(name,ok):
  checks.append({'name':name,'passed':bool(ok)})
  if not ok:raise ValueError(name)
 check('offline RAM observe scope',r['status']=='PASS_OFFLINE_RAM_OBSERVE_BUNDLE' and not r['hardware_actions'] and not r['kernel_recompiled'] and not r['dt_or_config_modified'] and not r['firmware_flash_image'] and not r['rootfs_bundled'] and not r['save_allowed'] and not r['allow_program'])
 for name in ['kernel','uimage','provider','supervisor_ram','cli','loader','rootfs','bootbase_contract']:
  item=r[name];check('artifact '+name,sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'])
 for name,p in r['exact_kernel_inputs'].items():check('exact unchanged F350 '+name,sha(p['path'])==p['sha256'])
 check('packing inputs unchanged',all(sha(p)==h for p,h in r['sources'].items()))
 evidence={}
 for name,item in r['evidence'].items():
  check('evidence '+name,sha(item['path'])==item['sha256']);evidence[name]=json.loads(Path(item['path']).read_text())
 for name in ['provider','supervisor']:
  check(name+' sources current',all(sha(ROOT/p)==h for p,h in evidence[name]['sources'].items()))
 check('module exactly matches tested sources',evidence['provider']['sources']==evidence['provider_tests']['sources'])
 check('ID gate and partial cleanup tests','F356_ID_GATE_PASS initial_ids=5 changed_during_cleanup=1 unknown_id_writes=0' in evidence['provider_tests']['logs']['model.log'])
 check('post-release diagnostic and real adapter tests','F356_KERNEL_ADAPTER_PASS cases=11 id_before_write=1' in evidence['provider_tests']['logs']['adapter.log'])
 check('static analyses pass',evidence['provider_tests']['logs']['analyzer.log']=='' and evidence['supervisor']['analyzer']=='PASS')
 cases=evidence['supervisor']['process_tests']['process_cases']
 check('supervisor policy and all profile cases',len(cases)==13 and {'f340-uts-refused-before-open','wrong-release-refused-before-open','wrong-build-timestamp-refused-before-open','missing-uts-refused-before-open'}<=set(cases) and evidence['supervisor']['policy_tests']=='F340_POLICY_PASS cases=20 hardware=0')
 supervisor=Path(r['supervisor_ram']['path']).read_bytes()
 check('production supervisor requires actual #350 profile',b'#350 @1790006400' in supervisor and b'#340 @1790006400' not in supervisor and b'F356_TEST_OPEN_TRACE' not in supervisor and b'F340_TEST' not in supervisor)
 check('IPC remains F340-compatible without mislabelling kernel',r['supervisor_ram']['ipc_schema']=='openmitrastar.f340-supervisor-state/v1' and r['supervisor_ram']['kernel_version']=='#350 @1790006400' and not r['supervisor_ram']['automatic_arm'])
 for name in ['provider','supervisor']:
  path=Path(evidence[name]['artifact']['path']);other=path.parent.parent/'b'/path.name if name=='provider' else path.with_name(path.name.removesuffix('-a')+'-b')
  check(name+' double build identical',path.read_bytes()==other.read_bytes())
 check('two RAM packings identical',all((bundle/'a'/name).read_bytes()==(bundle/'b'/name).read_bytes() for name in ['f356.lzma','F356-OBSERVE-RAM-ONLY.uImage','F356-OBSERVE-RAM-ONLY.ras.bin']))
 raw=Path(r['exact_kernel_inputs']['raw']['path']).read_bytes();ras=Path(r['kernel']['path']).read_bytes();uimage=Path(r['uimage']['path']).read_bytes()
 check('RAS and uImage same exact compressed kernel',ras[0x2000:]==uimage[64:] and lzma.decompress(ras[0x2000:],format=lzma.FORMAT_ALONE)==raw)
 check('Bootbase header and RAM limits',json.loads(Path(r['bootbase_contract']['path']).read_text())['accepted_by_contract'] and int(r['memory']['staging'],16)+len(ras)<int(r['memory']['crc_scratch'],16)<int(r['memory']['load'],16) and int(r['memory']['kernel_end'],16)<int(r['memory']['ddr_end'],16))
 check('runtime kernel and load/entry',r['kernel']['kernel_version']=='#350 @1790006400' and r['memory']['load']=='0x8493a000' and r['memory']['entry']=='0x8493e000')
 check('kernel CRC bound',f'{zlib.crc32(ras)&0xffffffff:08x}'==r['kernel']['crc32'])
 exports={line.split()[1] for line in Path(r['exact_kernel_inputs']['module_symvers']['path']).read_text().splitlines()}
 check('all provider imports resolve in exact F350 kernel',set(evidence['provider']['imports'])<=exports)
 with Path(r['provider']['path']).open('rb') as f:
  elf=ELFFile(f);info=elf.get_section_by_name('.modinfo').data();sym=elf.get_section_by_name('.symtab')
  check('new identifiable GPL ARC module',elf.elfclass==32 and elf.header['e_machine']=='EM_ARC_COMPACT' and b'license=GPL\0' in info and b'version=356\0' in info)
  for name in ['allow_hw','allow_program']:
   v=sym.get_symbol_by_name(name)[0];check('default inactive parameter '+name,elf.get_section(v['st_shndx'])['sh_type']=='SHT_NOBITS' and v['st_size']==1)
 check('observe-only runtime binding',r['provider']['parameters']=='allow_hw=1 allow_program=0' and r['allowed_operation']=='OBSERVE_ONLY' and r['provider']['module_name']=='qtn_f356_journal')
 check('rootfs unchanged/read-only',r['rootfs']['physical_address']=='0x90960000' and r['rootfs']['access']=='unchanged persistent F340 read-only rootfs' and ' ro rootwait ' in r['bootargs'])
 check('passive observation is not flash identity acceptance',evidence['passive_control']['observed_spi_control']=='00000004' and evidence['passive_control']['flash_identification_or_programming_accepted'] is False and evidence['passive_control']['cpu_bus_halt_recovery_proven'] is False)
 out=ROOT/'outputs/preflight'/('f356-artifacts-qualified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 result={'schema':'openmitrastar.f356-artifact-qualification/v1','status':'PASS_OFFLINE_F356_OBSERVE_ARTIFACTS','checks':checks,'bundle_manifest':pin(bundle/'result.json'),'kernel':r['kernel'],'provider':r['provider'],'supervisor_ram':r['supervisor_ram'],'hardware_actions':False,'physical_observe':'UNRUN','flash_image':False,'save_allowed':False,'qualifier':pin(Path(__file__).resolve())}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(checks),'result':str(out/'result.json')}))
if __name__=='__main__':main()
