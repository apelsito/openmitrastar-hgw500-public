"""Compare same SquashFS settings, export only public evaluation assets."""
from pathlib import Path
import argparse,json,shutil,subprocess,hashlib
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
WINDOWS=Path('/workspace/user-home/Desktop/MitraStar')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
 if a.output.exists():raise RuntimeError('Immutable output exists')
 a.output.mkdir(mode=0o700)
 result=json.loads((a.candidate/'result.json').read_text())
 old=BASE/'radioeth73-doom-complete-size-v1/root/www/Doom'
 new=a.candidate/'www/Doom'
 sets=[('old-eleven',old),('xz-full-preserved',new)]
 playable=a.output/'playable';playable.mkdir()
 for row in result['inventory']:
  if row['runtime_set']:shutil.copyfile(new/row['name'],playable/row['name'])
 sets.append(('xz-playable',playable))
 rows=[]
 for name,root in sets:
  image=a.output/(name+'.squashfs')
  with (a.output/(name+'.log')).open('xb') as log:
   subprocess.run(['mksquashfs',str(root),str(image),'-noappend','-all-root','-no-progress','-comp','xz','-b','1048576','-processors','2','-mkfs-time','1792365298','-all-time','1792365298'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
  rows.append({'name':name,'file_bytes':sum(p.stat().st_size for p in root.iterdir()),'squashfs_bytes':image.stat().st_size,'sha256':sha(image)})
 export=WINDOWS/'outputs/doom/xzwasm-candidate-20261023-v1'
 if export.exists():raise RuntimeError('Immutable public export exists')
 export.mkdir(parents=True)
 shutil.copytree(new,export/'www/Doom')
 shutil.copyfile(a.candidate/'result.json',export/'package-result.json')
 comparison={'status':'PASS_ISOLATED_GAME_SQUASHFS_MEASUREMENT_NOT_FIRMWARE','hardware_accessed':False,'rows':rows,'note':'Same host compressor/settings. Final rootfs blocks/kernel/drivers fit remains separate.'}
 (a.output/'result.json').write_text(json.dumps(comparison,indent=2)+'\n')
 (export/'size-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
 print(json.dumps(comparison,indent=2))
if __name__=='__main__':main()
