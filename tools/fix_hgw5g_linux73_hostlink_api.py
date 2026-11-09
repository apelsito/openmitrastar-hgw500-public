"""Versioned7.3compat: in_irq→in_hardirq, exactstrncpy semantics, MMIOcast."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
COMPAT=r'''
/* Linux7.3removed in_irq alias: same hardIRQcount contract, not softIRQ. */
#ifndef in_irq
#define in_irq in_hardirq
#endif
/* Preserve original strncpy copy/pad/truncation semantics for historical ABI
 * buffers; replacing all callers with strscpy would alter nonterminated fields. */
static inline char *om_linux73_strncpy(char *destination,const char *source,size_t count)
{
    size_t copied=strnlen(source,count);
    memcpy(destination,source,copied);
    if(copied<count)memset(destination+copied,0,count-copied);
    return destination;
}
#define strncpy om_linux73_strncpy
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();shutil.copytree(a.parent,a.output);proof=json.loads((a.parent/'result.json').read_text());changes={};patch=[];rel='source/qdrv/compat/include/openmitrastar_qdrv_compat.h';f=a.output/rel;old=f.read_text();anchor='#include <linux/fs.h>';assert anchor in old;new=old.replace(anchor,anchor+'\n#include <linux/preempt.h>\n#include <linux/interrupt.h>\n#include <linux/string.h>',1);idx=new.rfind('#endif');new=new[:idx]+COMPAT+new[idx:];f.write_text(new,newline='\n');changes[rel]=sha(f);patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel));rel='source/qdrv/qdrv_soc.h';f=a.output/rel;old=f.read_text();assert old.count('writel(val, addr);')==1;new=old.replace('writel(val, addr);','writel(val, (void __iomem *)(uintptr_t)addr);',1);f.write_text(new,newline='\n');changes[rel]=sha(f);patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel));(a.output/'linux73-api-fix.patch').write_text(''.join(patch),newline='\n');proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};proof.update(status='SOURCE_ONLY_LINUX73_FULL44_HOSTLINK_API_FIX_PENDING_FRESH_BUILD',parent=str(a.parent),changed_sources=changes,api_patch_sha256=sha(a.output/'linux73-api-fix.patch'));(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changes':changes},indent=2))
if __name__=='__main__':main()
