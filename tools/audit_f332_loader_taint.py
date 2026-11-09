"""Audit the REAL Linux 5.10 proprietary-taint/GPL-only import restriction."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
BUNDLE=BASE/'f332-kernel-bundle-20260921T121717Z'
QDRV=ROOT/'outputs/kernel-port/f332-qdrv-ready-20260921T122632Z/qdrv-a.ko'
KERNEL_SYMBOLS=ROOT/'outputs/kernel-port/f334-qdrv-profile-20260921T105936Z/kernel-Module.symvers'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inspect(path):
 with path.open('rb') as f:
  elf=ELFFile(f);info=dict(x.split('=',1) for x in elf.get_section_by_name('.modinfo').data().decode().split('\0') if '=' in x)
  imports=[s.name for s in elf.get_section_by_name('.symtab').iter_symbols() if s['st_shndx']=='SHN_UNDEF' and s.name]
  return {'name':info['name'],'license':info['license'],'depends':info.get('depends','').split(','),'imports':imports,'sha256':sha(path)}
def main():
 out=BASE/('f332-loader-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
 loader=subprocess.check_output(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat','/home/user/mitrastar-linux-5.10.260/kernel/module.c'])
 (out/'kernel-module.c').write_bytes(loader)
 vmlinux=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.vmlinux'
 actual_guard_present=b'module using GPL-only symbols uses symbols from proprietary module' in vmlinux.read_bytes()
 kernel={r[1]:r[3] for line in KERNEL_SYMBOLS.read_text().splitlines() if (r:=line.split())}
 paths=[BUNDLE/'a/provider/qtn_radar_f332.ko',BUNDLE/'a/engine/f332_detector_engine.ko',BASE/'f330-kernel-preprocess-20260921T103900Z/a/f330_preprocess_engine.ko',BASE/'f331-kernel-20260921T103722Z/a/f331_postfilter_port.ko',QDRV]
 modules={r['name']:r for p in paths if (r:=inspect(p))}
 exports={}
 symvers=[BUNDLE/'a/provider/Module.symvers',BUNDLE/'a/engine/Module.symvers',BASE/'f330-kernel-preprocess-20260921T103900Z/a/Module.symvers',BASE/'f331-kernel-20260921T103722Z/a/Module.symvers']
 for p in symvers:
  for line in p.read_text().splitlines():
   r=line.split();exports[r[1]]={'owner':Path(r[2]).name,'type':r[3]}
 tainted={n for n,m in modules.items() if m['license']=='Proprietary'}
 changed=True
 while changed:
  changed=False
  for n,m in modules.items():
   if n not in tainted and any(exports.get(s,{}).get('owner') in tainted for s in m['imports']):tainted.add(n);changed=True
 blockers=[]
 for n,m in modules.items():
  only=[s for s in m['imports'] if kernel.get(s)=='EXPORT_SYMBOL_GPL' or exports.get(s,{}).get('type')=='EXPORT_SYMBOL_GPL']
  m['gpl_only_imports']=only;m['proprietary_or_inherited_taint']=n in tainted
  if n in tainted and only:blockers.append({'module':n,'reason':'Linux 5.10 inherit_taint/resolve_symbol forbids GPL-only imports with proprietary-tainted symbol providers','symbols':only})
 report={'schema':'openmitrastar.f332-real-loader-audit/v1','status':'NO_GO_KERNEL_PROPRIETARY_GPL_ONLY_MIX' if blockers else 'PASS_NO_TAINT_IMPORT_CONFLICT','modules':modules,'blockers':blockers,'kernel_symbol_source':str(KERNEL_SYMBOLS),'kernel_symbol_source_sha256':sha(KERNEL_SYMBOLS),'kernel_loader_evidence':'/home/user/mitrastar-linux-5.10.260/kernel/module.c:1432-1478 inherit_taint and resolve_symbol','kernel_loader_source_sha256':hashlib.sha256(loader).hexdigest(),'actual_f321_vmlinux_sha256':sha(vmlinux),'actual_f321_guard_message_present':actual_guard_present,'kernel_or_host_checks_modified':False,'licenses_modified':False,'hardware':False,'candidate_runtime_loadable':not blockers,'architecture_resolution':'Use a legitimate userspace UAPI for proprietary OEM math, or finish a fully GPL native reconstruction. Do not relabel binaries, alter loader/export checks, or hide dependency ownership.'}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':report['status'],'blocked_modules':[b['module'] for b in blockers]},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
