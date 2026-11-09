"""Publish only sanitized radio73 source/recipes and local build receipts.
Copies no per-unit DT, firmware, private key, binary module or rootfs.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert not a.output.exists();a.output.mkdir(parents=True)
 resolution=json.loads((a.candidate/'RESOLUTION.json').read_text())
 for row in resolution['files']:
  f=a.candidate/row['path'];assert f.stat().st_size==row['bytes'] and sha(f)==row['sha256']
  relative=Path(row['path']).relative_to('overlay');assert sha(a.source/relative)==row['sha256'],relative
  target=a.output/'overlay'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
 platform=['drivers/pci/controller/pcie-qtn-topaz.c','drivers/pci/controller/Makefile','arch/arc/plat-topaz-basic/Kconfig','arch/arc/kernel/intc-compact.c','arch/arc/boot/dts/topaz_mitrastar_eth73.dts','include/linux/soc/qtn/topaz-ethernet.h']
 for relative in platform:
  target=a.output/'overlay'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((a.source/relative).read_bytes())
 dt=(a.output/'overlay/arch/arc/boot/dts/topaz_mitrastar_eth73.dts').read_text()
 assert 'local-mac-address' not in dt and 'status = "disabled";' in dt
 # Emit reviewed final decisions rather than the failed merge history.
 decisions=['Keep upstream ASPM quirks and HGW tracing/DMA helpers.',
  'Use upstream rtl_init_sw_leds API with HGW stage logging.',
  'Use upstream fail6 unwind and HGW registration-state cleanup guard.',
  'Retain HGW TX ownership diagnostics without upstream-removed unused stop counter.',
  'Use Linux7.3 linux/unaligned.h in pci.c, efuse.c and trx.c.',
  'Read station HT capabilities via sta->deflink.ht_cap.']
 (a.output/'SOURCE_RESOLUTION.json').write_text(json.dumps({'schema':'openmitrastar.radio73-final-decisions/v1','decisions':decisions,'original_resolution_sha256':sha(a.candidate/'RESOLUTION.json')},indent=2)+'\n')
 qualification=json.loads(a.qualification.read_text());assert qualification['status']=='PASS_PAIRED_KERNEL_MODULE_ARC_IMPORTS'
 for row in qualification['files']:
  file=a.build/row['path'];assert file.stat().st_size==row['bytes'] and sha(file)==row['sha256'],row['path']
 (a.output/'OFFLINE_RESULT.json').write_bytes(a.qualification.read_bytes())
 config=(a.build/'.config').read_text()
 assert sha(a.build/'.config')==qualification['config_sha256']
 config=re.sub(r'CONFIG_INITRAMFS_SOURCE="[^"]*"','CONFIG_INITRAMFS_SOURCE="@INITRAMFS_LIST@"',config)
 (a.output/'radio73.config.template').write_text(config,newline='\n')
 for name in ['rebuild.py']:
  shutil.copyfile(HERE/name,a.output/name)
 files=[{'path':f.relative_to(a.output).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(a.output.rglob('*')) if f.is_file()]
 (a.output/'SOURCE_MANIFEST.json').write_text(json.dumps({'schema':'openmitrastar.radio73-source-package/v1','upstream_commit':'c03c1a14507dfaf8b856c2608f9ac216021fc222','hardware_accessed':False,'role':'OFFLINE_REPRODUCIBLE_SOURCE_NO_PHYSICAL_RADIO_ACCEPTANCE','files':files},indent=2)+'\n')
 print(json.dumps({'source_files':len(resolution['files']),'platform_files':len(platform),'manifest_files':len(files),'output':str(a.output)}))
if __name__=='__main__':main()
