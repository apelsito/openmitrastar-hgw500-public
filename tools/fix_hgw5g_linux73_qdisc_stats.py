"""Read modernu64qdiscstats through accessor, preserve32bittelemetrylowword."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);rel='source/qdrv/qdrv_pktlogger.c';f=a.output/rel;t=f.read_text();assert t.count('= qd->bstats.packets;')==2;t=t.replace('= qd->bstats.packets;','= (u32)u64_stats_read(&qd->bstats.packets);');f.write_text(t,newline='\n');k=a.output/'Kbuild';t=k.read_text();import re;t=re.sub(r'^QTN_GPL :=.*$','QTN_GPL ?= $(src)/original-Quantenna-GPL',t,flags=re.M);k.write_text(t,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_QDISC_U64_STATS_API_FIX',parent=str(a.parent),changed_sources={rel:sha(f),'Kbuild':sha(k)},kbuild_sha256=sha(k));proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed_sources':proof['changed_sources']},indent=2))
if __name__=='__main__':main()
