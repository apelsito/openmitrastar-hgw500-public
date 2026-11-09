"""Independent flatCPIO/ELF/LZMA/Bootbase/root qualification; no hardware."""
from pathlib import Path
import argparse,dataclasses,hashlib,json,lzma,stat,struct,sys
WORK=Path('/workspace/user-home/Desktop/MitraStar')
sys.path.insert(0,str(WORK/'tools'))
from bootbase_contract_emulator import validate_bootbase_slot
PRIVATE=('server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow')
def sha(data):return hashlib.sha256(data).hexdigest()
def req(ok,msg):
 if not ok:raise RuntimeError(msg)
def window(data,start,size):
 req(0<=start<=start+size<=len(data),'Truncated ELF/CPIO range')
 return data[start:start+size]
def examine(build,lane):
 data=(build/lane['lane']/'vmlinux').read_bytes()
 req(sha(data)==lane['kernel_sha256'],'ELF hash drift')
 h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
 req(h[0][:7]==b'\x7fELF\x01\x01\x01' and h[1:4]==(2,93,1),'ARC32 executable required')
 req(h[7]==0x403 and h[4]==int(lane['entry'],16),'ARC ABI/entry mismatch')
 sections=[struct.unpack('<10I',window(data,h[6]+i*40,40)) for i in range(h[12])]
 ns=sections[h[13]];names=window(data,ns[4],ns[5])
 alloc=[]
 for s in sections:
  name=names[s[0]:names.find(b'\0',s[0])].decode()
  if s[2]&2 and s[5]:
   req(0x8493a000<=s[3]<s[3]+s[5]<=0x88000000,'Allocated section beyond DDR')
   alloc.append((name,s))
 stored=sorted(((name,s) for name,s in alloc if s[1]!=8),key=lambda row:row[1][3])
 top=max(s[3]+s[5] for _,s in stored);raw=bytearray(top-0x8493a000);last=0x8493a000
 for _,s in stored:
  req(s[3]>=last,'ELF overlap');raw[s[3]-0x8493a000:s[3]-0x8493a000+s[5]]=window(data,s[4],s[5]);last=s[3]+s[5]
 req(sha(raw)==lane['raw_sha256'] and len(raw)==lane['raw_bytes'],'ELF to raw reconstruction mismatch')
 req((max(s[3]+s[5] for _,s in alloc)+8191)&~8191==int(lane['end'],16),'ARC page end differs')
 ramfs=next(s for name,s in alloc if name=='.init.ramfs')
 cpio=window(data,ramfs[4],ramfs[5]);req(cpio[:6]==b'070701','FlatCPIO required')
 cursor=0;entries={}
 while cursor+110<=len(cpio):
  header=window(cpio,cursor,110);req(header[:6]==b'070701','CPIO header magic mismatch')
  v=[int(header[6+i*8:14+i*8],16) for i in range(13)]
  req(0<v[11]<4096,'CPIO name invalid');name=window(cpio,cursor+110,v[11])
  req(name[-1:]==b'\0','CPIO name termination');name=name[:-1].decode()
  req(name not in entries,'Duplicate CPIO name')
  start=(cursor+110+v[11]+3)&~3;body=window(cpio,start,v[6])
  entries[name]={'body':body,'mode':v[1],'uid':v[2],'gid':v[3],'major':v[9],'minor':v[10]}
  cursor=(start+v[6]+3)&~3
  if name=='TRAILER!!!':break
 req('TRAILER!!!' in entries,'CPIO trailer absent')
 root=build/'initramfs/root'
 for p in root.rglob('*'):
  name=p.relative_to(root).as_posix();row=entries.get(name)
  req(row is not None and row['uid']==row['gid']==0,'Embedded root entry/owner differs')
  if p.is_symlink():
   expect=str(p.readlink()).encode()
   req(stat.S_ISLNK(row['mode']) and row['body'] in (expect,expect+b'\0'),'Embedded symlink mismatch')
  elif p.is_file():
   req(stat.S_ISREG(row['mode']) and row['body']==p.read_bytes(),'Embedded file differs: '+name)
   req(row['mode']&0o777==p.stat().st_mode&0o777,'Embedded mode mismatch')
   if any(k in name for k in PRIVATE):req(row['mode']&0o777==0o600,'Private file mode mismatch')
 console=entries['dev/console'];req(stat.S_ISCHR(console['mode']) and (console['major'],console['minor'])==(5,1),'Console device mismatch')
 req(len(entries['run/openmitrastar/secrets/web.password.sha256']['body'])==65,'Credential normalized shape')
 game=[name for name,row in entries.items() if name.startswith('www/Doom/') and stat.S_ISREG(row['mode'])]
 req(len(game)==11 and 'www/Doom/doom1.wad.xz' in game and 'www/Doom/doom19s.zip' not in game,'Compact game delivery differs')
 image=(build/('radio73-2g-doom-autostart-'+lane['lane']+'.ras.bin')).read_bytes()
 req(sha(image)==lane['image_sha256'],'Image hash differs')
 req(lzma.decompress(image[8192:],format=lzma.FORMAT_ALONE)==raw,'Complete LZMA image decoded mismatch')
 req(int.from_bytes(image[8192+5:8192+13],'little')==len(raw),'Bootbase exact LZMA size absent')
 req(int.from_bytes(image[8192+1:8192+5],'little')==32*1024*1024,'Legacy decoder dictionary identity mismatch')
 contract=validate_bootbase_slot('2g flash prefix',image,0x5e0000)
 req(contract.accepted_by_contract,'Bootbase prefix refused')
 req(0x83000000+len(image)<0x84000000<0x8493a000,'Staging/scratch/load overlap')
 return {'lane':lane['lane'],'ELF_raw_exact':True,'flat_cpio_bytes':len(cpio),'flat_cpio_entries':len(entries),'embedded_root_exact':True,'private_modes':True,'compact_game_files':len(game),'LZMA_roundtrip_exact':True,'Bootbase_contract':dataclasses.asdict(contract),'hardware_accessed':False,'physical_boot':'UNRUN'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 req(not a.output.exists(),'Immutable output exists')
 r=json.loads((a.build/'result.json').read_text())
 req(r['status']=='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN','Build receipt unqualified')
 lanes=[examine(a.build,l) for l in r['lanes']]
 a.output.mkdir(mode=0o700)
 result={'status':'PASS_INDEPENDENT_2G_FLATCPIO_LZMA_ENTRY_PREFIX_ROOT_CONTRACTS','build_result_sha256':sha((a.build/'result.json').read_bytes()),'qualifier_sha256':sha(Path(__file__).read_bytes()),'lanes':lanes,'hardware_accessed':False,'flash_go_no_go':'RAM_BOOT_ROLLBACK_READBACK_PENDING'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'cpio_entries':[l['flat_cpio_entries'] for l in lanes]}))
if __name__=='__main__':main()
