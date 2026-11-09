"""Keep kernelIPv6 visible to nativeFWT/TQEproviders; privateQDRVoffload scoped."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);rel='source/qdrv/compat/include/openmitrastar_qdrv_compat.h';f=a.output/rel;t=f.read_text();needle='#ifdef OPENMITRASTAR_QDRV_NO_IPV6_OFFLOAD\n#undef CONFIG_IPV6\n#endif';assert needle in t;t=t.replace(needle,'#if defined(OPENMITRASTAR_QDRV_NO_IPV6_OFFLOAD) && !defined(OPENMITRASTAR_NATIVE_IPV6_PROVIDER)\n#undef CONFIG_IPV6\n#endif',1);f.write_text(t,newline='\n');k=a.output/'Kbuild';t=k.read_text();t+='\n# NativeFWT/TQE/IPproviderneedsactualIPv6types independentofQDRVprivateNDISC.\n';
 for n in('fwt_if','switch_tqe'):t+='CFLAGS_source/platform/topaz/'+n+'.o += -DOPENMITRASTAR_NATIVE_IPV6_PROVIDER=1\n'
 t+='CFLAGS_source/platform/ruby/iputil.o += -DOPENMITRASTAR_NATIVE_IPV6_PROVIDER=1\n';k.write_text(t,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_NATIVE_IPV6_PROVIDER_FLAG_SCOPE',parent=str(a.parent),changed_sources={rel:sha(f),'Kbuild':sha(k)},kbuild_sha256=sha(k));proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed_sources':proof['changed_sources']},indent=2))
if __name__=='__main__':main()
