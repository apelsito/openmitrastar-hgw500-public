"""Validate captured active.conf via the real normalizer and generate one F342 image. No hardware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,re,shlex,shutil,subprocess,zlib
from init_lyoko_device_host_key import restrict_acl
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
PAYLOAD=DEVICE/'analysis/f360-current-config-20260921T181713Z/active.conf'
F358=DEVICE/'firmware/f358-f340-config-backend-device-bound'
BASE='openmitrastar-linux510-f358-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'crc32':f'{zlib.crc32(b)&0xffffffff:08x}'}
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 assert shutil.disk_usage('C:/').free>500*1024*1024
 data=PAYLOAD.read_bytes();assert len(data)==586 and sha(PAYLOAD)=='073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9'
 assert b'\0' not in data and b'\r' not in data and data.endswith(b'\n')
 rows=data.decode('ascii').splitlines();pairs=[line.split('=',1) for line in rows];assert all(len(p)==2 for p in pairs)
 values=dict(pairs);assert len(pairs)==len(values)==26
 out=DEVICE/'analysis'/('f360-expected-config-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);restrict_acl(out,directory=True)
 rootfs=F358/(BASE+'.rootfs.squashfs');manifest=json.loads((F358/'manifest.json').read_text());assert sha(rootfs)==manifest['artifacts']['rootfs_squashfs']['sha256']
 read=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','unsquashfs','-cat',linux(rootfs),'usr/sbin/om-config-prepare'],capture_output=True,check=True)
 normalizer=out/'om-config-prepare';normalizer.write_bytes(read.stdout);assert sha(normalizer)=='c909f0bcfcc111c11ac0a5a6767c643321e6eae8dbb4d3c4c5600c2a27cbc51f'
 generated_keys=re.findall(rb"printf '([A-Z0-9_]+)=%s",read.stdout);assert len(generated_keys)==26 and {p.decode() for p in generated_keys}==set(values)
 origin=out/'origin.fixture.conf';origin.write_bytes(('ORIGIN_MTD5_IMPORTED='+values['ORIGIN_MTD5_IMPORTED']+'\nRADIO5G_SSID='+values['RADIO5G_SSID']+'\n').encode('ascii'));restrict_acl(origin,directory=False)
 runtime=out/'normalized';runtime.mkdir()
 command=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','env','LC_ALL=C','OM_CONFIG_NO_SIDE_EFFECTS=1','OM_CONFIG_DEFAULTS='+linux(PAYLOAD),'OM_CONFIG_PERSIST_ROOT='+linux(out/'absent-persist'),'OM_CONFIG_RUNTIME='+linux(runtime),'OM_ORIGIN_RUNTIME='+linux(origin),'/bin/sh',linux(normalizer)]
 r=subprocess.run(command,capture_output=True);assert r.returncode==0 and not r.stderr,'normalizer failed'
 assert (runtime/'active.conf').read_bytes()==data,'normalizer changed the captured configuration'
 core=ROOT/'work/kernel-port/modules/f342_config_journal/f342_journal.c';header=core.with_suffix('.h');ops=ROOT/'work/kernel-port/modules/f318_store_transaction/f318_store_transaction.h'
 assert sha(core)=='60862469525a6181d4e38ff7743e30accd820b8f058a4550f4e23de8ffc6fc4f'
 q=shlex.quote
 script=f'''set -eu
umask 077
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I{q(linux(core.parent))} -I{q(linux(ops.parent))} {q(linux(core))} {q(linux(ROOT/'tools/f360_expected_journal.c'))} -o {q(linux(out/'generate'))}
{q(linux(out/'generate'))} {q(linux(PAYLOAD))} {q(linux(out/'expected-dc-dd.bin'))}
'''
 (out/'generate.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'generate.sh')],capture_output=True);assert run.returncode==0 and not run.stderr,'F342 generation failed'
 generation=json.loads(run.stdout);assert generation['save_calls']==1 and generation['slot']==0 and generation['sequence']==1 and generation['payload_bytes']==586
 pair=(out/'expected-dc-dd.bin').read_bytes();assert len(pair)==131072 and pair[65536:]==b'\xff'*65536
 dc=pair[:65536];assert dc[32:32+586]==data and dc[:4]==bytes(4) and dc[4:8]==b'F342' and dc[32+586:]==b'\xff'*(65536-32-586)
 assert int.from_bytes(dc[24:28],'little')==zlib.crc32(data)&0xffffffff and int.from_bytes(dc[28:32],'little')==zlib.crc32(dc[4:28])&0xffffffff
 for name,content in [('expected-dc.bin',dc),('expected-dd.bin',pair[65536:]),('original-dc-ff.bin',b'\xff'*65536),('expected-store.bin',pair+b'\xff'*(0x1c0000-len(pair)))]:
  target=out/name;target.write_bytes(content);restrict_acl(target,directory=False)
 fw=(F358/(BASE+'.webformat.bin')).read_bytes();assert hashlib.sha256(fw).hexdigest()=='fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f'
 prefix=fw+b'\xff'*(0x5e0000-len(fw));initial_slot=fw+b'\xff'*(0x7a0000-len(fw));expected_slot=prefix+(out/'expected-store.bin').read_bytes()
 assert f'{zlib.crc32(initial_slot)&0xffffffff:08x}'=='4d006632'
 result={'schema':'openmitrastar.f360-expected-config/v1','status':'PASS_PRIVATE_PAYLOAD_AND_SINGLE_F342_GENERATION','hardware_actions':False,'payload':item(PAYLOAD),'payload_values_changed':False,'key_count':26,
  'validator':{'path':str(normalizer),'sha256':sha(normalizer),'real_image_path':'/usr/sbin/om-config-prepare','mode':'exact producer/normalizer round-trip, byte identical, side effects disabled','origin_fixture_source':'captured active.conf fields only; no new mtd5 validation'},
  'generation':generation,'artifacts':{name:item(out/name) for name in ['expected-dc.bin','expected-dd.bin','expected-dc-dd.bin','expected-store.bin','original-dc-ff.bin']},
  'header':{'bytes':32,'hex':dc[:32].hex(),'commit_offset':0,'commit_bytes':4,'payload_offset':32,'slot':0,'sequence':1,'payload_crc32':f'{zlib.crc32(data)&0xffffffff:08x}','header_crc32':f'{zlib.crc32(dc[4:28])&0xffffffff:08x}'},
  'expected_after_save':{'firmware_prefix_bytes':len(prefix),'firmware_prefix_crc32':f'{zlib.crc32(prefix)&0xffffffff:08x}','full_slot_crc32':f'{zlib.crc32(expected_slot)&0xffffffff:08x}','full_slot_sha256':hashlib.sha256(expected_slot).hexdigest(),'protected_crc32':{'mtd0':'347cf8db','mtd1':'05624c17','mtd2':'13b7c1f7','mtd3':'f7d14d3d','mtd5':'1165e46d'}},
  'original':{'dc_ff':True,'dd_ff':True,'remaining_store_expected_ff':True,'store_crc32':f'{zlib.crc32(bytes([255])*0x1c0000)&0xffffffff:08x}','store_sha256':hashlib.sha256(bytes([255])*0x1c0000).hexdigest(),'full_slot_crc32':'4d006632','prewrite_confirmation_required':True},
  'postboot_readback':{'mtd_name':'lyoko_store','expected_runtime_index':4,'require_unique_name_size_ro':True,'bytes':0x1c0000,'dc_offset':0,'dd_offset':0x10000,'physical_spi_offset':0xdc0000,'note':'Linux mtd4 is the ROM store view, not the physical linux_live partition numbering'},
  'rollback':{'target':'DC only at SPI offset0xdc0000,65536B','expected':item(out/'original-dc-ff.bin'),'requires':'fresh/reset-proven domain, exclusive owner, observed IDc22018 CTRL4 WIP/WEL0 SR0 SCUR0, no quarantine, original DD/rest/store and protected witnesses intact','operation':'erase-only DC via separately qualified executor primitive; never a second SAVE, no DD/global-unlock','eligibility_not_assumed':True},
  'source_pins':{str(p):sha(p) for p in [core,header,ops,ROOT/'tools/f360_expected_journal.c',Path(__file__),PAYLOAD,normalizer]}}
 for p in out.rglob('*'):
  if p.is_file():restrict_acl(p,directory=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');restrict_acl(out/'result.json',directory=False)
 print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'payload_bytes':len(data),'payload_sha256':sha(PAYLOAD),'operations':generation['operations'],'expected_dc':result['artifacts']['expected-dc.bin'],'expected_store':result['artifacts']['expected-store.bin'],'expected_full_slot_crc32':result['expected_after_save']['full_slot_crc32']}))
if __name__=='__main__':main()
