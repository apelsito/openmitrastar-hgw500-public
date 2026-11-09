"""Bind exact final2g candidate, qualified image and owned private Windows ACL."""
from pathlib import Path
import json,hashlib,subprocess,sys
BUILD=Path('/home/rea/openmitrastar-linux73-20261022T135100Z/radio73-2g-flash-autostart-r1-v4')
QUAL=BUILD.parent/'radio73-2g-flash-qualified-v4'
WORK=Path('/workspace/user-home/Desktop/MitraStar')
PRIVATE=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radio73-2g-doom-autostart-20261023-v4')
PUBLIC=WORK/'outputs/rea/radio73-2g-doom-autostart-offline-20261023-v4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def win(p):return str(p).replace('/mnt/c/','C:/')
def main():
 if PRIVATE.exists() or PUBLIC.exists():raise RuntimeError('Immutable output')
 b=json.loads((BUILD/'result.json').read_text());q=json.loads((QUAL/'result.json').read_text())
 assert b['status']=='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN'
 assert q['build_result_sha256']==sha(BUILD/'result.json')
 PRIVATE.mkdir(mode=0o700);PUBLIC.mkdir()
 image=PRIVATE/'radio73-2g-doom-autostart.ras.bin'
 image.write_bytes((BUILD/'radio73-2g-doom-autostart-a.ras.bin').read_bytes())
 cert=PRIVATE/'server.pem';cert.write_bytes((BUILD/'initramfs/root/etc/lyoko/tls/server.pem').read_bytes())
 for src,name in [(BUILD/'result.json','BUILD_RESULT.json'),(QUAL/'result.json','QUALIFICATION.json')]:
  (PUBLIC/name).write_bytes(src.read_bytes())
 inventory=[{'path':'/'+p.relative_to(BUILD/'initramfs/root').as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted((BUILD/'initramfs/root').rglob('*')) if p.is_file() and not p.is_symlink() and not any(k in p.relative_to(BUILD/'initramfs/root').as_posix() for k in ['server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow'])]
 (PUBLIC/'PUBLIC_ROOT_INVENTORY.json').write_text(json.dumps(inventory,indent=2)+'\n')
 row=b['lanes'][0]
 config={'classification':'FLASH_CANDIDATE_NEEDS_RAM_BOOT_READBACK_ROLLBACK','image':win(image),'bytes':row['image_bytes'],'sha256':row['image_sha256'],'crc32':row['image_crc32'],'payload_bytes':row['payload_bytes'],'raw_sha256':row['raw_sha256'],'raw_bytes':row['raw_bytes'],'entry':row['entry'],'end':row['end'],'compression':3,'kernel_release':'7.3.0-openmitrastar-radio73-v1','product_release':'lyoko-linux73-2g-doom-flash-r1','receipt':win(PUBLIC/'BUILD_RESULT.json'),'receipt_sha256':sha(PUBLIC/'BUILD_RESULT.json'),'qualification':win(PUBLIC/'QUALIFICATION.json'),'qualification_sha256':sha(PUBLIC/'QUALIFICATION.json'),'tls_cert':win(cert),'tls_cert_sha256':sha(cert),'normal_flash_offset':0x7e0000,'prefix_bytes':0x5e0000,'preserved_store_bytes':0x1c0000,'prefix_headroom_bytes':row['prefix_headroom'],'physical_boot':'UNRUN','flash_writes':0,'bootenv_writes':0,'root_inventory':win(PUBLIC/'PUBLIC_ROOT_INVENTORY.json'),'root_inventory_sha256':sha(PUBLIC/'PUBLIC_ROOT_INVENTORY.json')}
 (PRIVATE/'CONFIG.json').write_text(json.dumps(config,indent=2)+'\n')
 (PUBLIC/'MANIFEST.json').write_text(json.dumps(config|{'status':'PASS_OFFLINE_PAIR_BOOTBASE_PREFIX_ROOT_AUTOSTART','game_bytes':b['game_bytes'],'flash_go_no_go':'RAM_BOOT_AND_CURRENT_READBACK_ROLLBACK_PENDING'},indent=2)+'\n')
 print(json.dumps({'config':win(PRIVATE/'CONFIG.json'),'bytes':row['image_bytes'],'sha256':row['image_sha256']}))
if __name__=='__main__':main()
