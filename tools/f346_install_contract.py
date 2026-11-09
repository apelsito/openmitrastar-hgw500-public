"""File-only exact-image contract for F340 install and conditional F321 return."""
from pathlib import Path
import hashlib,json,zlib
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware'
LIVE=0x007e0000
PREFIX=0x005e0000
SLOT=0x007a0000
STORE=0x00dc0000
STORE_BYTES=SLOT-PREFIX
LOAD=0x83000000
READBACK=0x86000000
SCRATCH=0x84000000
PNP=r'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'
BOOTARGS='earlycon=uart8250,mmio32,0xf0000000 console=ttyS0,115200n8 root=31:3 rootfstype=squashfs ro rootwait init=/sbin/init panic=10'
SPECS={
 'f340':dict(directory='f340-f321-watchdog-baseline-device-bound',base='openmitrastar-linux510-f340-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH',bytes=5349376,
    sha256='211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa',manifest_sha256='91804168356f540401efb25abaa71e38f81f2de5c356b764d8b0b3f851369bed',
    version='lyoko-foundation-6.9.6-f340-watchdog-baseline-device',known_hosts='known_hosts.f340',kernel_build='#340',marker='F340_WATCHDOG_BASELINE'),
 'f321':dict(directory='f321-f314-device-bound',base='openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH',bytes=5337088,
    sha256='eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18',manifest_sha256='2b8b2f2b2e2b845c1fe660b7f89feb34da113b60ad43c6c42f312f3621dc87ff',
    version='lyoko-foundation-6.8.5-f321-classic-ui-f314-device',known_hosts='known_hosts.f321',kernel_build='#1',marker=''),
}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def crc(data):return f'{zlib.crc32(data)&0xffffffff:08x}'
def require(ok,code):
 if not ok:raise ValueError(code)
def images():
 result={}
 for name,spec in SPECS.items():
  folder=DEVICE/spec['directory'];path=folder/(spec['base']+'.webformat.bin');data=path.read_bytes();manifest=folder/'manifest.json'
  require(len(data)==spec['bytes'] and hashlib.sha256(data).hexdigest()==spec['sha256'] and sha(manifest)==spec['manifest_sha256'],'image_binding')
  require(len(data)<PREFIX,'store_overlap');contract=image_to_dict(validate_bootbase_slot(name,data,SLOT));require(contract['accepted_by_contract'],'bootbase_contract')
  require(contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','kernel_entry')
  full=data+b'\xff'*(SLOT-len(data));prefix=data+b'\xff'*(PREFIX-len(data))
  result[name]={**spec,'directory':str(folder),'path':str(path),'crc32':crc(data),'prefix_crc32':crc(prefix),'full_slot_crc32':crc(full),'full_slot_sha256':hashlib.sha256(full).hexdigest(),'known_hosts_path':str(folder/spec['known_hosts'])}
 require(Path(result['f340']['known_hosts_path']).read_bytes()==Path(result['f321']['known_hosts_path']).read_bytes(),'SSH_identity_changed')
 return result
def protected_backups():
 path=ROOT/'outputs/flash-backups/hgw500-physical-ssh-20260823T220312Z/current-unit/manifest.json'
 require(sha(path)=='8f3bbed7a9ed9ed07a86ba8b07aa30bc1f1ddf26940025ad1f64c8dae53b1fbf','backup_manifest_binding')
 manifest=json.loads(path.read_text(encoding='utf-8'));require(manifest['read_only_capture'] is True and manifest['mtd6_included'] is False,'backup_scope')
 expected={0:(0,0x20000),1:(0x20000,0x10000),2:(0x30000,0x10000),3:(0x40000,0x7a0000),5:(0xf80000,0x80000)};parts=[]
 for item in manifest['partitions']:
  index=item['index']
  if index not in expected:continue
  offset,size=expected[index];file=(path.parent/item['file']).resolve()
  require(file.is_relative_to(path.parent.resolve()) and item['offset']==offset and item['size']==size and file.stat().st_size==size and sha(file)==item['sha256'],'protected_backup_binding')
  parts.append(dict(partition='mtd'+str(index),offset=offset,bytes=size,path=str(file),sha256=item['sha256'],crc32=crc(file.read_bytes())))
 require(len(parts)==5,'protected_backup_cardinality');return dict(manifest=str(path),sha256=sha(path),parts=parts)
def validate_proofs():
 paths=[('outputs/preflight/f340-qualified-20260921T134752Z/result.json','a2c151a6f437e5671c9af56df60376d414290feb10afd2160249e0b9994bf354','PASS_OFFLINE_FULLIMAGE_AND_SUPERVISOR'),
        ('outputs/preflight/f340-f336-physical-link-20260921T135057Z/result.json','eb5fe066316b0311eada927378af4aff4d89eab506797743c3791ca544644aed','PASS_F336_CESSATION_COMPONENT_EVIDENCE'),
        ('outputs/preflight/f346-bootbase-paths-20260921T144707Z/result.json','c0668eddd0bb2c18470a5debda705161c0297fa04eff2044b12703a6439de17d','PASS_STATIC_BOUND_REVIEW')]
 result=[]
 for rel,digest,status in paths:
  path=ROOT/rel;require(sha(path)==digest,'prerequisite_hash');data=json.loads(path.read_text(encoding='utf-8'));require(data['status']==status and all(data['checks'].values()),'prerequisite_not_passed');result.append(dict(path=str(path),sha256=digest))
 return result
