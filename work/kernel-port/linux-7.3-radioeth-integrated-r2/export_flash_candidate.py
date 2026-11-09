"""Export exact private image and public receipts, never credentials or key bytes."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,zlib
WORK=Path('/workspace/user-home/Desktop/MitraStar')
BUILD=Path('/home/rea/openmitrastar-linux73-20261022T135100Z/radio73-2g-flash-autostart-r1-v2')
QUAL=BUILD.parent/'radio73-2g-flash-qualified-v2'
PRIVATE=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radio73-2g-doom-autostart-20261023-v2')
PUBLIC=WORK/'outputs/rea/radio73-2g-doom-autostart-offline-20261023-v2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if PRIVATE.exists() or PUBLIC.exists():raise RuntimeError('Immutable output exists')
 b=json.loads((BUILD/'result.json').read_text());q=json.loads((QUAL/'result.json').read_text())
 assert b['status']=='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN'
 assert q['status']=='PASS_INDEPENDENT_2G_FLATCPIO_LZMA_ENTRY_PREFIX_ROOT_CONTRACTS'
 assert q['build_result_sha256']==sha(BUILD/'result.json')
 os.umask(0o077);PRIVATE.mkdir(mode=0o700);PUBLIC.mkdir()
 lane=b['lanes'][0];image=PRIVATE/'radio73-2g-doom-autostart.ras.bin'
 image.write_bytes((BUILD/'radio73-2g-doom-autostart-a.ras.bin').read_bytes())
 assert sha(image)==lane['image_sha256']
 certificate=PRIVATE/'server.pem';certificate.write_bytes((BUILD/'initramfs/root/etc/lyoko/tls/server.pem').read_bytes())
 for src,name in [(BUILD/'result.json','BUILD_RESULT.json'),(QUAL/'result.json','QUALIFICATION.json')]:
  (PUBLIC/name).write_bytes(src.read_bytes())
 config={'classification':'FLASH_CANDIDATE_NEEDS_RAM_BOOT_READBACK_ROLLBACK','image':str(image).replace('/mnt/c/','C:/'),'bytes':lane['image_bytes'],'sha256':lane['image_sha256'],'crc32':lane['image_crc32'],'payload_bytes':lane['payload_bytes'],'raw_sha256':lane['raw_sha256'],'raw_bytes':lane['raw_bytes'],'entry':lane['entry'],'end':lane['end'],'compression':3,'kernel_release':'7.3.0-openmitrastar-radio73-v1','product_release':'lyoko-linux73-2g-doom-flash-r1','receipt':str(PUBLIC/'BUILD_RESULT.json').replace('/mnt/c/','C:/'),'receipt_sha256':sha(PUBLIC/'BUILD_RESULT.json'),'qualification':str(PUBLIC/'QUALIFICATION.json').replace('/mnt/c/','C:/'),'qualification_sha256':sha(PUBLIC/'QUALIFICATION.json'),'tls_cert':str(certificate).replace('/mnt/c/','C:/'),'tls_cert_sha256':sha(certificate),'normal_flash_offset':0x7e0000,'prefix_bytes':0x5e0000,'preserved_store_bytes':0x1c0000,'autostart':'2g WPA2 ES1 and WLAN DHCP; selected Ethernet; SSH22/HTTPS443; DoomXZ','physical_boot':'UNRUN','flash_writes':0,'bootenv_writes':0}
 (PRIVATE/'CONFIG.json').write_text(json.dumps(config,indent=2)+'\n')
 manifest=config|{'status':'PASS_OFFLINE_PAIR_FLATCPIO_LZMA_BOOTBASE_PREFIX_PHYSICAL_UNRUN','prefix_headroom_bytes':lane['prefix_headroom'],'game_bytes':b['game_bytes'],'init_sha256':b['init_sha256'],'dhcp':b['dhcp'],'flash_go_no_go':'PHYSICAL_RAM_BOOT_READBACK_ROLLBACK_PENDING'}
 (PUBLIC/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'status':manifest['status'],'bytes':config['bytes'],'sha256':config['sha256'],'config':str(PRIVATE/'CONFIG.json').replace('/mnt/c/','C:/')}))
if __name__=='__main__':main()
