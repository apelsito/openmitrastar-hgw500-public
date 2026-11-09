"""Bind the corrected F350 module, real-source tests and immutable kernel. Offline only."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,struct,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary')
SOURCE=ROOT/'work/kernel-port/versions/f350-spi-journal'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):p=Path(p);return {'path':str(p),'sha256':sha(p)}
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for name in ['kernel','module','tests','guard']:ap.add_argument('--'+name,type=Path,required=True)
 a=ap.parse_args();paths={k:getattr(a,k).resolve() for k in ['kernel','module','tests','guard']}
 reports={k:json.loads((p/'result.json').read_text()) for k,p in paths.items()};checks=[]
 def check(name,ok):
  checks.append({'name':name,'passed':bool(ok)})
  if not ok:raise ValueError(name)
 k,m,t,g=[reports[n] for n in ['kernel','module','tests','guard']]
 check('own F350 kernel and final module outcomes',k['status']=='PASS_OFFLINE_READER_ARBITRATION_KERNEL' and k['kernel_build_identity']==350 and m['status']=='PASS_OFFLINE_KERNEL_MODULE')
 check('actual native provider and guard tests pass',t['status']==g['status']=='PASS')
 check('no hardware observations or activation claimed',all(not r['hardware_actions'] for r in reports.values()) and not m['physical_spi_control_observed'] and not m['physical_id_protection_observed'] and not m['flash_eligible'])
 check('module binds this exact kernel',Path(m['kernel_manifest']['path'])==paths['kernel']/'result.json' and m['kernel_manifest']['sha256']==sha(paths['kernel']/'result.json'))
 check('module pins exactly the tested provider sources',m['sources']==t['sources'])
 check('all provider sources current',all(sha(p)==h for p,h in m['sources'].items()))
 check('all guard sources current',all(sha(p)==h for p,h in g['sources'].items()))
 check('kernel overlay matches tested code',all(sha(p['path'])==p['sha256'] for p in k['sources']))
 check('kernel bytes and double build current',k['reproducible'] and all(sha(p['path'])==p['sha256'] for p in k['artifacts'].values()) and all(p.read_bytes()==(paths['kernel']/'b'/p.name).read_bytes() for p in (paths['kernel']/'a').iterdir()))
 module=Path(m['artifact']['path'])
 check('module reproducible and artifact exact',m['reproducible'] and sha(module)==m['artifact']['sha256'] and module.read_bytes()==(paths['module']/'b/qtn_f350_journal.ko').read_bytes())
 check('no silent link warnings',not (paths['module']/'build-a.log').read_text().strip() and not (paths['module']/'build-b.log').read_text().strip())
 exports={line.split()[1] for line in (paths['kernel']/'a/Module.symvers').read_text().splitlines()}
 required={'qtn_topaz_flash_claim','qtn_topaz_flash_release','qtn_topaz_flash_read_store','qtn_topaz_flash_stage_page','qtn_topaz_flash_quarantine'}
 check('five common-owner imports resolved by own kernel',required<=set(m['imports']) and set(m['imports'])<=exports)
 params={}
 with module.open('rb') as f:
  elf=ELFFile(f);sym=elf.get_section_by_name('.symtab');info=elf.get_section_by_name('.modinfo').data()
  check('ARC32 GPL module',elf.elfclass==32 and elf.header['e_machine']=='EM_ARC_COMPACT' and b'license=GPL\0' in info)
  for name in ['allow_hw','allow_program']:
   variable=sym.get_symbol_by_name(name)[0];section=elf.get_section(variable['st_shndx'])
   check('default zero '+name,section.header['sh_type']=='SHT_NOBITS' and variable['st_size']==1)
   param=sym.get_symbol_by_name('__param_'+name)[0];section=elf.get_section(param['st_shndx']);off=param['st_value']-section['sh_addr']
   permission=struct.unpack_from('<H',section.data(),off+12)[0];params[name]={'permission':oct(permission),'default':False}
   check('load-only gate parameter '+name,permission==0o400)
 check('real adapter checks access and ownership', 'default_mmio=0 capability=1 copies_outside_claim=1' in t['logs']['adapter.log'])
 check('full provider/NOR and explicit footer model passed','F350_FAULT_POSITIONS=4399' in t['logs']['model.log'] and 'F350_MODEL_PASS' in t['logs']['model.log'])
 check('both analyzers clean',t['logs']['analyzer.log']==g['tests']['analyzer.log']=='')
 check('actual concurrency staging and quarantine passed','groups=7 actual_pthread_exclusion=1' in g['tests']['core.log'])
 for folder,names in [('f342_config_journal',['f342_journal.c','f342_journal.h']),('f318_store_transaction',['f318_store_transaction.h']),('f345_spi_nor_protocol',['f345_protocol.c','f345_protocol.h'])]:
  for name in names:check('unchanged qualified source '+name,(SOURCE/'provider'/name).read_bytes()==(ROOT/'work/kernel-port/modules'/folder/name).read_bytes())
 check('F340 config/DT unchanged',(paths['kernel']/'a/f350.config').read_bytes()==(DEVICE/'analysis/f340-watchdog-kernel-20260921T132951Z/a/f340.config').read_bytes() and (paths['kernel']/'a/f350.dtb').read_bytes()==(DEVICE/'analysis/f340-watchdog-kernel-20260921T132951Z/a/f340.dtb').read_bytes())
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f350-qualified-'+stamp);out.mkdir(parents=True,exist_ok=False)
 witnesses={}
 for name in ['arch/arc/mm/ioremap.c','drivers/mtd/maps/physmap-core.c']:
  run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',k['isolated_source']+'/'+name],capture_output=True,check=True)
  dest=out/('witness-'+name.replace('/','_'));dest.write_bytes(run.stdout);witnesses[name]=pin(dest)
  if name.endswith('ioremap.c'):check('ARC ioremap forces uncached',b'prot = pgprot_noncached(prot)' in run.stdout and b'PAGE_KERNEL_NO_CACHE' in run.stdout)
  else:check('actual map virt originates from managed ioremap resource',b'info->maps[i].virt = devm_ioremap_resource(&dev->dev, res)' in run.stdout)
 primary=ROOT/'outputs/research/f345-nor-datasheet-20260921T135832Z'
 result={'schema':'openmitrastar.f350-spi-journal-qualification/v1','status':'PASS_OFFLINE_COMMON_BP0_JOURNAL',
  'created_utc':stamp,'checks':checks,'evidence':{n:pin(p/'result.json') for n,p in paths.items()},
  'module':m['artifact'],'params':params,'source_witnesses':witnesses,
  'primary_sources':{name:pin(primary/name) for name in ['MX25L12836E-v1.7.pdf','MX25L12835F-v1.7.pdf','Macronix-AN0177-v3.pdf']},
  'supported':'observed c22018, WPSEL0, BP0, idle single-transaction OEM controller path; E/F identity remains unknown',
  'protection':'no-op verified preservation only; no WRSR/CLSR/WPSEL/OTP/SPB/global protection command',
  'limits':{'write_blocks':['0xdc0000','0xdd0000'],'page_bytes':256,'payload_bytes':4096,'program_poll_ms':20,'erase_poll_ms':2100},
  'hardware_actions':False,'physical_spi_control_observed':False,'physical_id_protection_observed':False,'flash_eligible':False,
  'superseded_module':{'path':str(ROOT/'outputs/kernel-port/f350-provider-20260921T160932Z/result.json'),'reason':'before explicit sync/footer correction; never deployed'},
  'physical_gates_unrun':['legacy controller access/completion','ID/status/security snapshot','electrical command/read-array transition','program/erase persistence and protection readback'],
  'next_consumer':'ABI1 /dev/om-f350-journal ioctl F350_IOCTL; require response status/backend_status/journal_status, not just ioctl rc0',
  'identity_note':'kernel #350 retains base F340 DT; a future firmware and watchdog supervisor must bind the new kernel identity explicitly',
  'qualifier':pin(__file__)}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(checks),'result':str(out/'result.json')}))
if __name__=='__main__':main()
