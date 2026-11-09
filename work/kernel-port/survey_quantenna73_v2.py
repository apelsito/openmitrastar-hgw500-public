"""Apply explicit 7.3 API adaptations to isolated5GHz compile survey."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,shutil,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'quantenna73-api-survey-v1';OUT=BASE/'quantenna73-api-survey-v3'
KERNEL=BASE/'radioeth73-events-ram-v2/source';CONTEXT=BASE/'radioeth73-events-ram-v2/a'
ROOT=Path('/workspace/user-home/Desktop/MitraStar')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable survey exists')
 OUT.mkdir(mode=0o700)
 for folder in ['source','headers','compat','legacy','port-context']:shutil.copytree(OLD/folder,OUT/folder)
 # These are real header adaptations, not pretend fields in a synthetic object.
 # Their future hardware use requires rebuilding whole kernel+all modules.
 kernel_header=OUT/'kernel-overrides/linux';kernel_header.mkdir(parents=True)
 skb=(KERNEL/'include/linux/skbuff.h').read_text()
 anchor='\tstruct_group(headers,\n'
 assert skb.count(anchor)==1
 extra='''
\t/* Native Topaz packet metadata; copied by __copy_skb_header(). */
\tstruct qtn_skb_cb qtn_cb;
\tstruct net_device *orig_dev;
\tstruct qtn_skb_recycle_list *recycle_list;
\t__u32 src_port;
\t__u32 dest_port;
\t__u8 is_recyclable:1, cache_is_cleaned:1, hbm_no_free:1, ext_l2_filter:1;
'''
 skb=skb.replace('#include <linux/types.h>','#include <linux/types.h>\n#include <linux/openmitrastar_qtn_skb.h>',1)
 if '#include <linux/openmitrastar_qtn_skb.h>' not in skb:
  skb=skb.replace('#include <linux/kernel.h>','#include <linux/kernel.h>\n#include <linux/openmitrastar_qtn_skb.h>',1)
 assert '#include <linux/openmitrastar_qtn_skb.h>' in skb
 skb=skb.replace(anchor,anchor+extra,1)
 (kernel_header/'skbuff.h').write_text(skb)
 # Preserve I/O semantics; make conversion of ARC32 register address explicit.
 compat=OUT/'compat/openmitrastar_qdrv_compat.h'
 support='''
#include <linux/timer.h>
#include <linux/proc_fs.h>
#include <linux/preempt.h>
#define del_timer timer_delete
#define del_timer_sync timer_delete_sync
#define from_timer timer_container_of
#define PDE_DATA pde_data
#define in_irq in_hardirq
static inline u32 om73_readl(unsigned long address) { return readl((void __iomem *)address); }
static inline void om73_writel(u32 value, unsigned long address) { writel(value,(void __iomem *)address); }
#undef readl
#undef writel
#define readl(address) om73_readl((unsigned long)(address))
#define writel(value,address) om73_writel((value),(unsigned long)(address))
'''
 compat.write_text(compat.read_text().replace('#include <linux/fs.h>','#include <linux/fs.h>\n'+support,1))
 file=OUT/'source/qdrv/qdrv_f355_lifetime.c'
 file.write_text(file.read_text().replace('strlcpy(f355_first_operation,operation,sizeof(f355_first_operation))','strscpy(f355_first_operation,operation,sizeof(f355_first_operation))'))
 # Fixed-width BSD strncpy use must retain its zero-padding behavior. It is
 # deliberately named as port helper and not aliased to strscpy.
 string=OUT/'compat/om73_fixed_string.h'
 string.write_text('''#ifndef OM73_FIXED_STRING_H
#define OM73_FIXED_STRING_H
static inline char *om73_fixed_strncpy(char *dst,const char *src,unsigned long size)
{ unsigned long i=0;for(;i<size&&src[i];i++)dst[i]=src[i];for(;i<size;i++)dst[i]=0;return dst; }
#endif
''')
 for directory in ['source/qdrv','source/wlan']:
  for file in (OUT/directory).glob('*.c'):
   text=file.read_text()
   text=re.sub(r'\bstrncpy\(', 'om73_fixed_strncpy(',text)
   file.write_text(text)
 base=[item.replace(str(OLD),str(OUT)) for item in json.loads((OLD/'compile-base.json').read_text())]
 base[1:1]=['-I'+str(OUT/'kernel-overrides')]
 base+=['-include',str(string)]
 (OUT/'compile-base.json').write_text(json.dumps(base,indent=2)+'\n')
 old=json.loads((OLD/'result.json').read_text());jobs=old['rows'];rows=[]
 def compile(record):
  module=record['module'];name=record['unit'];folder=OUT/'objects'/module;folder.mkdir(parents=True,exist_ok=True)
  oldcmd=json.loads((OLD/'objects'/module/(name+'.command.json')).read_text())
  source=Path(oldcmd[-1].replace(str(OLD),str(OUT)))
  cmd=base+(['-DQTN_DYN_CCA=1'] if module=='wlan' else [])+['-DKBUILD_BASENAME="'+name+'"','-DKBUILD_MODNAME="'+module+'"','-c','-o',str(folder/(name+'.o')),str(source)]
  (folder/(name+'.command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  r=subprocess.run(cmd,cwd=CONTEXT,capture_output=True,text=True,timeout=120);(folder/(name+'.stderr')).write_text(r.stderr)
  errors=[line for line in r.stderr.splitlines() if re.search(r'error:|fatal error:',line)]
  row={'module':module,'unit':name,'exit':r.returncode,'errors':errors[:24]}
  if not r.returncode:row.update(bytes=(folder/(name+'.o')).stat().st_size,sha256=sha(folder/(name+'.o')))
  print(json.dumps({'module':module,'unit':name,'compiled':r.returncode==0,'first_error':errors[:1]}),flush=True);return row
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(compile,jobs))
 result={'status':'QUANTENNA73_API_ADAPTATION_COMPILE_ONLY','compiled':sum(r['exit']==0 for r in rows),'failed':sum(r['exit']!=0 for r in rows),'units':len(rows),'rows':rows,'kernel_header_sha256':sha(kernel_header/'skbuff.h'),'compat_sha256':sha(compat),'hardware_accessed':False,'firmware_eligible':False,'whole_kernel_with_packet_layout':'UNRUN','module_link':'UNRUN','limits':['No hardware use: whole kernel and every driver must be rebuilt with packet-layout change.','Sysctl registration/const callbacks, legacy filesystem access and typed lifetime remain explicit errors; no no-op stubs.']}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['status','compiled','failed','units']}))
if __name__=='__main__':main()
