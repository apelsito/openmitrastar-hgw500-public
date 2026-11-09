"""Versioned7.3 API fixes from actualcompile: timer/MMIO/kernel-file context."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);changed={};rel='source/qdrv/compat/include/openmitrastar_qdrv_compat.h';f=a.output/rel;t=f.read_text();idx=t.rfind('#endif');extra='''
/* Exact Linux7.3 renamed timer API compatibility; no timing policy changes. */
#ifndef from_timer
#define from_timer timer_container_of
#endif
#ifndef del_timer
#define del_timer timer_delete
#endif
#ifndef del_timer_sync
#define del_timer_sync timer_delete_sync
#endif
/* OEM register constants are CPU I/O addresses. Preserve MMIO ordering while
 * explicitly expressing pointer typing to modern Linux ARC accessors. */
#undef readl
#define readl(address) ({ u32 om_value=readl_relaxed((const volatile void __iomem *)(uintptr_t)(address)); __iormb(); om_value; })
#undef writel
#define writel(value,address) ({ __iowmb(); writel_relaxed((value),(volatile void __iomem *)(uintptr_t)(address)); })
''';t=t[:idx]+extra+t[idx:];f.write_text(t,newline='\n');changed[rel]=sha(f)
 for rel in('source/qdrv/qdrv_control.c','source/qdrv/qdrv_comm.c'):
  f=a.output/rel;t=f.read_text();import re
  t=re.sub(r'^\s*mm_segment_t (?:OldFs|old_fs);\n','\n',t,flags=re.M);t=re.sub(r'^\s*(?:OldFs|old_fs) = get_fs\(\);\n','\n',t,flags=re.M);t=re.sub(r'^\s*set_fs\((?:KERNEL_DS|OldFs|old_fs)\);\n','\n',t,flags=re.M);f.write_text(t,newline='\n');changed[rel]=sha(f)
 f=a.output/'Kbuild';t=f.read_text();needle='qtn73_support-y := providers/qtn_pm_qos_compat.o providers/qtn_platform_support.o providers/board_compat.o providers/runtime_compat.o\nobj-m += qtn73_support.o';assert needle in t;t=t.replace(needle,'\n'.join(n+'-y := providers/'+n+'.o'for n in('qtn_pm_qos_compat','qtn_platform_support','board_compat','runtime_compat'))+'\nobj-m += qtn_pm_qos_compat.o qtn_platform_support.o board_compat.o runtime_compat.o');f.write_text(t,newline='\n');changed['Kbuild']=sha(f);proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_TIMER_MMIO_KERNELFILE_API_FIX',parent=str(a.parent),changed_sources=changed,kbuild_sha256=sha(f));proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed':changed},indent=2))
if __name__=='__main__':main()
