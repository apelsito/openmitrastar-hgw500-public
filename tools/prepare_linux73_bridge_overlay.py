"""Port existing owned FDB/isolation provider bodies into current Linux73 bridge."""
import argparse,difflib,hashlib,json
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--kernel',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);prior=ROOT/'work/kernel-port/linux-5.10/qdrv-core-compat.patch';patch=prior.read_text();files={};diff=[]
 def additions(start,end):
  t=patch[patch.index(start):patch.index(end,patch.index(start))];return '\n'.join(l[1:]for l in t.splitlines()if l.startswith('+')and not l.startswith('+++'))+'\n'
 fdb=additions('+#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT\n+int openmitrastar_br_fdb_fillbuf','+\n static struct net_bridge_fdb_entry *fdb_create')
 # Match Linux73 current FDB concurrent timestamp read and bound host array size.
 fdb=fdb.replace('if (!dev || !entries)','if (!dev || !entries || maxnum > INT_MAX ||\n\t    maxnum > SIZE_MAX / sizeof(*entries))',1).replace('jiffies_delta_to_clock_t(jiffies - fdb->updated)','jiffies_delta_to_clock_t(jiffies - READ_ONCE(fdb->updated))')
 isolate=additions('+#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT\n+static int br_ap_isolate_enabled',' /* Don\'t forward packets')
 for rel,block in [('net/bridge/br_fdb.c',fdb),('net/bridge/br_forward.c',isolate)]:
  original=a.kernel/rel;t=original.read_text();anchor='#include "br_private.h"';assert t.count(anchor)==1;t=t.replace(anchor,'#include <linux/openmitrastar_bridge.h>\n'+anchor,1)
  if rel.endswith('br_fdb.c'):
   body=function(t,'int br_fdb_fillbuf(');assert t.count(body)==1;t=t.replace(body,body+'\n\n'+block,1)
  else:t=t.replace(anchor,anchor+'\n\n'+block,1)
  if rel.endswith('br_forward.c'):
   anchor='\t\t!br_skb_isolated(p, skb);';assert t.count(anchor)==1;t=t.replace(anchor,'''#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT
\t\topenmitrastar_br_ap_isolate_should_forward(p, skb) &&
#endif
'''+anchor,1)
  f=a.output/'kernel-overlay'/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(t,newline='\n');files[rel]=sha(f);diff.extend(difflib.unified_diff(original.read_text().splitlines(True),t.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 (a.output/'linux73-bridge-provider.patch').write_text(''.join(diff));pins={str(p):sha(p)for p in[Path(__file__),prior,a.kernel/'net/bridge/br_fdb.c',a.kernel/'net/bridge/br_forward.c',ROOT/'work/kernel-port/linux-5.10/include/linux/openmitrastar_bridge.h']};r={'status':'SOURCE_ONLY_LINUX73_REAL_BRIDGE_FDB_ISOLATION_PROVIDERS_PENDING_COMPILE','hardware_accessed':False,'firmware_eligible':False,'files':files,'pins':pins,'config_required':['CONFIG_NET_SCHED=y','CONFIG_BRIDGE=m'],'functions':['openmitrastar_br_fdb_fillbuf','openmitrastar_br_fdb_update_const','br_set_ap_isolate','br_get_ap_isolate'],'limits':['ExistingownedLinux510FDB/isolationcontractportedtoactual73bridgebodies; no successful kernelcompileyet.','MainlineFDBdoesnotencodeQuantenna hardware sub_port; originaladapter limitation retained.','Privateisolationpredicateincludedinshould_deliver; neitheremptyvoidprovider nor unconditionalsuccess.','Nohardware/runtimebridge/client/trafficacceptance.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
