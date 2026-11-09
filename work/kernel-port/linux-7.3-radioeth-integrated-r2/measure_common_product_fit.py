"""Measure coherent common radio root and kernel; not an executable firmware.

All modules use one actual common ABI. Includes the three 5GHz carriers and
compact Doom. Keeps private root/keys local; exports only non-sensitive receipt.
"""
from pathlib import Path
import hashlib,json,lzma,os,shutil,subprocess
HERE=Path(__file__).resolve().parent
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
COMMON=BASE/'radio73-common-r3-context-v1'
NATIVE=BASE/'radio73-common-r3-r26-native-v1'
R2=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z'
GAME=WORKSPACE/'outputs/doom/xzwasm-runtime-delivery-20261023-v3'
OUT=BASE/'radio73-common-product-fit-v1'
PRIVATE=('server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def main():
 require(not OUT.exists(),'Immutable output exists')
 c=json.loads((COMMON/'result.json').read_text());n=json.loads((NATIVE/'result.json').read_text())
 require(c['status']=='PASS_PAIRED_COMMON_KERNEL_REALTEK_ETHERNET_R24_22_NATIVE_ABI','Common kernel unqualified')
 require(n['status']=='PASS_R26_NATIVE_PAIR_ON_THIS_COMMON_KERNEL','R26/common native unqualified')
 native=json.loads((NATIVE/'pair/result.json').read_text())
 os.umask(0o077);OUT.mkdir(mode=0o700);root=OUT/'root'
 shutil.copytree(R2/'initramfs/root',root,symlinks=True)
 # Remove inherited module copies only in this new composition. Every original
 # remains unchanged; there is exactly one package per common .ko in the root.
 shutil.rmtree(root/'modules');(root/'qtn-topaz-emac-eth73.ko').unlink()
 moddir=root/'lib/modules'/c['release'];moddir.mkdir(parents=True)
 sources=sorted((COMMON/'a/kernel').rglob('*.ko'))+sorted((NATIVE/'pair/a').glob('*.ko'))+[COMMON/'a/emac/qtn-topaz-emac-eth73.ko']
 require(len(sources)==49,'Common full module count differs')
 records=[]
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 for src in sources:
  name=src.name;dest=moddir/name;require(not dest.exists(),'Duplicate module basename')
  if src.is_relative_to(NATIVE/'pair/a'):
   pin=native['lanes'][0]['modules'][name]['sha256']
  else:
   pin=c['lanes'][0]['modules'][src.relative_to(COMMON/'a').as_posix()]['sha256']
  require(sha(src)==pin,'Common module pin changed')
  shutil.copyfile(src,dest)
  before=dest.stat().st_size;subprocess.run([tc+'strip','--strip-debug',str(dest)],check=True)
  records.append({'name':name,'source_sha256':pin,'bytes_before':before,'bytes_after':dest.stat().st_size,'sha256':sha(dest)})
 # Compact runtime with downloadable sources supplied in the sidecar delivery.
 old_game=root/'www/Doom';shutil.rmtree(old_game)
 package=json.loads((GAME/'package-result.json').read_text())
 require(package['playable_set_bytes']==1963602,'Compact game delivery changed')
 shutil.copytree(GAME/'www/Doom',old_game)
 for row in package['inventory']:require(sha(old_game/row['name'])==row['sha256'],'Compact game pin changed')
 carriers=[('qtn_driver.qtn_ruby.0.bin','71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4'),('auc_driver.nomu.0.bin','c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6'),('rdsp_driver.0.bin','87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd')]
 fw=root/'etc/firmware';fw.mkdir(exist_ok=True);fwrows=[]
 for name,pin in carriers:
  src=WORKSPACE/'work/hgw500-rootfs-live/squashfs-root/etc/firmware'/name
  require(sha(src)==pin,'Exact 5GHz carrier changed')
  shutil.copyfile(src,fw/name);(fw/name).chmod(0o644)
  fwrows.append({'name':name,'bytes':src.stat().st_size,'sha256':pin})
 # Runtime hints are deliberately not an executable init integration.
 (root/'etc/openmitrastar/release').write_text('OPENMITRASTAR_PRODUCT_VERSION=lyoko-linux73-common-product-fit-only\nOPENMITRASTAR_BUILD_ID=common-r3-r26-size-v1\n')
 rows=[]
 for block in [131072,1048576]:
  image=OUT/('root-xz-'+str(block)+'.squashfs')
  with (OUT/('pack-'+str(block)+'.log')).open('xb') as log:
   subprocess.run(['mksquashfs',str(root),str(image),'-noappend','-all-root','-no-progress','-comp','xz','-b',str(block),'-processors','2','-mkfs-time','1792365298','-all-time','1792365298'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
  rows.append({'block_bytes':block,'rootfs_bytes':image.stat().st_size,'sha256':sha(image),'historical_root_window':0x460000,'overflow_historical_root':max(0,image.stat().st_size-0x460000),'fits_historical_root':image.stat().st_size<=0x460000})
 raw=OUT/'kernel-no-initramfs.raw'
 subprocess.run([tc+'objcopy','-O','binary',str(COMMON/'a/kernel/vmlinux'),str(raw)],check=True)
 data=raw.read_bytes();compressed=lzma.compress(data,format=lzma.FORMAT_ALONE,preset=9)
 # Bootbase requires exact uncompressed size instead of Python's all-ones field.
 compressed=compressed[:5]+len(data).to_bytes(8,'little')+compressed[13:]
 require(lzma.decompress(compressed,format=lzma.FORMAT_ALONE)==data,'Kernel LZMA roundtrip failed')
 kxz=OUT/'kernel-no-initramfs.lzma';kxz.write_bytes(compressed)
 layout=[]
 for row in rows:
  dynamic_offset=(8192+len(compressed)+0x1ffff)&~0x1ffff
  layout.append({'block_bytes':row['block_bytes'],'compressed_kernel_plus_ras_bytes':8192+len(compressed),'historical_root_offset':0x180000,'kernel_fits_before_historical_root':8192+len(compressed)<=0x180000,'historical_prefix_total':0x180000+row['rootfs_bytes'],'historical_prefix_overflow':max(0,0x180000+row['rootfs_bytes']-0x5e0000),'alternative_aligned_root_offset':dynamic_offset,'alternative_prefix_total':dynamic_offset+row['rootfs_bytes'],'alternative_prefix_overflow':max(0,dynamic_offset+row['rootfs_bytes']-0x5e0000),'note':'Layout arithmetic only; no Bootbase/root mounting contract for changed offset.'})
 inventory=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink() and not any(k in p.relative_to(root).as_posix() for k in PRIVATE)]
 r={'status':'PASS_COHERENT_COMMON_ABI_ROOT_AND_KERNEL_CAPACITY_MEASUREMENT_NOT_FIRMWARE','hardware_accessed':False,'firmware_eligible':False,'module_count':49,'native_revision':'R26','common_kernel_release':c['release'],'compact_game_bytes':package['playable_set_bytes'],'source_and_original_game_outside_flash':True,'three_5g_carriers':fwrows,'module_records':records,'rootfs_measurements':rows,'kernel_raw_bytes':len(data),'kernel_raw_sha256':sha(raw),'kernel_lzma_bytes':len(compressed),'kernel_lzma_sha256':sha(kxz),'layout_arithmetic':layout,'inventory_non_sensitive':inventory,'limits':['Capacity composition has common-ABI modules, but inherited diagnostic PID1 still uses parent module paths. It cannot be flashed or booted as this root.','Persistent init/storage/LED/runtime config transactions/recovery remain incomplete.','No kernel/DT/MTD mount contract or exact flash image generated.','Protected partitions and 0x1c0000 store tail are excluded from available space.','SRAM registration/5GHz client traffic/soak remain unproved.']}
 (OUT/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 public=WORKSPACE/'outputs/rea/radio73-common-product-fit-20261023-v1';public.mkdir()
 (public/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r[k] for k in ['status','module_count','compact_game_bytes','rootfs_measurements','kernel_lzma_bytes','layout_arithmetic']},indent=2))
if __name__=='__main__':main()
