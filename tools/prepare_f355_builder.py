"""Derive the F355 coherent builder with all bulky outputs on D:."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 s=(ROOT/'tools/build_f344_closure.py').read_text()
 s=s.replace('Recompile all26 F344 mode-workflow modules','Recompile all26 F355 lifetime modules')
 s=s.replace("QDRV=ROOT/'work/linux510-radio-port/quantenna-f344-modes'","QDRV=ROOT/'work/linux510-radio-port/quantenna-f355-lifetime'")
 s=s.replace("out=BASE/('f344-closure-'+stamp);out.mkdir(parents=True,exist_ok=False)","out=Path('/workspace/OpenMitraStar-build/f355')/('f355-closure-'+stamp);out.mkdir(parents=True,exist_ok=False)")
 s=s.replace("module_kout='/home/user/openmitrastar-build/f344-module-context-'+stamp","module_kout=linux(out/'kernel-context')")
 s=s.replace('KBUILD_BUILD_HOST=f344-modes KBUILD_BUILD_VERSION=344','KBUILD_BUILD_HOST=f355-lifetime KBUILD_BUILD_VERSION=355')
 s=s.replace('/f344-source','/f355-source')
 s=s.replace("'openmitrastar.f344-closure/v1'","'openmitrastar.f355-closure/v1'").replace("'PASS_F344_COHERENT_CLOSURE'","'PASS_F355_COHERENT_CLOSURE_OFFLINE'")
 s=s.replace(" ap=argparse.ArgumentParser", " if shutil.disk_usage(ROOT).free<=500*1024*1024:raise ValueError('C: free space guard')\n ap=argparse.ArgumentParser",1)
 s=s.replace(" (out/'manifest.json').write_text", " if shutil.disk_usage(ROOT).free<=500*1024*1024:errors.append('C: free space guard at completion')\n (out/'manifest.json').write_text",1)
 s=s.replace(" p=subprocess.run(['wsl.exe'", " require('# CONFIG_MODULE_FORCE_UNLOAD is not set' in config.read_text(),'forced module removal must be disabled')\n p=subprocess.run(['wsl.exe'",1)
 (ROOT/'tools/build_f355_closure.py').write_bytes(s.encode())
if __name__=='__main__':main()
