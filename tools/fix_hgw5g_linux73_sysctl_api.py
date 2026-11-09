"""Current7.3 per-VAP sysctl registration and const-table callback ownership."""
import argparse,hashlib,json,shutil,re
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
DECL=r'''
#undef IEEE80211_SYSCTL_DECL
#define IEEE80211_SYSCTL_DECL(f,ctl,write,filp,buffer,lenp,ppos) \
    f(const struct ctl_table *ctl,int write,void __user *buffer,size_t *lenp,loff_t *ppos)
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);rel='source/wlan/ieee80211_linux.c';f=a.output/rel;t=f.read_text();anchor='#define proc_net init_net.proc_net';assert anchor in t;t=t.replace(anchor,anchor+'\n'+DECL,1)
 # Six handlers formerly mutated registeredctl->data to a stacklocal. Use local
 # copy now, so neither const API nor a concurrentcallback publishes stackptr.
 names=['debug','dev_type','monitor_nods_only','monitor_txf_len','monitor_phy_errors','monitor_crc_errors']
 for n in names:
  sig='IEEE80211_SYSCTL_DECL(ieee80211_sysctl_'+n;body=function(t,sig);brace=body.index('{');new=body[:brace+1]+'\n\tstruct ctl_table local_ctl=*ctl;'+body[brace+1:];new=new.replace('ctl->data = &val;','local_ctl.data = &val;').replace('ctl->maxlen = sizeof(val);','local_ctl.maxlen = sizeof(val);').replace('IEEE80211_SYSCTL_PROC_DOINTVEC(ctl,','IEEE80211_SYSCTL_PROC_DOINTVEC(&local_ctl,');t=t.replace(body,new,1)
 start=t.index('\t/* setup the table */',t.index('ieee80211_sysctl_vattach('));end=t.index('\tif (!vap->iv_sysctl_header)',start);old=t[start:end];new='''\t/* Keep storedVAPname atreserved[2] for the existing detachownership. */
        memset(vap->iv_sysctls,0,space);
        vap->iv_sysctls[2].procname=devname;
        memcpy(&vap->iv_sysctls[4],ieee80211_sysctl_template,sizeof(ieee80211_sysctl_template));
        for(i=4;vap->iv_sysctls[i].procname;i++)
                if(!vap->iv_sysctls[i].extra1)vap->iv_sysctls[i].extra1=vap;
        vap->iv_sysctls[i-1].data="";
        {
                char path[IFNAMSIZ+8];
                snprintf(path,sizeof(path),"net/%s",devname);
                /* CurrentAPI registers leaf table under explicitnamespacepath;
                 * old childtree registration API no longer exists. */
                vap->iv_sysctl_header=register_sysctl_sz(path,&vap->iv_sysctls[4],
                        ARRAY_SIZE(ieee80211_sysctl_template)-1);
        }
''';t=t[:start]+new+t[end:];needle='\t\tprintk("%s: failed to register sysctls!\\n", vap->iv_dev->name);\n\t\tkfree(vap->iv_sysctls);';assert needle in t;t=t.replace(needle,'\t\tprintk("%s: failed to register sysctls!\\n", vap->iv_dev->name);\n\t\tkfree(devname);\n\t\tkfree(vap->iv_sysctls);',1);f.write_text(t,newline='\n');(a.output/'sysctl-legacy-provenance.c.txt').write_text(old,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_MODERN_SYSCTL_API_FIX',parent=str(a.parent),changed_sources={rel:sha(f)});proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed_sources':proof['changed_sources']},indent=2))
if __name__=='__main__':main()
