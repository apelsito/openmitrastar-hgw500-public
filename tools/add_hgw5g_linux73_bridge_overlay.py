"""Versionedreal7.3bridgekernelproviders andrequiredconfiguration manifest."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--bridge',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);bp=json.loads((a.bridge/'result.json').read_text());proof=json.loads((a.parent/'result.json').read_text());extra={}
 for rel,h in bp['files'].items():src=a.bridge/'kernel-overlay'/rel;assert sha(src)==h;dst=a.output/'kernel-overlay'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);extra[rel]=sha(dst)
 proof['kernel_overlay'].update(extra);proof.update(status='SOURCE_ONLY_LINUX73_FULL44_REAL_BRIDGE_NATIVE_PROVIDER_CLOSURE',parent=str(a.parent),bridge_result_sha256=sha(a.bridge/'result.json'),new_kernel_config_required=['OPENMITRASTAR_QDRV_COMPAT=y','WIRELESS_EXT=y','WEXT_CORE=y','WEXT_PRIV=y','NET_SCHED=y','BRIDGE=m','GPIOLIB=y','I2C=y']);proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'bridge':extra,'config_required':proof['new_kernel_config_required']},indent=2))
if __name__=='__main__':main()
