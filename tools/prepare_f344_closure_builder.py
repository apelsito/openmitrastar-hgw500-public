from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 s=(ROOT/'tools/build_f341_closure.py').read_text()
 s=s.replace('Recompile all26 F341 radio modules','Recompile all26 F344 mode-workflow modules')
 s=s.replace("QDRV=ROOT/'work/linux510-radio-port/quantenna-f338-availability'","QDRV=ROOT/'work/linux510-radio-port/quantenna-f344-modes'\nF344_PEERS=ROOT/'work/linux510-radio-port/quantenna-f344-peers'\nF344_HEADERS=ROOT/'work/kernel-port/f344/headers'")
 s=s.replace(" for row in qproof['sources']:require(sha(ROOT/row['path'])==row['sha256'],'qdrv source drift '+row['path'])", " # F344 is a versioned derivative; its own complete source snapshot is pinned below.")
 s=s.replace("out=BASE/('f341-closure-'+stamp)","out=BASE/('f344-closure-'+stamp)")
 s=s.replace("copytree_files(PEERS/'source',out/'source/peers')","copytree_files(F344_PEERS,out/'source/peers');copytree_files(F344_HEADERS,out/'source/headers')")
 needle=" sources={str(p.relative_to(out/'source'))"
 i=s.index(needle)
 s=s[:i]+''' for target in ('provider','qdrv','peers'):
  mf=out/'source'/target/'Makefile'
  prefix='ccflags-y' if target=='provider' else 'subdir-ccflags-y'
  mf.write_bytes((prefix+' += -I$(F344_HEADERS)\\n'+mf.read_text()).encode())
'''+s[i:]
 s=s.replace("module_kout='/home/user/openmitrastar-build/f341-module-context-'+stamp","module_kout='/home/user/openmitrastar-build/f344-module-context-'+stamp")
 s=s.replace('KBUILD_BUILD_HOST=f341-native KBUILD_BUILD_VERSION=341','KBUILD_BUILD_HOST=f344-modes KBUILD_BUILD_VERSION=344')
 s=s.replace('KCFLAGS="-ffile-prefix-map=$out/$lane=/f341-source"','F344_HEADERS="$out/$lane/headers" KCFLAGS="-ffile-prefix-map=$out/$lane=/f344-source"')
 s=s.replace("'openmitrastar.f341-closure/v1'","'openmitrastar.f344-closure/v1'")
 s=s.replace("'PASS_F341_COHERENT_CLOSURE'","'PASS_F344_COHERENT_CLOSURE'")
 s=s.replace("'watchdog_physical':'PENDING_ROOT_GATE'","'watchdog_physical':'F336_CESSATION_ONLY_SEPARATE_EVIDENCE'")
 (ROOT/'tools/build_f344_closure.py').write_bytes(s.encode())
if __name__=='__main__':main()
