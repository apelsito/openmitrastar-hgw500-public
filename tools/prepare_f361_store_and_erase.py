"""Bind the physically verified journal and audit the exact Bootbase erase end."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,lzma,os,struct
from init_lyoko_device_host_key import restrict_acl
import f358_install_contract as c
ROOT=c.ROOT
F360=Path('/workspace/OpenMitraStar/f360-evidence/f360-save-20260921T183947Z-b2328b27/result.json')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,name):
 if not ok:raise ValueError(name)
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f361-preserve-store-'+stamp);out.mkdir(exist_ok=False)
 require(sha(F360)=='00cb0a2b9744983dd28f11591408157ece9fd4158aa6a575a676c478ab3590b3','physical_result_binding');record=json.loads(F360.read_text(encoding='ascii'));returned=record['return'];snapshot=returned['store_snapshot']
 require(record['status']=='PASS_F360_CONFIG_SAVED_AND_PERSISTED' and returned['persisted_expected_record'] is True and returned['readback_error'] is None and returned['platform']['checks']==27,'physical_save_required')
 pieces=[];captures=[]
 for expected_name in ('dc','dd'):
  item=next(p for p in snapshot['parts'] if p['name']==expected_name);path=Path(item['path']);require(path.stat().st_size==65536 and sha(path)==item['sha256'],'physical_capture_hash');pieces.append(path.read_bytes());captures.append(item)
 data=b''.join(pieces)+b'\xff'*(0x1c0000-0x20000)
 require(hashlib.sha256(data).hexdigest()==snapshot['store_sha256'],'store_reconstruction')
 private=c.DEVICE.parent/'analysis'/('f361-preserved-journal-'+stamp);private.mkdir(parents=True,exist_ok=False);restrict_acl(private,directory=True);backup=private/'store.bin'
 with backup.open('xb') as stream:require(stream.write(data)==len(data),'backup_short_write')
 restrict_acl(backup,directory=False);require(sha(backup)==snapshot['store_sha256'],'backup_readback')
 store=dict(path=str(backup),bytes=len(data),sha256=sha(backup),crc32=c.crc(data),physical_result=dict(path=str(F360),sha256=sha(F360)),captured_parts=captures,reconstructed_tail='FF tail verified by the physically observed full-store SHA256',raw_full_capture_claimed=False)
 binary=ROOT/'work/bootbase-decoded.bin';disasm=ROOT/'work/bootbase-decoded.disasm.txt';rom=ROOT/'outputs/flash-backups/f159-physical-new-dump-20260831T2359/current-unit/hgw500_mtdblock0.bin';blob=binary.read_bytes();text=disasm.read_text(encoding='ascii');base=0x88014000
 checks={}
 def check(name,condition):checks[name]=bool(condition);require(condition,name)
 reference=c.original.validate_proofs()[2];prior=json.loads(Path(reference['path']).read_text(encoding='ascii'))
 check('exact_bootbase',sha(binary)==prior['sources'][str(binary)])
 check('exact_disassembly',sha(disasm)==prior['sources'][str(disasm)])
 check('decoded_from_preserved_rom',lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(rom.read_bytes()[0xf34:])==blob)
 pointer,ident,sector,count,flags=struct.unpack_from('<IIIHH',blob,0x88036130-base);name=blob[pointer-base:blob.index(0,pointer-base)].decode('ascii')
 check('descriptor_common_id_geometry',ident==0xc22018 and sector==0x10000 and count==256 and flags==0)
 def literal(address):offset=address-base;return blob[offset:blob.index(0,offset)].decode('ascii')
 check('literal_erase_dispatch',literal(0x88033d88)=='erase')
 for address,fragment in [('880234a0','ld_s\tr0,[r15,0x8]'),('880234b0','ld_s\tr0,[r15,0xc]'),('880234ec',';0x88022734'),('880234f0','mov_s\tr1,r13'),('880227a6','add\tr2,r16,r14'),('880227c8','mov_s\tr15,r2'),('880227ca','brne\tr14,0,136'),('88022832','st.di\tr3,[r18]'),('88022840','add_s\tr14,r14,r13'),('88022868','brlo.d\tr14,r15,-88')]:
  line=next(line for line in text.splitlines() if line.startswith(address+':'));check('instruction_'+address,fragment in line)
 start,size=0x7e0000,0x5e0000;end=min(start+size,sector*count);addresses=list(range(start,end,sector))
 check('exclusive_end_is_store_start',end==0xdc0000 and len(addresses)==94 and addresses[-1]==0xdb0000 and all(addr+sector<=end for addr in addresses))
 sentinel=bytearray(b'\0'*size+b'COMMITTED_JOURNAL_SENTINEL')
 for address in addresses:offset=address-start;sentinel[offset:offset+sector]=b'\xff'*sector
 check('non_ff_store_sentinel_untouched',sentinel[size:]==b'COMMITTED_JOURNAL_SENTINEL')
 erase=dict(schema='openmitrastar.f361-erase-exclusive-audit/v1',status='PASS_STATIC_EXCLUSIVE_PREFIX_END',hardware_actions=False,checks=checks,offset=start,length=size,end_exclusive=end,sector_bytes=sector,sectors=len(addresses),last_sector=addresses[-1],descriptor_name=name,descriptor_name_is_not_exact_part_identity=True,
  explanation='Dispatcher passes offset and length unchanged; end=start+length is clamped to capacity. brlo.d enters a sector operation only while cursor<end, then increments by descriptor sector size. DC is never entered.',sources={str(p):sha(p) for p in (binary,disasm,rom,Path(__file__))})
 (out/'erase-exclusive.json').write_text(json.dumps(erase,indent=2)+'\n',encoding='ascii');store['erase_audit']={'path':str(out/'erase-exclusive.json'),'sha256':sha(out/'erase-exclusive.json')}
 target=ROOT/'work/kernel-port/versions/f361-installer/store-binding.json';target.parent.mkdir(parents=True,exist_ok=True);require(not target.exists(),'store_binding_already_exists');tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(store,indent=2)+'\n',encoding='ascii');os.replace(tmp,target)
 result=dict(status='PASS_F361_PRESERVED_STORE_AND_ERASE_END',store_binding=str(target),store_sha256=store['sha256'],store_crc32=store['crc32'],erase_audit=store['erase_audit'],hardware_actions=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
