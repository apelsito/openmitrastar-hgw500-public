"""Measure compression of standalone2g root/initramfs before firmware rebuild."""
from pathlib import Path
import hashlib,json,lzma,shutil,subprocess,os
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
WORK=Path('/workspace/user-home/Desktop/MitraStar')
OUT=BASE/'radio73-2g-doom-fit-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 os.umask(0o077);OUT.mkdir(mode=0o700);root=OUT/'root'
 shutil.copytree(BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z/initramfs/root',root,symlinks=True)
 shutil.rmtree(root/'www/Doom')
 shutil.copytree(WORK/'outputs/doom/xzwasm-runtime-delivery-20261023-v3/www/Doom',root/'www/Doom')
 for block in [131072,1048576]:
  image=OUT/('2g-doom-'+str(block)+'.squashfs')
  with (OUT/('pack-'+str(block)+'.log')).open('xb') as log:
   subprocess.run(['mksquashfs',str(root),str(image),'-noappend','-all-root','-no-progress','-comp','xz','-b',str(block),'-processors','2','-mkfs-time','1792365298','-all-time','1792365298'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
  print(json.dumps({'block':block,'rootfs_bytes':image.stat().st_size,'sha256':sha(image),'fits_root_window':image.stat().st_size<=0x460000}))
 # Kernel actually builds gzip initramfs, then RAS can LZMA entire raw kernel.
 # Measuring root alone bounds next action, does not prove final RAS fit.
 raw=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z/kernel-a.raw'
 data=raw.read_bytes();compressed=lzma.compress(data,format=lzma.FORMAT_ALONE,preset=9)
 compressed=compressed[:5]+len(data).to_bytes(8,'little')+compressed[13:]
 (OUT/'parent-complete.lzma').write_bytes(compressed)
 print(json.dumps({'parent_full_Doom_ras_lzma_bytes':8192+len(compressed),'fits_prefix':8192+len(compressed)<=0x5e0000,'note':'Parent includes originalZIP/sources; compact game not yet kernel-packaged.'}))
if __name__=='__main__':main()
