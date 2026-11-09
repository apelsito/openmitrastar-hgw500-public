"""Reuse sealed actual kernel pair with original qualified LZMA encoder."""
from pathlib import Path
import hashlib,json,lzma,os,struct,subprocess,zlib
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
WORK=Path('/workspace/user-home/Desktop/MitraStar')
BUILD=BASE/'radio73-2g-flash-autostart-r1-v2'
OUT=BASE/'radio73-2g-legacy-lzma-v3'
ENC=WORK/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 assert sha(ENC)=='04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18'
 b=json.loads((BUILD/'result.json').read_text());assert b['status']=='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN'
 os.umask(0o077);OUT.mkdir(mode=0o700);rows=[]
 for lane in ['a','b']:
  raw=BUILD/('kernel-'+lane+'.raw');assert sha(raw)==b['lanes'][0]['raw_sha256']
  encoded=OUT/('kernel-'+lane+'.lzma')
  with encoded.open('xb') as f:
   subprocess.run([str(ENC),'--keep','--best',str(raw),'-c'],stdout=f,check=True,timeout=300)
  data=encoded.read_bytes();decoded=lzma.decompress(data,format=lzma.FORMAT_ALONE)
  assert decoded==raw.read_bytes() and int.from_bytes(data[5:13],'little')==len(decoded)
  original=(BUILD/('radio73-2g-doom-autostart-'+lane+'.ras.bin')).read_bytes()
  vals=list(struct.unpack('>7I4B32s',original[:64]));vals[1]=0;vals[3]=len(data);vals[6]=zlib.crc32(data)&0xffffffff
  vals[1]=zlib.crc32(struct.pack('>7I4B32s',*vals))&0xffffffff
  image=struct.pack('>7I4B32s',*vals)+original[64:8192]+data
  p=OUT/('radio73-2g-doom-autostart-'+lane+'.ras.bin');p.write_bytes(image)
  assert len(image)<=0x5e0000,'Legacy encoder no fit'
  rows.append({'lane':lane,'image_bytes':len(image),'image_sha256':sha(p),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','payload_bytes':len(data),'entry':hex(vals[5]),'raw_sha256':sha(raw),'raw_bytes':len(decoded),'LZMA_properties':data[:5].hex(),'LZMA_dict_bytes':int.from_bytes(data[1:5],'little'),'prefix_headroom':0x5e0000-len(image)})
 for key in rows[0]:
  if key!='lane':assert rows[0][key]==rows[1][key]
 result={'status':'PASS_LEGACY_LZMA_PAIR_LINUX_DECODE_WINDOWS_PENDING','kernel_build':str(BUILD),'kernel_build_result_sha256':sha(BUILD/'result.json'),'legacy_encoder_sha256':sha(ENC),'hardware_accessed':False,'physical_boot':'UNRUN','flash_writes':0,'bootenv_writes':0,'lanes':rows}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 private=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radio73-2g-doom-autostart-legacy-20261023-v3')
 private.mkdir(mode=0o700)
 (private/'radio73-2g-doom-autostart.ras.bin').write_bytes((OUT/'radio73-2g-doom-autostart-a.ras.bin').read_bytes())
 (private/'ENCODER_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
