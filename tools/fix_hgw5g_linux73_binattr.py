"""Linux7.3 sysfs callback now requires constbin_attribute; newsourceonly."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];shutil.copytree(a.parent,a.output);f=a.output/'source/qdrv/qdrv_module.c';t=f.read_text();needle='BIN_ATTR_ACCESS_DECL(qdrv_attr_rssi_phy_stats, filp, p_kobj, p_bin_attr, buf, offset, size)';assert t.count(needle)==1;t=t.replace(needle,'static ssize_t qdrv_attr_rssi_phy_stats(struct file *filp,struct kobject *p_kobj,\n    const struct bin_attribute *p_bin_attr,char *buf,loff_t offset,size_t size)',1);f.write_text(t,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_CONST_BINATTR_API_FIX',parent=str(a.parent),changed_sources={'source/qdrv/qdrv_module.c':sha(f)});proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed_sources':proof['changed_sources']},indent=2))
if __name__=='__main__':main()
