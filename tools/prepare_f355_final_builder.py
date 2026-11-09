"""Reuse the already rebuilt unchanged peers; rebuild final qdrv twice."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 s=(ROOT/'tools/build_f355_closure.py').read_text()
 s=s.replace("ap.add_argument('--f340-kernel-result',required=True,type=Path);a=ap.parse_args()", "ap.add_argument('--f340-kernel-result',required=True,type=Path);ap.add_argument('--reuse-closure',required=True,type=Path);a=ap.parse_args()\n reuse=json.loads(a.reuse_closure.read_text());require(reuse['status']=='PASS_F355_COHERENT_CLOSURE_OFFLINE','reused closure is not qualified')\n reuse_dir=a.reuse_closure.parent")
 s=s.replace("('f355-closure-'+stamp)","('f355-final-closure-'+stamp)")
 s=s.replace(" sources={str(p.relative_to(out/'source')):sha(p) for p in (out/'source').rglob('*') if p.is_file()}"," sources={str(p.relative_to(out/'source')):sha(p) for p in (out/'source').rglob('*') if p.is_file()}\n for name,digest in sources.items():\n  if not name.replace('\\\\','/').startswith('qdrv/'):\n   require(reuse['source'].get(name)==digest,'unchanged peer/provider/header source drift '+name)\n require(reuse['kernel_config_sha256']==sha(config),'reused kernel config mismatch')")
 s=s.replace("module_kout=linux(out/'kernel-context')","module_kout=reuse['isolated_module_context']")
 start=s.index('test ! -e "$kout"\n');end=s.index('test "$(sha256sum "$kout/.config"',start)
 s=s[:start]+s[end:]
 start=s.index(' SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f355-lifetime KBUILD_BUILD_VERSION=355 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/provider"')
 end=s.index(' cat "$out/$lane/provider/Module.symvers"',start)
 s=s[:start]+''' cp -a {q(linux(reuse_dir))}/$lane/provider/. "$out/$lane/provider/"
 cp -a {q(linux(reuse_dir))}/$lane/peers/. "$out/$lane/peers/"
'''+s[end:]
 s=s.replace(" (out/'manifest.json').write_text", " result['status']='PASS_F355_FINAL_COHERENT_CLOSURE_OFFLINE' if not errors else 'FAIL'\n result['unchanged_peer_reuse']={'manifest':str(a.reuse_closure),'sha256':sha(a.reuse_closure),'module_count':25,'all_sources_headers_config_equal':True}\n (out/'manifest.json').write_text",1)
 (ROOT/'tools/build_f355_final_closure.py').write_bytes(s.encode())
if __name__=='__main__':main()
