"""Explicit7.3 RTNL declarations for VOPT same-TU adapter; no semantic changes."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);rel='source/wlan/ieee80211_wireless.c';f=a.output/rel;t=f.read_text();assert '#include <linux/rtnetlink.h>'not in t;t=t.replace('#include <linux/netdevice.h>','#include <linux/netdevice.h>\n#include <linux/rtnetlink.h>',1);f.write_text(t,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_RTNL_HEADER_API_FIX',parent=str(a.parent),changed_sources={rel:sha(f)});proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed_sources':proof['changed_sources']},indent=2))
if __name__=='__main__':main()
