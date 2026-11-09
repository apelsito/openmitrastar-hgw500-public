"""Measure full preserved Doom/root with qualified current web/SSH and5GHzR22."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,os
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OUT=BASE/'complete-rootfs-fit-v45'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700);root=OUT/'root'
 original=BASE/'radioeth73-doom-complete-size-v1/root'
 shutil.copytree(original,root,symlinks=True)
 updates=[
  (BASE/'uhttpd73-wasm-mime-v1/a/uhttpd','usr/sbin/uhttpd','43a0fea8072cfd725ae5803bc7fc4bfd94bb734d8a321b8490945d9563c62d1c'),
  (BASE/'dropbear73-pie-qualified-v1/dropbearmulti-a','usr/sbin/dropbearmulti','23026d9cabd53cab1d9b7c5a78ef5c5be0e6842b7a81a1696af9949bf5974da0')]
 for src,dst,pin in updates:
  assert sha(src)==pin;shutil.copyfile(src,root/dst);(root/dst).chmod(0o755)
 # Debug-only removal preserves allocatedcode/data, module symbols/relocations
 # and all user-visible files. No program, applet, locale or game data removed.
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 stripped=[]
 for file in root.rglob('*'):
  if not file.is_file() or file.is_symlink() or file.open('rb').read(4)!=b'\x7fELF':continue
  before=file.stat().st_size
  subprocess.run([tc+'strip','--strip-debug',str(file)],check=True)
  stripped.append({'path':file.relative_to(root).as_posix(),'before':before,'after':file.stat().st_size})
 # Add every native5GHzR22 module for capacity measurement. These modules are
 # not ABI-compatible with this root's Realtek/context and are NOT executable
 # firmware; full co-build and root services remain required.
 native=Path('/home/rea/linux73-typed-sram-dma-r22-native-pair-r1/a')
 receipt=json.loads((native.parent/'result.json').read_text());assert receipt['status']=='PASS_PAIRED_REAL_LINUX73_74C_22MODULES_IDENTICAL_TYPED_SRAM'
 destination=root/'modules/radio5g-r22-capacity-only';destination.mkdir()
 native_rows=[]
 for file in sorted(native.glob('*.ko')):
  pin=receipt['lanes'][0]['modules'][file.name]['sha256'];assert sha(file)==pin
  shutil.copyfile(file,destination/file.name)
  subprocess.run([tc+'strip','--strip-debug',str(destination/file.name)],check=True)
  native_rows.append({'name':file.name,'bytes':(destination/file.name).stat().st_size,'source_sha256':pin})
 assert len(native_rows)==22
 private=['server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow']
 inventory=[{'path':f.relative_to(root).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(root.rglob('*')) if f.is_file() and not f.is_symlink() and not any(t in f.as_posix() for t in private)]
 (OUT/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
 rows=[]
 for block in [131072,1048576]:
  image=OUT/('complete-xz-'+str(block)+'.squashfs')
  with (OUT/('pack-'+str(block)+'.log')).open('xb') as log:
   subprocess.run(['mksquashfs',str(root),str(image),'-noappend','-all-root','-no-progress','-comp','xz','-b',str(block),'-processors','2','-mkfs-time','1792365298','-all-time','1792365298'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
  rows.append({'block':block,'rootfs_bytes':image.stat().st_size,'sha256':sha(image),'historical_window':0x460000,'rootfs_overflow':max(0,image.stat().st_size-0x460000),'total_prefix':0x5e0000,'rootfs_alone_exceeds_entire_prefix':image.stat().st_size>0x5e0000})
 game=[r for r in inventory if r['path'].startswith('www/Doom/')]
 assert len(game)==11 and any(x['path'].endswith('doom19s.zip') for x in game)
 result={'status':'FULL_PRESERVED_GAME_AND_NATIVE_MODULE_CAPACITY_MEASUREMENT_NOT_FIRMWARE','hardware_accessed':False,'firmware_eligible':False,'game_files':len(game),'game_raw_bytes':sum(x['bytes']for x in game),'native_modules':native_rows,'stripped_debug_only':stripped,'rows':rows,'limits':['Capacity only: modules need full commonkernelABI rebuild and persistentservices/storage/LED/recovery.','All originalgame/archive/source/music/licenses retained; no protected/store capacity borrowed.','Moving rootfs alone cannot solve fit if it exceeds entire prefix.']}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'game_files':len(game),'native_modules':len(native_rows),'rows':rows},indent=2))
if __name__=='__main__':main()
