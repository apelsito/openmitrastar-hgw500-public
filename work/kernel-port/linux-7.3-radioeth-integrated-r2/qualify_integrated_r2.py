"""Read-only independent ELF/CPIO/RAS contract qualification; outputs a new receipt."""
from pathlib import Path
import argparse,dataclasses,hashlib,json,stat,struct,sys,zlib
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
sys.path.insert(0,str(WORKSPACE/'tools'))
from bootbase_contract_emulator import validate_bootbase_slot
PRIVATE=('server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow')
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(data):return hashlib.sha256(data).hexdigest()
def window(data,start,size):
 require(0<=start<=start+size<=len(data),'Truncated input range');return data[start:start+size]
def examine(build,row):
 elf=(build/'vmlinux').read_bytes()
 h=struct.unpack_from('<16sHHIIIIIHHHHHH',elf)
 require(h[0][:7]==b'\x7fELF\x01\x01\x01' and h[1:4]==(2,93,1),'Not ARC32 executable')
 require(h[4]==int(row['entry'],16) and h[7]==0x403 and h[11]==40,'ELF ABI/entry mismatch')
 sections=[struct.unpack('<10I',window(elf,h[6]+i*40,40)) for i in range(h[12])]
 strings=sections[h[13]];names=window(elf,strings[4],strings[5])
 allocated=[]
 for s in sections:
  end=names.find(b'\0',s[0]);require(end>=0,'Invalid section name')
  name=names[s[0]:end].decode('ascii')
  if s[2]&2 and s[5]:
   require(0x8493a000<=s[3]<s[3]+s[5]<=0x88000000,'Allocated section exceeds DDR')
   allocated.append((name,s))
 stored=sorted(((name,s) for name,s in allocated if s[1]!=8),key=lambda item:item[1][3])
 require(min(s[3] for _,s in stored)==0x8493a000,'ELF load differs')
 top=max(s[3]+s[5] for _,s in stored);raw=bytearray(top-0x8493a000);last=0x8493a000
 for _,s in stored:
  require(s[3]>=last,'Overlapping ELF sections')
  raw[s[3]-0x8493a000:s[3]-0x8493a000+s[5]]=window(elf,s[4],s[5]);last=s[3]+s[5]
 require(sha(raw)==row['raw_sha256'],'Reconstructed ELF payload differs')
 ramfs=next(s for name,s in stored if name=='.init.ramfs')
 decoder=zlib.decompressobj(31);cpio=decoder.decompress(window(elf,ramfs[4],ramfs[5]),32*1024*1024)+decoder.flush()
 require(decoder.eof and len(cpio)<32*1024*1024,'Initramfs gzip invalid or oversized')
 cursor=0;entries={}
 while cursor+110<=len(cpio):
  header=window(cpio,cursor,110);require(header[:6]==b'070701','Not newc archive')
  v=[int(header[6+i*8:14+i*8],16) for i in range(13)]
  require(0<v[11]<4096,'Invalid CPIO name size')
  name=window(cpio,cursor+110,v[11]);require(name[-1:]==b'\0','Unterminated CPIO name')
  name=name[:-1].decode('utf8');require(name not in entries,'Duplicate CPIO entry')
  start=(cursor+110+v[11]+3)&~3;body=window(cpio,start,v[6])
  entries[name]={'mode':v[1],'uid':v[2],'gid':v[3],'mtime':v[5],'data':body,'major':v[9],'minor':v[10]}
  cursor=(start+v[6]+3)&~3
  if name=='TRAILER!!!':break
 require('TRAILER!!!' in entries,'No CPIO trailer')
 root=build.parent/'initramfs/root'
 for p in root.rglob('*'):
  name=p.relative_to(root).as_posix();item=entries.get(name)
  require(item is not None,'Root entry absent from embedded CPIO')
  require(item['uid']==item['gid']==0,'CPIO owner differs')
  if p.is_symlink():
   # Linux gen_init_cpio emits a terminating NUL in its symlink body.
   expected=str(p.readlink()).encode()
   require(stat.S_ISLNK(item['mode']) and item['data'] in (expected,expected+b'\0'),'Symlink differs: '+name)
  elif p.is_file():
   require(stat.S_ISREG(item['mode']) and item['data']==p.read_bytes(),'Embedded file content differs')
   require(item['mode']&0o777==p.stat().st_mode&0o777,'Embedded file mode differs')
   if any(k in name for k in PRIVATE):require(item['mode']&0o777==0o600,'Embedded private mode differs')
 require(entries['bin/id']['data'] in (b'busybox',b'busybox\0'),'BusyBox id link absent')
 credential=entries['run/openmitrastar/secrets/web.password.sha256']['data']
 require(len(credential)==65 and credential[-1:]==b'\n' and b'\r' not in credential,'Credential LF contract failed')
 console=entries['dev/console'];require(stat.S_ISCHR(console['mode']) and (console['major'],console['minor'])==(5,1),'Console device contract differs')
 game=[name for name in entries if name.startswith('www/Doom/') and stat.S_ISREG(entries[name]['mode'])]
 require(len(game)==11,'Embedded game asset count differs')
 allocated_end=max(s[3]+s[5] for _,s in allocated)
 # _end includes final ARC page alignment, not necessarily another section.
 require((allocated_end+8191)&~8191==int(row['end'],16),'ELF RAM end differs')
 data=(build.parent/('radioeth73-integrated-r2-'+row['lane']+'-RAM-ONLY.ras.bin')).read_bytes()
 require(sha(data)==row['image_sha256'] and data[8192:]==raw,'RAS identity/payload mismatch')
 ram_contract=validate_bootbase_slot('RAM staging only',data,0x1000000)
 require(ram_contract.accepted_by_contract,'Bootbase RAM RAS contract failed')
 prefix_contract=validate_bootbase_slot('Preserved flash prefix',data,0x5e0000)
 require(not prefix_contract.accepted_by_contract,'Unexpected flash prefix fit; reassess classification')
 staging_end=0x83002000+len(raw);load=0x8493a000
 require(staging_end<0x84000000<load<int(row['entry'],16)<load+len(raw)<0x88000000,'Bootbase staging/load intervals overlap')
 return {'lane':row['lane'],'ELF_ABI':'PASS','ELF_raw_reconstruction':'PASS','CPIO_bytes':len(cpio),'CPIO_entries':len(entries),'CPIO_exact_root_and_private_modes':'PASS','game_files':len(game),'RAM_RAS_contract':dataclasses.asdict(ram_contract),'flash_prefix_contract':dataclasses.asdict(prefix_contract),'staging_interval':[hex(0x83002000),hex(staging_end)],'load_interval':[hex(load),hex(load+len(raw))],'physical_boot':'UNRUN'}
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--build',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args();require(not args.output.exists(),'Immutable output exists')
 report=json.loads((args.build/'result.json').read_text());require(report['status']=='PASS_PAIRED_RAM_INTEGRATION_PHYSICAL_UNRUN','Build not qualified')
 lanes=[examine(args.build/row['lane'],row) for row in report['lanes']]
 args.output.mkdir(mode=0o700)
 result={'status':'PASS_INDEPENDENT_ELF_CPIO_BOOTBASE_RAM_CONTRACTS','hardware_accessed':False,'flash_go_no_go':'NO_GO_RAM_ONLY','builder_receipt_sha256':sha((args.build/'result.json').read_bytes()),'qualifier_sha256':sha(Path(__file__).read_bytes()),'lanes':lanes,'limits':['Static validation only; boot/radio/TLS/game/recovery not run on this image.','Flash prefix rejection is expected; store/protected partitions cannot be borrowed.']}
 (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'cpio_entries':[x['CPIO_entries'] for x in lanes],'flash':'NO_GO_RAM_ONLY'}))
if __name__=='__main__':main()
